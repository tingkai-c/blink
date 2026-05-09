#!/usr/bin/env python3
import base64
import os
import plistlib
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path.cwd()
BUILD = ROOT / "build"
CI = BUILD / "ci"
CI.mkdir(parents=True, exist_ok=True)
PROFILE_DIR = Path.home() / "Library/MobileDevice/Provisioning Profiles"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

EXPORT_METHOD = os.environ.get("EXPORT_METHOD", "ad-hoc")
TEAM_ID = os.environ["APPLE_TEAM_ID"]
BUNDLE_ID = os.environ["IOS_BUNDLE_ID"]
GROUP_ID = os.environ["IOS_GROUP_ID"]
CLOUD_ID = os.environ["IOS_CLOUD_ID"]
KEYCHAIN_ID1 = os.environ["IOS_KEYCHAIN_ID1"]
TARGET_DEVICE_UDID = os.environ.get("TARGET_DEVICE_UDID", "")


def require_secret(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"missing required secret: {name}")
    return value


def decode_b64_env(name: str, path: Path) -> None:
    path.write_bytes(base64.b64decode(require_secret(name)))
    os.chmod(path, 0o600)


def run(args, **kwargs):
    print("+", " ".join(str(a) for a in args))
    return subprocess.run(args, check=True, text=True, **kwargs)


def decode_profile(env_name: str) -> tuple[Path, dict]:
    raw_path = CI / f"{env_name}.mobileprovision"
    decode_b64_env(env_name, raw_path)
    plist_path = CI / f"{env_name}.plist"
    with plist_path.open("wb") as out:
        subprocess.run(["security", "cms", "-D", "-i", str(raw_path)], check=True, stdout=out)
    profile = plistlib.loads(plist_path.read_bytes())
    uuid = profile["UUID"]
    install_path = PROFILE_DIR / f"{uuid}.mobileprovision"
    shutil.copy2(raw_path, install_path)
    os.chmod(install_path, 0o600)
    return install_path, profile


cert_path = CI / "signing_certificate.p12"
decode_b64_env("SIGNING_CERTIFICATE_BASE64", cert_path)
keychain_path = Path(os.environ["RUNNER_TEMP"]) / "blink-signing.keychain-db"
keychain_password = require_secret("KEYCHAIN_PASSWORD")
run(["security", "create-keychain", "-p", keychain_password, str(keychain_path)])
run(["security", "set-keychain-settings", "-lut", "21600", str(keychain_path)])
run(["security", "unlock-keychain", "-p", keychain_password, str(keychain_path)])
run(["security", "import", str(cert_path), "-P", require_secret("SIGNING_CERTIFICATE_PASSWORD"), "-A", "-t", "cert", "-f", "pkcs12", "-k", str(keychain_path)])
run(["security", "list-keychain", "-d", "user", "-s", str(keychain_path), str(Path.home() / "Library/Keychains/login.keychain-db")])
run(["security", "set-key-partition-list", "-S", "apple-tool:,apple:,codesign:", "-s", "-k", keychain_password, str(keychain_path)])
run(["security", "find-identity", "-v", "-p", "codesigning", str(keychain_path)])

profiles = {
    BUNDLE_ID: decode_profile("PROFILE_APP_BASE64"),
    f"{BUNDLE_ID}.BlinkFileProviderExtension": decode_profile("PROFILE_FILE_PROVIDER_BASE64"),
    f"{BUNDLE_ID}.BlinkFileProviderExtensionUI": decode_profile("PROFILE_FILE_PROVIDER_UI_BASE64"),
}


def profile_entitlements(bundle: str) -> dict:
    return profiles[bundle][1].get("Entitlements", {})


def validate_profile(bundle: str) -> str:
    _, profile = profiles[bundle]
    ent = profile.get("Entitlements", {})
    app_id = ent.get("application-identifier", "")
    if not app_id.endswith("." + bundle):
        raise SystemExit(f"profile {profile.get('Name')} does not match bundle {bundle}: {app_id}")
    teams = profile.get("TeamIdentifier", [])
    if TEAM_ID not in teams:
        raise SystemExit(f"profile {profile.get('Name')} does not contain team {TEAM_ID}: {teams}")
    if TARGET_DEVICE_UDID and TARGET_DEVICE_UDID not in profile.get("ProvisionedDevices", []):
        raise SystemExit(f"profile {profile.get('Name')} does not contain device {TARGET_DEVICE_UDID}")
    return profile["Name"]

