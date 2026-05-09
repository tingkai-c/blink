# Project Agent Instructions

## Build and verification policy

- Do **not** run local Xcode builds for this project.
- Do **not** run local framework/bootstrap build commands such as `get_frameworks.sh` for build verification unless the user explicitly asks.
- Always use the GitHub Actions CI workflow to build signed IPA artifacts and verify build success.
- Local commands are OK for lightweight static checks, grep, plist validation, package metadata inspection, and non-build script syntax checks.
- For device verification, download the successful GitHub Actions artifact, install it with the repo install script or `devicectl`, then launch/check crash reports locally.
