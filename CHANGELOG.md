# Changelog

All notable changes to this project are documented here.

The format follows Keep a Changelog, and the project intends to use semantic versioning once it reaches a supported release.

## Unreleased

### Added

- **Provenance ledger** (`job_events` table): every job transition (`inspected`,
  `migrated`, `failed`, `rolled_back`) is recorded as an immutable, append-only
  row with SHA-256 input/output hashes, tool version, actor, and a
  `prev_event_id` chain link for tamper detection.
- **Artifact manifest** (`v{N}/manifest.json`): written to disk after every
  migration, capturing the artifact's SHA-256 byte hash and the full event chain
  up to that point, forming a tamper-evident provenance record.
- **`rollback_job`** in `persistence/repositories.py`: copies the artifact from
  a chosen manifest version into a new `v{N+1}` slot, resets the job row to
  `status='inspected'`, appends a `rolled_back` ledger event, writes a new
  manifest, and returns the restored job dict. No history is deleted.
- **`ledger` CLI command**: prints the full event table for a job
  (`event_id`, `event`, `step`, `actor`, `recorded_at`, `output_hash[:16]`).
  Accepts `--owner` and `--log-level`. Exits with code 1 on access errors.
- **`rollback` CLI command**: invokes `rollback_job` and prints the restored
  job's status and manifest path. Accepts `--version`, `--owner`, `--log-level`.
- **Ledger section in HTML/JSON reports**: `build_report_data`,
  `render_json_report`, and `render_html_report` now accept an optional
  `ledger_entries` parameter. The HTML report gains a "Ledger History" table
  after "Integrity Checks"; all values are HTML-escaped. Existing callers
  are unaffected (default `None` → empty list).
- **`get_job_events`** / **`purge_ledger_entries_before`** in
  `persistence/repositories.py`: retrieve ledger rows (owner-scoped) and
  bulk-delete rows older than a cutoff timestamp for data-retention maintenance.
- `LedgerRollbackError` in `core/errors.py` for manifest-not-found and
  missing-artifact conditions.
- `tool_version()` helper in `core/identity.py` to stamp ledger events with
  the installed package version.
- 17 unit tests in `tests/unit/test_ledger.py` covering AC-1 through AC-14,
  including HTML rendering, XSS-escape verification, PII exclusion, tamper
  detection, and rollback owner scoping.
- **Accessibility check for images** (`core/quality.py`): every HTML
  page of the canonical course is scanned for `<img>` tags without a
  meaningful alt text (no `alt` attribute, or only a file name such as
  `chart.png`). Works for Open edX and Moodle courses; intentionally empty
  `alt=""` (decorative images) is not flagged.
- **Accessibility finding format** (`Finding` in `core/quality.py`): each
  finding has `code`, `severity`, `message`, `source_object` (kind and ID of
  the affected course component) and `recommendation`, as agreed in the
  team document. `run_quality_checks` collects all checks.
- **Accessibility section in HTML/JSON reports**: `build_report_data` adds an
  `"accessibility"` block with a summary by severity and all findings; the
  HTML report gains an "Accessibility & Content Quality" table after
  "Validation Warnings & Errors". Findings no longer appear in the
  validation list (`core/validate.py` is unchanged from upstream).
- Test courses `a11y_openedx_archive` and `a11y_moodle_archive` in
  `tests/conftest.py`, plus unit tests for the check, the finding ID and
  the report section, and 1 integration test.
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

### Changed

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

### Removed

- Generated Open edX exports from version control.
- Unused placeholder modules and the hello-world entry point.
