# rustCad releases

rustCad uses its own version and `rustcad-v*` tags. FreeCAD's internal version,
the Rust crate version, JSON protocol version and document schema remain separate.
The first product release is `rustcad-v0.1.0-alpha.1`. During alpha, qualifying
features, fixes and breaking changes advance the alpha counter. Promotion to
0.1.0 requires a reviewed policy change; after promotion, fixes increment patch
and features/breaking changes increment minor while the product is below 1.0.

Use Conventional Commit PR titles and squash merges. Release Please maintains
`rustcad-version.txt`, `.release-please-manifest.json` and `RUSTCAD_CHANGELOG.md`.
The bootstrap commit is the original fork baseline `f69b1eb064874749739b87bf3d951985ce51bfe3`.
It excludes inherited FreeCAD history and remains an ancestor after a squash merge;
an unmerged local upstream commit would not provide that guarantee.
No build edits or commits version files.

## One-time GitHub App setup

Register a dedicated App in [Yis-company's App settings](https://github.com/organizations/Yis-company/settings/apps/new):

- Name: a unique rustCad release name, for example `Yis rustCad releases`.
- Homepage: `https://github.com/Yis-company/rustCad`.
- Disable the webhook; leave callback/redirect URLs empty. No event subscriptions
  or user authorization are needed.
- Repository permissions: **Contents: read/write**, **Pull requests: read/write**,
  **Issues: read/write**. Metadata read access is automatic. No organization,
  administration, workflow, secret, or Actions write permissions.
- Install only on this account, selecting **rustCad only**.
- Generate one private key. Set repository variable `RUSTCAD_RELEASE_APP_ID` to
  the numeric App ID. Store the PEM as repository secret
  `RUSTCAD_RELEASE_APP_PRIVATE_KEY` through secure secret input or GitHub's secret
  settings. Never put the key in a PR, command argument, source file or chat.

The workflow mints a short-lived token restricted to rustCad. Only the trusted
main release job receives it. PR/build/package-test jobs use read-only access.
Unrelated installed Apps are not reused. There is no fallback to a personal token
or the default token when the release App is missing.

Enable Actions to create PRs. Once the implementation workflow has run, require
the **RustCad required** and **Conventional PR title** checks on main and require PRs before merging, with zero
additional reviewer approvals, no force pushes or deletion. Protect `rustcad-v*`
tags against updates/deletion without a normal automation bypass. Verify the
actual check name and settings through the API before calling this enforced.
Yi merges implementation and release PRs; the automation never merges them.

## CI and publication

Every main-targeting PR runs the release policy tests, Rust corpus and native
regressions, plus the Linux GUI build and package checks. The required aggregate
fails on failed, cancelled or unexpectedly skipped jobs; there are no path filters.
Existing FreeCAD CI remains enabled.
Title validation also runs on metadata edits in a separate cheap workflow, so
editing a PR description cannot restart or cancel an application build. Dependency
Graph must be enabled for the inherited dependency-review check; Dependabot alerts
enable that graph without enabling automatic dependency updates.

The reusable Linux path runs on standard `ubuntu-24.04` runners. It builds with
locked Pixi dependencies, the pinned Rust toolchain and `BUILD_RUSTCAD=ON`.
Two compile jobs and one link job limit memory use. AppImage packaging uses
appimagetool 1.9.1 and type2-runtime 20251108, with no upstream update URL.
Only disposable staging is pruned. No source checkout or host tools are wiped.

A **fresh runner** downloads the package and extracts it without FUSE. No Pixi
environment or compiled source build exists there. It runs the packaged GUI under
Xvfb with Cargo/Rustup absent from PATH and verifies module/library origins,
creation/editing/placement, undo/redo, persistence, rendering, failure recovery,
legacy Part operation and independently validated raw STEP exports.

After Yi merges a release PR, Release Please creates an immediate lightweight tag
and a draft prerelease. The same Linux path builds that **exact SHA**, even if main
advances. A separate publisher checks all gates, tag/version/package identity and
clean source, uploads the tested bytes without replacement, then publishes the
draft as a prerelease. It does not rebuild or mark the alpha as latest.

Each AppImage includes FreeCAD attribution, installed dependency notices, a package
list and build identity. `rustcad-evidence.json` beside the AppImage records the
source SHA, native revision, separate compatibility/schema versions and package
test result. Development packages use `dev-<commit>-<run>` identities and cannot
be published by this release path.

Full logs and timing/disk samples remain in `build/evidence/`; CI retains evidence
for seven days and package-transfer artifacts for one day. These use Actions
artifact storage; free public runner time does not promise unlimited storage.
Runner capacity is verified by hosted runs, not inferred from a local build. If
the standard runner runs out of resources, retain its failure and review the
resource plan rather than silently buying a larger runner or dropping checks.

## Retry and rollback

Use **RustCad release → Run workflow**, supplying an existing unpublished
`rustcad-v0.x.y-alpha.N` tag. The workflow verifies the tag belongs to main and
matches the committed version file, then reruns the exact source through all gates.

Published releases cannot be retried or overwritten. Partial uploads resume only
when existing asset bytes exactly match the tested files. Different bytes,
unexpected assets, changed tags and failed checks leave the draft unpublished.
A source fix gets a new version; never move or reuse the old tag. If a rebuilt
package differs from a partial upload, stop and report the collision rather than
delete or replace the earlier asset.

Disable only the RustCad release workflow or revoke its App access if publication
malfunctions. Preserve tags and evidence. Revert automation through a normal PR,
retaining Rust features and unrelated CI. Windows/macOS, signing, drawing parity
and further kernel migration remain separate milestones.

The first publication is unproven until Yi merges its release PR and the exact-tag
package gates pass. A local pass or implementation PR is not a release.
