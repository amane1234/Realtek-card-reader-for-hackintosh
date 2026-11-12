#!/usr/bin/env python3
"""Compile actual controller method bodies against small IOKit doubles.
This checks logic only, not the macOS ABI, DMA, scheduling or hardware.
"""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'RealtekCardReader/RealtekPCICardReaderController.cpp').read_text()

def method(name):
    marker = 'RealtekPCICardReaderController::' + name + '('
    pos = source.index(marker)
    start = source.rfind('\n', 0, pos) + 1
    brace = source.index('{', pos)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

preamble = r'''
#include <cassert>
#include <cstdint>
#include <vector>
#include <iostream>
using UInt32 = uint32_t;
constexpr int kIOReturnSuccess=0, kIOReturnError=1, kIOReturnNotReady=2, kIOReturnTimeout=3;
constexpr int kIOInterruptTypePCIMessaged=4;
#define pinfo(...) ((void)0)
#define perr(...) ((void)0)
#define pwarning(...) ((void)0)
#define YESNO(x) ((x)?"yes":"no")
#define OSSafeReleaseNULL(x) do { (x)->release(); (x)=nullptr; } while(0)
#define OSMemberFunctionCast(type, owner, method) 0
namespace UserConfigs::PCR { bool DisableMSI=false; }
namespace RTSX::MMIO {
constexpr UInt32 rBIPR=0x14, rBIER=0x18;
namespace BIPR {
constexpr UInt32 kTransferSucceeded=1U<<29, kTransferFailed=1U<<28;
constexpr UInt32 kSD=1U<<25, kSDExists=1U<<16, kSDOvercurrentOccurred=1U<<22;
}}
struct BitOptions {
    UInt32 bits;
    BitOptions(UInt32 v):bits(v) {}
    UInt32 flatten() const { return bits; }
    bool contains(UInt32 mask) const { return (bits&mask)==mask; }
    void mutativeBitwiseAnd(UInt32 mask) { bits &= mask; }
};
struct IOInterruptEventSource {};
struct IOTimerEventSource { int cancellations=0; void cancelTimeout() { ++cancellations; } };
struct Gate { int wakeups=0; void commandWakeup(void*) { ++wakeups; } };
struct Device {
    std::vector<int> types;
    int getInterruptType(int i, int* out) {
        if (i>=static_cast<int>(types.size())) return kIOReturnError;
        *out=types[i]; return kIOReturnSuccess;
    }
};
struct IOFilterInterruptEventSource: IOInterruptEventSource {
    using Filter=int; using Action=int;
    static inline bool fail=false;
    static inline int releases=0;
    bool enabled=false;
    static IOFilterInterruptEventSource* filterInterruptEventSource(void*, int, int, Device*, int) {
        return fail ? nullptr : new IOFilterInterruptEventSource;
    }
    void enable() { enabled=true; }
    void disable() { enabled=false; }
    void release() { ++releases; delete this; }
};
struct WorkLoop {
    int result=0;
    int addEventSource(IOFilterInterruptEventSource*) { return result; }
};
class RealtekPCICardReaderController {
public:
    UInt32 pending=0, enabled=0; int writes=0;
    int hostBufferTransferStatus=kIOReturnNotReady;
    IOTimerEventSource timer; IOTimerEventSource* hostBufferTimer=&timer;
    Gate gate; Gate* commandGate=&gate;
    Device dev; Device* device=&dev;
    WorkLoop loop; WorkLoop* workLoop=&loop;
    IOFilterInterruptEventSource* interruptEventSource=nullptr;
    struct { struct { bool enable=true; } ocp; } parameters;
    void* slot=this;
    int dmaErrorCounter=7, insertions=0, removals=0, overcurrents=0;
    UInt32 readRegister32(UInt32 reg) { return reg==RTSX::MMIO::rBIPR?pending:enabled; }
    void writeRegister32(UInt32 reg, UInt32 value) {
        ++writes;
        if(reg==RTSX::MMIO::rBIER) enabled=value;
        else pending &= ~value;
    }
    void onSDCardInsertedGated() { ++insertions; }
    void onSDCardRemovedGated() { ++removals; }
    void onSDCardOvercurrentOccurredGated() { ++overcurrents; }
    bool interruptEventSourceFilter(IOFilterInterruptEventSource*);
    void interruptHandlerGated(IOInterruptEventSource*, int);
    void bufferTransferTimeoutHandlerGated(IOTimerEventSource*);
    void onTransferDoneGated(bool);
    int probeMSIIndex();
    bool setupInterrupts();
};
'''
checks = r'''
int main() {
    using C=RealtekPCICardReaderController;
    using namespace RTSX::MMIO::BIPR;
    // All combinations of success, failure and pending state: one completion,
    // failure wins, and completed/timed-out transfers keep their result.
    for(int state=0;state<4;++state) for(int flags=0;flags<4;++flags) {
        C c; c.hostBufferTransferStatus=state;
        c.enabled=kTransferSucceeded|kTransferFailed;
        c.pending=((flags&1)?kTransferSucceeded:0)|((flags&2)?kTransferFailed:0);
        c.interruptHandlerGated(nullptr,1);
        bool completes=state==kIOReturnNotReady && flags!=0;
        assert(c.gate.wakeups==(completes?1:0));
        int expected=completes?((flags&2)?kIOReturnError:kIOReturnSuccess):state;
        assert(c.hostBufferTransferStatus==expected);
    }
    for(auto invalid : {false,true}) {
        C c; c.pending=invalid?0xFFFFFFFF:kTransferSucceeded;
        c.enabled=invalid?kTransferSucceeded:0xFFFFFFFF;
        assert(!c.interruptEventSourceFilter(nullptr));
        c.interruptHandlerGated(nullptr,1);
        assert(c.writes==0 && c.gate.wakeups==0);
    }
    { C c; c.pending=kTransferSucceeded; assert(!c.interruptEventSourceFilter(nullptr));
      c.interruptHandlerGated(nullptr,1); assert(c.gate.wakeups==0); }
    for(int state=0;state<4;++state) {
        C c; c.hostBufferTransferStatus=state;
        c.bufferTransferTimeoutHandlerGated(nullptr);
        assert(c.gate.wakeups==(state==kIOReturnNotReady?1:0));
        assert(c.hostBufferTransferStatus==(state==kIOReturnNotReady?kIOReturnTimeout:state));
        c.onTransferDoneGated(true); // a late IRQ cannot turn timeout into success
        assert(c.gate.wakeups==(state==kIOReturnNotReady?1:0));
    }
    { C c; c.hostBufferTimer=nullptr; c.onTransferDoneGated(true); assert(c.gate.wakeups==0); }
    for(bool attached : {false,true}) for(bool present : {false,true}) {
        C c; c.slot=attached?&c:nullptr;
        c.enabled=kSD; c.pending=kSD|(present?kSDExists:0);
        assert(c.interruptEventSourceFilter(nullptr));
        c.interruptHandlerGated(nullptr,1);
        assert(c.insertions==(attached&&present?1:0));
        assert(c.removals==(attached&&!present?1:0));
    }
    { C c; c.enabled=kSDOvercurrentOccurred; c.pending=c.enabled;
      c.interruptHandlerGated(nullptr,1); assert(c.overcurrents==1); }
    { C c; c.dev.types={1,4}; assert(c.probeMSIIndex()==1);
      UserConfigs::PCR::DisableMSI=true; assert(c.probeMSIIndex()==0); }
    { C c; c.dev.types={4,1}; assert(c.probeMSIIndex()==1); }
    { C c; c.dev.types={4}; assert(c.probeMSIIndex()==-1); }
    UserConfigs::PCR::DisableMSI=false;
    { C c; c.dev.types={1}; assert(c.probeMSIIndex()==0); }
    { C c; assert(c.probeMSIIndex()==-1); assert(!c.setupInterrupts()); }
    { C c; c.dev.types={4}; c.loop.result=kIOReturnError;
      assert(!c.setupInterrupts()); assert(c.interruptEventSource==nullptr);
      assert(IOFilterInterruptEventSource::releases==1); }
    { C c; c.dev.types={4}; IOFilterInterruptEventSource::fail=true;
      assert(!c.setupInterrupts()); IOFilterInterruptEventSource::fail=false; }
    { C c; c.dev.types={4}; c.enabled=0xFFFFFFFF;
      assert(c.setupInterrupts()); assert(c.enabled==0);
      assert(c.interruptEventSource->enabled); c.interruptEventSource->release(); }
    std::cout << "PASS: interrupt selection, registration, filtering, completion, timeout and card events\n";
}
'''
methods = ['interruptEventSourceFilter', 'interruptHandlerGated', 'bufferTransferTimeoutHandlerGated', 'onTransferDoneGated', 'probeMSIIndex', 'setupInterrupts']
with tempfile.TemporaryDirectory() as directory:
    cpp = Path(directory) / 'test.cpp'
    exe = Path(directory) / 'test'
    cpp.write_text(preamble + '\n'.join(method(n) for n in methods) + checks)
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', str(cpp), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