profile_names = {bundle: validate_profile(bundle) for bundle in profiles}

# developer_setup.xcconfig mirrors template variables used by the project.
(ROOT / "developer_setup.xcconfig").write_text(
    "\n".join([
        f"TEAM_ID = {TEAM_ID}",
        f"BUNDLE_ID = {BUNDLE_ID}",
        f"GROUP_ID = {GROUP_ID}",
        f"CLOUD_ID = {CLOUD_ID}",
        f"KEYCHAIN_ID1 = {KEYCHAIN_ID1}",
        "SWIFT_ACTIVE_COMPILATION_CONDITIONS[config=Debug] = BLINK_PUBLISHING_OPTION_DEVELOPER",
        "SWIFT_ACTIVE_COMPILATION_CONDITIONS[config=Release] = BLINK_PUBLISHING_OPTION_TESTFLIGHT",
        "BLINK_MIGRATION_SCHEME = blinkv15",
        "WHATS_NEW_URL = http:/$()/localhost/whats-new",
        "CONVERSION_OPPORTUNITY_URL = http:/$()/localhost/conversionOpportunity",
        "WHATS_NEW_GITHUB_URL = http:/$()/localhost/conversionOpportunity",
        "BLINK_APP_FONT = JetBrains Mono",
        "",
    ]),
    encoding="utf-8",
)


def prune_entitlements(source: Path, dest: Path, bundle: str, main: bool) -> None:
    ent = plistlib.loads(source.read_bytes())
    allowed = profile_entitlements(bundle)
    ent.pop("com.apple.developer.web-browser", None)
    if allowed.get("aps-environment"):
        ent["aps-environment"] = allowed["aps-environment"]
    else:
        ent.pop("aps-environment", None)
    if not allowed.get("com.apple.security.application-groups"):
        ent.pop("com.apple.security.application-groups", None)
    if not allowed.get("com.apple.developer.icloud-container-identifiers"):
        for key in [
            "com.apple.developer.icloud-container-identifiers",
            "com.apple.developer.icloud-container-development-container-identifiers",
            "com.apple.developer.icloud-services",
            "com.apple.developer.ubiquity-container-identifiers",
            "com.apple.developer.ubiquity-kvstore-identifier",
        ]:
            ent.pop(key, None)
    if not allowed.get("com.apple.developer.user-fonts"):
        ent.pop("com.apple.developer.user-fonts", None)
    # These sandbox-style macOS entitlements are not provisioning-profile controlled for iOS sideload.
    # Keep application-groups when a provisioning profile actually grants it; iOS uses this
    # entitlement for App Group containers shared with extensions.
    for key in list(ent):
        if key.startswith("com.apple.security.") and key != "com.apple.security.application-groups":
            ent.pop(key, None)
    # Data protection is omitted for the CI sideload profile unless Apple embeds it in the profile.
    if "com.apple.developer.default-data-protection" not in allowed:
        ent.pop("com.apple.developer.default-data-protection", None)
    dest.write_bytes(plistlib.dumps(ent, sort_keys=False))

main_entitlements = CI / "Blink.entitlements"
ext_entitlements = CI / "BlinkFileProviderExtension.entitlements"
prune_entitlements(ROOT / "Blink/Blink.entitlements", main_entitlements, BUNDLE_ID, True)
prune_entitlements(ROOT / "BlinkFileProviderExtension/BlinkFileProviderExtension.entitlements", ext_entitlements, f"{BUNDLE_ID}.BlinkFileProviderExtension", False)

info = plistlib.loads((ROOT / "Blink/Info.plist").read_bytes())
containers = info.get("NSUbiquitousContainers")
if isinstance(containers, dict):
    value = next(iter(containers.values()), {}) if containers else {}
    info["NSUbiquitousContainers"] = {f"iCloud.{CLOUD_ID}": value}
