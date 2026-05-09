#!/usr/bin/env bash
set -euo pipefail
IPA=${1:?usage: verify_ipa.sh path/to/Blink.ipa}
REPORT_DIR=build/verification
WORK=$REPORT_DIR/ipa
rm -rf "$REPORT_DIR"
mkdir -p "$WORK"
unzip -q "$IPA" -d "$WORK"
test -d "$WORK/Payload/Blink.app"
APP="$WORK/Payload/Blink.app"
/usr/bin/codesign --verify --deep --strict --verbose=4 "$APP" 2>&1 | tee "$REPORT_DIR/codesign-app.txt"
for appex in "$APP"/PlugIns/*.appex; do
  [ -d "$appex" ] || continue
  /usr/bin/codesign --verify --strict --verbose=4 "$appex" 2>&1 | tee "$REPORT_DIR/codesign-$(basename "$appex").txt"
done
/usr/bin/codesign -d --entitlements :- "$APP" > "$REPORT_DIR/Blink.entitlements.plist" 2>/dev/null
if /usr/libexec/PlistBuddy -c 'Print :com.apple.developer.web-browser' "$REPORT_DIR/Blink.entitlements.plist" >/dev/null 2>&1; then
  echo 'managed web-browser entitlement must be absent' >&2
  exit 1
fi
APS=$(/usr/libexec/PlistBuddy -c 'Print :aps-environment' "$REPORT_DIR/Blink.entitlements.plist" 2>/dev/null || true)
if [ "$APS" != "production" ]; then
  echo "expected production aps-environment for ad-hoc IPA, got '$APS'" >&2
  exit 1
fi
for bundle in "$APP" "$APP"/PlugIns/*.appex; do
  [ -d "$bundle" ] || continue
  if [ -f "$bundle/embedded.mobileprovision" ]; then
    security cms -D -i "$bundle/embedded.mobileprovision" > "$REPORT_DIR/$(basename "$bundle").mobileprovision.plist"
  fi
done
find "$WORK/Payload" -maxdepth 4 -type d -name '*.app' -o -name '*.appex' > "$REPORT_DIR/bundles.txt"
unzip -l "$IPA" > "$REPORT_DIR/ipa-listing.txt"
echo "Verified $IPA"
