#!/usr/bin/env bash
set -euo pipefail
IPA=${1:?usage: install_ipa_on_device.sh path/to/Blink.ipa [device-udid]}
DEVICE=${2:-00008140-000179AC3062201C}
WORK=${TMPDIR:-/tmp}/blink-install-$$
rm -rf "$WORK"
mkdir -p "$WORK"
unzip -q "$IPA" -d "$WORK"
test -d "$WORK/Payload/Blink.app"
xcrun devicectl device install app --device "$DEVICE" "$WORK/Payload/Blink.app" --timeout 120
