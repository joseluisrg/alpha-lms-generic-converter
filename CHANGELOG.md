# Changelog

All notable changes to this project are documented here.

The format follows Keep a Changelog, and the project intends to use semantic versioning once it reaches a supported release.

## Unreleased

### Added

- Database schema versioning via `PRAGMA user_version`, one-time startup migrations for legacy databases, and repository reads that no longer execute DDL.
- Configurable retention cleanup for expired job rows, extracted paths, outputs, and upload sessions, with dry-run support and a `cleanup` CLI command.
- Golden migration corpus with synthetic Open edX and Moodle source trees, canonical IR/report/export snapshots, frozen binary contracts, malformed and malicious inputs, feature-coverage enforcement, fixture hygiene checks, and `scripts/update_golden.py`.
- Stable source question identifiers for Open edX and Moodle questions, removing random UUIDs from parser output.
- Hardened multi-stage container image with a digest-pinned Python base, hash-locked runtime dependencies, non-root execution, root-owned application files, a health check, and production fail-closed defaults.
- Hardened `compose.yaml` with a read-only root filesystem, writable data volume and `/tmp`, dropped capabilities, `no-new-privileges`, PID/memory/CPU limits, log rotation, and loopback-only port binding.
- CycloneDX SBOM generation and validation through `scripts/generate_sbom.py` and `scripts/validate_sbom.py`, published as a CI artifact and attached to releases.
- Container build, non-root, CLI smoke, and web health checks in CI.
- Deployment guide covering Compose, reverse-proxy authentication, CLI usage, hardening controls, upgrades, and supply-chain checks.
- Architecture reference covering runtime components, the processing pipeline, module boundaries, data ownership, and trust boundaries.
- Operator runbook covering health checks, upgrade and rollback, stopped-snapshot backup, restore verification, retention cleanup, incident triage, support handoff, and a recovery drill.
- Backup and restore integration drill that snapshots the managed data root, restores it, and verifies jobs, artifacts, schema version, and SQLite integrity.
- Versioned format and feature matrix covering every supported feature ID, with target status, import checks, fixture evidence, and certification gaps.
- Certification harness scaffold with a versioned result contract, matrix-driven import planning, golden artifact generation, credential redaction, fake-target runner tests, and a dry-run CLI.
- Real Moodle 5.3.1 and Open edX Verawood.2/Tutor 22.0.4 certification targets with pinned Docker environments, import and re-export commands, manifest/static evidence collection, and feature verifiers.
- Nightly and manually dispatched LMS certification workflow with disk guards, checksum-verified Moodle download, separate target jobs, and uploaded reports/logs.
- Certification schema version 2 with re-export artifact hashes, sizes, commands, exit codes, durations, and log references.
- Certification guide covering local runs, workflow dispatch, pass criteria, evidence, troubleshooting, and known limitations.
- Machine-readable certification scorecard recording 39 verified features, 33 transformed plus 6 native, 18 expected gaps, and the two consecutive green `all` runs.

### Changed

- Recorded Moodle 5.3 LTS and Open edX Verawood as the certification targets, with pinned patch expectations for the LMS import harness.
- Updated the optional UI stack to Streamlit 1.67 and patched transitive dependencies; `pip-audit` is clean.
- Open edX exports use a stable identifier for synthetic open-assessment prompt HTML, removing a source of nondeterminism.
- Open edX numerical problems emit Moodle tolerances as OLX response parameters.
- Moodle backups declare Moodle 5.3.1 metadata and link SCORM packages with the activity instance identifier.
- Moodle SCORM parsing resolves packages through `inforef.xml` file records as well as legacy package files.
- Open edX exports now emit the Tutor-default `scorm` XBlock with inline package metadata and `scorm/<url_name>/package.zip`, and the Open edX parser reads that format while retaining legacy `scormxblock` support.
- Golden SCORM fixtures now contain valid deterministic SCORM 1.2 manifests and launch pages.

### Fixed

