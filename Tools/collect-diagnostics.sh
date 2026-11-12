#!/bin/bash
# Read-only: prints selected device properties and relevant logs to stdout.
set -u
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Run this on the affected macOS machine.' >&2
  exit 1
fi
printf '\n== macOS ==\n'
sw_vers
uname -r
printf '\n== Loaded card-reader and Lilu extensions ==\n'
kmutil showloaded 2>&1 | grep -Ei 'rtsx|realtekcard|lilu|error|failed' || true
printf '\n== PCI reader identity and matching ==\n'
ioreg -r -c IOPCIDevice -l -w0 | grep -E '(^[ |+`-]*\+-o|"(vendor-id|device-id|revision-id|class-code|IOName|IOPCIMatch|IOPCITunnelled)")' || true
printf '\n== Driver objects ==\n'
ioreg -p IOService -w0 | grep -Ei 'Realtek.*(Controller|Slot)|WolfsSDXC|IOSDHostDriver|IOSDBlockStorageDevice' || true
printf '\n== USB reader identity ==\n'
system_profiler SPUSBDataType | grep -Ei -A10 -B2 'card reader|rtsx|rts51|realtek' || true
printf '\n== Relevant recent logs ==\n'
log show --last 10m --style compact --predicate 'process == "kernel" AND (eventMessage CONTAINS[c] "rtsx" OR eventMessage CONTAINS[c] "IOSD" OR eventMessage CONTAINS[c] "RealtekPCI" OR eventMessage CONTAINS[c] "RTSF")' 2>&1