ci_info = CI / "Blink-Info.plist"
ci_info.write_bytes(plistlib.dumps(info, sort_keys=False))

export_options = {
    "method": EXPORT_METHOD,
    "teamID": TEAM_ID,
    "signingStyle": "manual",
    "stripSwiftSymbols": True,
    "compileBitcode": False,
    "provisioningProfiles": profile_names,
}
(CI / "ExportOptions.plist").write_bytes(plistlib.dumps(export_options, sort_keys=False))
redacted = dict(export_options)
redacted["provisioningProfiles"] = {k: "<redacted>" for k in profile_names}
(CI / "ExportOptions.redacted.plist").write_bytes(plistlib.dumps(redacted, sort_keys=False))

pbx_path = ROOT / "Blink.xcodeproj/project.pbxproj"
pbx = pbx_path.read_text(encoding="utf-8")

def find_pbx_object_end(text: str, start: int) -> int:
    """Return the index after the semicolon ending a pbxproj object."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                semicolon = text.index(";", index)
                return semicolon + 1
    raise SystemExit("could not find end of pbxproj object")

def patch_config(text: str, uuid: str, settings: dict[str, str | None]) -> str:
    marker = f"\t\t{uuid} /* Release */ = {{"
    start = text.index(marker)
    end = find_pbx_object_end(text, start)
    block = text[start:end]
    setting_line_prefix = "\n\t\t\t\t"
    for key, value in settings.items():
        quoted_key = re.escape(key)
        line_key = key if re.match(r"^[A-Za-z0-9_]+$", key) else f'"{key}"'
        if value is None:
            block = re.sub(rf"{setting_line_prefix}{quoted_key} = .*?;", "", block)
            block = re.sub(rf"{setting_line_prefix}\"{quoted_key}\" = .*?;", "", block)
            continue
        new_line = f"{setting_line_prefix}{line_key} = {value};"
        pattern = rf"{setting_line_prefix}(?:{quoted_key}|\"{quoted_key}\") = .*?;"
        if re.search(pattern, block):
            block = re.sub(pattern, new_line, block)
        else:
            insert = block.index("\n\t\t\t};")
            block = block[:insert] + new_line + block[insert:]
    return text[:start] + block + text[end:]

common = {
    "CODE_SIGN_STYLE": "Manual",
    "DEVELOPMENT_TEAM": TEAM_ID,
    "CODE_SIGN_IDENTITY": '"Apple Distribution"' if EXPORT_METHOD == "ad-hoc" else '"Apple Development"',
    "CODE_SIGN_IDENTITY[sdk=iphoneos*]": '"Apple Distribution"' if EXPORT_METHOD == "ad-hoc" else '"Apple Development"',
}

release_config_uuids = re.findall(r"\t\t([A-F0-9]{24}) /\* Release \*/ = \{", pbx)
for uuid in release_config_uuids:
    pbx = patch_config(pbx, uuid, common)

pbx = patch_config(pbx, "EA0BA1AF1C0CC57C00719C1A", {
    "CODE_SIGN_ENTITLEMENTS": str(main_entitlements.relative_to(ROOT)),
    "INFOPLIST_FILE": str(ci_info.relative_to(ROOT)),
    "PROVISIONING_PROFILE_SPECIFIER": f'"{profile_names[BUNDLE_ID]}"',
})
pbx = patch_config(pbx, "98271271262E4BDB00F883FA", {
    "CODE_SIGN_ENTITLEMENTS": str(ext_entitlements.relative_to(ROOT)),
    "PROVISIONING_PROFILE_SPECIFIER": f'"{profile_names[f"{BUNDLE_ID}.BlinkFileProviderExtension"]}"',
})
pbx = patch_config(pbx, "BD9EA1D62718E19000874007", {
    "CODE_SIGN_ENTITLEMENTS": None,
    "PROVISIONING_PROFILE_SPECIFIER": f'"{profile_names[f"{BUNDLE_ID}.BlinkFileProviderExtensionUI"]}"',
})
pbx_path.write_text(pbx, encoding="utf-8")

print("Prepared signing assets for:")
for bundle, name in profile_names.items():
    print(f"- {bundle}: {name}")
