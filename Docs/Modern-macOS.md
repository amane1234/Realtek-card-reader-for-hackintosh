# Sequoia / Tahoe experimental work

This branch targets Intel macOS Sequoia (Darwin 24) and Tahoe (Darwin 25).
It is based on amane1234/RealtekCardReader commit
006a8455d0ecf34571531f2c1471cddb4fc9303b. No reader hardware was available during
implementation. Do not interpret a successful build as verified OS/device support.

## Changes and rationale

- Match Linux rtsx_pci_isr's failure-before-success rule; complete only a pending
  transfer. Ignore duplicate/late completion and timeout callbacks after a result.
- Reject inaccessible all-ones PCI register reads and recheck enabled IRQs in the
  gated handler. Ignore card callbacks until the slot exists.
- Allocate completion resources before registering interrupts; mask controller
  interrupts before registration and before teardown. Remove the IRQ source before
  releasing host transfer buffers.
- Treat workloop registration failure as startup failure, releasing the source.
- Prefer MSI; fall back only to a legacy interrupt actually advertised by IOKit.
  `-rtsxnomsi` explicitly selects legacy IRQs for diagnosis, and fails clearly when
  none is available. This option is PCIe-only; it does not fix firmware IRQ routing.
- Update obsolete CI actions and pin MacKernelSDK for reproducible Debug/Release
  x86_64 builds on macos-15. The runner tests building, not attaching a reader.

These are bounded PCIe robustness changes, not a full port of current Linux RTSX.
No new chip IDs, USB controller logic, chip-specific voltage tables, SD Express,
MMC support, complete suspend/resume redesign, card-detect debounce or new DMA
implementation are included. Late events from an *older transfer after a new
transfer has started* still require hardware-level investigation. Existing power
management and concurrent teardown behavior still need hardware stress testing.

## Reference implementation

The IRQ result ordering and enabled-bit handling were compared to Linux v6.12:
https://github.com/torvalds/linux/blob/v6.12/drivers/misc/cardreader/rtsx_pcr.c
(`rtsx_pci_isr`, `rtsx_pci_acquire_irq`). The implementation here uses this
project's IOKit abstractions. Linux source is not bundled.

## Build / check

On macOS with full Xcode selected:

```sh
bash Tools/build-macos.sh
python3 Tests/test_interrupts.py
```

The build script downloads pinned MacKernelSDK and builds Debug and Release.
It builds the optional sibling RealtekCardReaderFriend tree only if present.
Output: `build/Debug/RealtekCardReader.kext` and
`build/Release/RealtekCardReader.kext` (plus the project's ZIP archives).
The test harness compiles actual method bodies with IOKit doubles. It checks
interrupt behavior and registration failures, not kernel ABI or hardware timing.

## Test on the affected machine

1. Keep a bootable backup EFI. Replace the existing RealtekCardReader entry rather
   than loading two copies. Check the OpenCore Kernel/Add entry is enabled and
   that any MinKernel/MaxKernel restriction includes the target Darwin version.
2. First test RealtekCardReader alone; Friend is optional and only changes the
   System Information display. Do not use its version override as an I/O fix.
3. Test a cold boot with and without a card, insertion/removal, reading a known
   file, then writes on a disposable test card with checksum verification.
4. If initialization fails in UHS/1.8 V mode, compare a boot using the existing
   `-iosd3v3` argument. This avoids UHS; reduced throughput is expected. It cannot
   fix an unsupported chip or a driver that never attaches.
5. If logs show command/DMA timeouts, compare the default boot to `-rtsxnomsi`.
   Change only one diagnostic option per boot. Remove it if startup reports no
   advertised legacy IRQ. Do not keep this option solely because the OS is new.
6. Test sleep/wake, removal during sleep and repeated insertion. The upstream
   sleep/ejection limitation is not claimed fixed by this patch.

Capture diagnostics after reproducing the failure with the Debug build:

```sh
bash Tools/collect-diagnostics.sh > cardreader-diagnostics.txt
```

Review the report before sharing: USB device details/logs can contain identifiers.
Provide the PCI vendor:device and revision (or USB VID:PID), exact macOS build,
whether failure occurs on cold boot, hot insertion or wake, and this report.
Without those details no chip-specific fix or working-device claim is possible.