- Open edX HTML wrappers that omit the `.html` suffix now resolve the payload file, preserving external URL and fallback content through re-export.
- Open edX SCORM components now keep package metadata inline and import through the target-aware course key, so package storage survives import and re-export.
- Two consecutive live `all` certification runs now pass against Moodle 5.3.1 and Open edX Verawood.2, verifying 17/23 and 22/34 features respectively.

## [0.1.0a1] - 2026-11-18

### Added

- Apache-2.0 license.
- Central environment-driven configuration for paths, upload limits, archive limits, XML limits, environment, and auth mode.
- Installable wheel with all adapter, CLI, core, domain, and persistence packages.
- Optional `ui` extra for Streamlit and a `--version` CLI flag.
- Bounded, chunked upload staging with SHA-256 integrity metadata and TTL cleanup.
- Production authentication gate that fails closed unless a trusted proxy identity is present.
- Owner-scoped job access for the web UI, preventing cross-user job retrieval.
- Server-owned output path resolution for web-facing migrations.
- Deterministic canonical identifiers derived from stable source keys.
- Archive extraction limits and path-containment checks, including duplicate and device entries.
- Defused XML parsing with configurable size and nesting limits.
- Typed application and security errors.
- Escaped, shared HTML report rendering.
- SQLite job lifecycle fields and failed-job recording.
- Tests for archive/XML hardening, uploads, output containment, authentication, job ownership, fidelity regressions, report escaping, and persistence.
- Integration tests for ingest and migration services, CLI end-to-end coverage, Streamlit smoke checks, and legacy schema migration coverage.
- CI workflow running lint, format, type checks, tests with a coverage policy, security scans, dependency audit, and a build/install smoke test on Python 3.12 and 3.13.
- Developer quality tooling: `ruff` lint/format, `mypy` type checks, `bandit` security scans, `pip-audit` dependency audits, and a coverage floor enforced at 80%.
- `scripts/ci_smoke.py`, which exercises a clean wheel install through inspect, migrate, and report on a generated fixture.
- Tag-driven release workflow that validates the tag against the project version and changelog, repeats the quality gates, builds and smoke-tests the wheel and source distribution, publishes checksums and a GitHub Release, and retains CI build artifacts.
- `scripts/check_release.py` for release metadata validation and changelog notes extraction, with a release checklist in `docs/RELEASING.md`.

### Changed

- Moodle file content hashes are computed with `usedforsecurity=False` because SHA-1 is required by the Moodle backup format for addressing, not for security.
- ZIP archives are now extracted member by member after validation so only individually verified entries are written.
- Target adapters narrow optional internal state through explicit accessors, and optional variables are typed throughout, making the package pass `mypy` with `check_untyped_defs`.

- Moodle backup generation now uses restore-shaped course, section, activity, question, file, and auxiliary XML.
- Open edX export now uses valid OLX problem and SCORM structures, course-scoped policies, and asset manifests.
- Moodle file records now use correct component, file area, and item identifiers.
- Migration jobs preserve existing inspection reports when no new report is supplied.
- Streamlit report rendering delegates to the shared escaped renderer and no longer displays a raw HTML preview.
- Streamlit errors are logged server-side and shown to users as sanitized messages.
- `docs/production-readiness-plan.md` now uses a controlled project-plan structure with scope, WBS, milestones, RACI, RAID, release gates, and a decision log.

### Fixed

- Stale extraction directories could reuse an old `course.xml`.
- Moodle page bodies could be duplicated during round trips.
- True/false answers were mapped by position instead of text.
- Duplicate question identifiers could be emitted across assessments.
- Open edX nested asset paths were flattened.
- Reused target adapters could leak state between exports.
- The web uploader now accepts Open edX `.tar.gz` and `.tgz` exports; browsers cannot filter on compound extensions, so the picker previously offered only `.mbz`.
- The CI workflow pins `astral-sh/setup-uv` to a published tag (`v10.3.3`) so jobs can resolve the action.

### Removed

- Generated Open edX exports from version control.
- Unused placeholder modules and the hello-world entry point.
