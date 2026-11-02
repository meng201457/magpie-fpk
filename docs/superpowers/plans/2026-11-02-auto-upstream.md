# Automatic upstream releases

**Goal:** Check upstream stable releases hourly and automatically publish both fnOS packages.

**Architecture:** Extend the existing workflow, using one resolved lock artifact for both builds. Only the release job can write repository contents; commit the lock and tag after both builds pass. Polling is needed because this repository does not control upstream webhooks. Use the existing default token without a PAT.

**Constraints:** Stable X.Y.Z releases only; no downgrade or silent retagging; increment the package patch version on upstream changes; preserve manual pinned builds and tag releases. Failed builds leave the lock unchanged. Missing/incomplete releases are retried. Existing upstream patch guards must still stop incompatible builds.

**Files:** `scripts/check_upstream.py`, `tests/test_check_upstream.py`, `.github/workflows/build.yml`, `README.md`.

- [x] Add behavioral tests for new/unchanged/older/prerelease/retagged versions and incomplete-release recovery; observe failure, then implement the resolver.
- [x] Extend workflow with hourly polling, opt-in manual sync, shared resolved-lock artifact, serialized runs, and post-build commit/tag/release.
- [x] Document automatic operation and permissions; run unit tests, Python compilation, workflow validation, and inspect the final diff.

**Review focus:** API errors fail visibly; tag SHA is resolved instead of using target branch; version ordering is numeric; releases missing either architecture retry; branch changes during build fail a fast-forward push rather than overwriting newer commits.

**Review fix:** When retrying a version whose tag already exists, resolve that tag's commit and build its packaging source, rather than newer main code. Resolver tests run from the workflow event checkout, so older release tags do not need to contain the new tests.

**Validation:** 11 unit tests, Python compilation, actionlint 1.7.12 (shellcheck/pyflakes disabled), and git whitespace checks. Real API smoke test was blocked by GitHub's unauthenticated 403 rate limit; authenticated CI build/publish remains to be run after pushing. Windows sandbox tests use workspace `.cache` for TEMP/TMP.
