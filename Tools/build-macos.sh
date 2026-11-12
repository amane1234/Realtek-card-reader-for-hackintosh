#!/bin/bash
# Build this source tree and, if present, the sibling Friend tree. No EFI changes.
set -euo pipefail
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Requires macOS with full Xcode; Linux cannot build this kext.' >&2
  exit 1
fi
xcodebuild -version
root="$(cd "$(dirname "$0")/.." && pwd)"
sdk_ref=3f750085caa17ec3a7880f11c11bf4f48cd6a164
lilu_ref=0249c3a918c68a43891350f35fded615b1575776
checkout_dependency() {
  local repo="$1" target="$2" ref="$3"
  if [[ -e "$target" ]]; then
    [[ "$(git -C "$target" rev-parse HEAD)" == "$ref" ]] || {
      echo "Dependency at $target differs from pinned revision; use a clean source folder." >&2
      exit 1
    }
    [[ -z "$(git -C "$target" status --porcelain --untracked-files=no)" ]] || {
      echo "Tracked dependency files modified at $target." >&2; exit 1;
    }
  else
    git init "$target"
    git -C "$target" remote add origin "$repo"
    git -C "$target" fetch --depth 1 origin "$ref"
    git -C "$target" checkout --detach FETCH_HEAD
  fi
}
checkout_dependency https://github.com/acidanthera/MacKernelSDK.git "$root/MacKernelSDK" "$sdk_ref"
cd "$root"
for configuration in Debug Release; do
  xcodebuild -project RealtekCardReader.xcodeproj -configuration "$configuration" -arch x86_64 CODE_SIGNING_ALLOWED=NO
 done
friend="$root/../RealtekCardReaderFriend"
if [[ -d "$friend/RealtekCardReaderFriend.xcodeproj" ]]; then
  checkout_dependency https://github.com/acidanthera/MacKernelSDK.git "$friend/MacKernelSDK" "$sdk_ref"
  checkout_dependency https://github.com/acidanthera/Lilu.git "$root/Dependencies/Lilu" "$lilu_ref"
  checkout_dependency https://github.com/acidanthera/MacKernelSDK.git "$root/Dependencies/Lilu/MacKernelSDK" "$sdk_ref"
  (cd "$root/Dependencies/Lilu" && xcodebuild -configuration Debug -arch x86_64 CODE_SIGNING_ALLOWED=NO)
  if [[ -e "$friend/Lilu.kext" ]]; then
    echo 'Existing Friend/Lilu.kext: move it aside before building to avoid mixing SDKs.' >&2
    exit 1
  fi
  cp -R "$root/Dependencies/Lilu/build/Debug/Lilu.kext" "$friend/Lilu.kext"
  cd "$friend"
  for configuration in Debug Release; do
    xcodebuild -project RealtekCardReaderFriend.xcodeproj -configuration "$configuration" -arch x86_64 CODE_SIGNING_ALLOWED=NO
  done
fi
printf '\nBuild complete. Outputs are in each project build/Debug and build/Release.\n'
