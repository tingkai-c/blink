# OSS/GPL Sideload Fork Notes

This fork builds the signed sideload IPA as an OSS/GPL flavor using
`BLINK_PUBLISHING_OPTION_GPL_SIDELOAD`.

Fork deltas kept intentionally small for upstream merges:

- GPL sideload unlocks the local paywall in `EntitlementsManager` as
  `GPL Sideload Build` / `CustomerTier.Classic`.
- GPL sideload does not activate Plus, early access, Blink Build, or server-backed
  Build account entitlements.
- Blink Build source files remain in the tree for upstream compatibility, but the
  GPL sideload flavor hides its Settings UI, filters the `build` shell command,
  skips Build purchase/restore/token flows, and makes `BuildAPI` fail fast before
  network calls.
- GitHub signed IPA generation writes Release Swift conditions as
  `BLINK_PUBLISHING_OPTION_GPL_SIDELOAD`.

After upstream merges, re-run these checks:

```bash
grep -R "api.blink.build\|raw.api.blink.build" Blink Settings
grep -R "BuildView()\|restoreBlinkBuildEntitlements\|purchaseBuildBasic\|build_main" Blink Settings Resources
grep -R "BLINK_PUBLISHING_OPTION_GPL_SIDELOAD" Blink template_setup.xcconfig .github/scripts
```

Do not re-enable Blink Build in the GPL sideload flavor without an explicit
product decision.
