# Architecture Reference

This document describes the runtime structure, processing pipeline, data
boundaries, and extension points for LMS Converter. It complements the
deployment and operator procedures in
[`DEPLOYMENT.md`](DEPLOYMENT.md) and [`OPERATOR_RUNBOOK.md`](OPERATOR_RUNBOOK.md).

The high-level component diagram is available at
[`System_Architecture.png`](System_Architecture.png).

## System context

LMS Converter is a self-hosted tool for moving course content between Moodle and
Open edX. It reads LMS export packages, normalizes them into a canonical course
model, validates migration readiness, writes a preserved/transformed/lost
report, and generates a target-format package.

The application deliberately uses package exchange rather than direct LMS APIs:

- Inputs are Moodle `.mbz` archives or Open edX `.tar.gz` exports.
- Outputs are restore-shaped Moodle backups or Open edX export archives.
- Reports are available as JSON and HTML.
- The CLI and Streamlit UI share the same core services and persistence layer.

There is no separate REST service, message queue, or database server in the
current architecture. The Streamlit process is the web interface, and SQLite is
the job store.

## Runtime interfaces

| Interface | Entry point | Purpose |
| --- | --- | --- |
| CLI | `cli/main.py` | Scriptable inspect, migrate, report, and cleanup operations |
| Web UI | `streamlit_app.py` | Interactive upload, inspection, migration, and reporting |
| Container | `Dockerfile`, `compose.yaml` | Non-root deployment with a read-only application layer |
| Release tooling | `scripts/check_release.py`, `scripts/generate_sbom.py` | Version checks, artifacts, and SBOMs |

The CLI and UI are separate front ends over the same in-process services. The UI
does not call an internal HTTP API.

## Processing pipeline

1. **Ingest** (`core/ingest.py`, `core/archive_utils.py`): validates the archive
   path, enforces expansion limits, extracts into the configured work directory,
   and records the extraction path.
2. **Parse** (`core/parse.py`, `adapters/openedx/`, `adapters/moodle/`): reads
   source-specific XML and assets into raw fragments.
3. **Transform** (`core/transform.py`): normalizes parsed content into the
   canonical course model in `domain/`.
4. **Validate** (`core/validate.py`): checks structural and migration-readiness
   conditions and produces review notes.
5. **Map and export** (`core/migrate.py`, target adapters): converts the
   canonical model into the requested target format.
6. **Report** (`core/report.py`, `core/process_report.py`): records preserved,
   transformed, and lost content as JSON or escaped HTML.
7. **Persist** (`persistence/repositories.py`): stores job metadata, owner,
   lifecycle state, course snapshot, report, and artifact paths in SQLite.

The canonical model is the stable boundary between source and target adapters.
Adapter-specific XML and packaging rules stay inside `adapters/`; core services
operate on the domain model.

## Module map

| Path | Responsibility |
| --- | --- |
| `cli/` | Typer commands and command-level input/output handling |
| `core/` | Ingest, parse orchestration, transform, validate, migrate, report, retention, auth, and configuration |
| `adapters/` | Moodle and Open edX readers and target writers |
| `domain/` | Canonical course entities, enums, and raw-fragment contracts |
| `persistence/` | SQLite schema, versioned migrations, and job repositories |
| `streamlit_app.py` | Streamlit UI over core services |
| `scripts/` | CI smoke, golden-corpus maintenance, SBOM, and release checks |
| `tests/` | Unit, integration, security, golden-corpus, and deployment tests |

## Data and trust boundaries

### Managed data root

All runtime data is rooted under the configured data directory
(`LMS_CONVERTER_DATA_DIR`, with a platform-specific default). Individual paths
can be overridden:

| Data | Default |
| --- | --- |
| SQLite database | `<data>/lms_converter.db` |
| Migration outputs | `<data>/output` |
| Extraction workspace | `<data>/work` |
| UI upload staging | `<data>/uploads` |
| Generated reports | `<data>/reports` |

The database and managed artifact directories are the primary backup unit. CLI
outputs written outside `LMS_CONVERTER_OUTPUT_DIR` are user-managed and are not
removed by retention cleanup.

### Persistence

SQLite runs in WAL mode with foreign-key enforcement and bounded connection
timeouts. The schema version is stored in `PRAGMA user_version`. Startup runs
only the required migrations, and reads do not execute DDL.

SQLite is a single-writer design intended for the self-hosted pilot. The
Postgres migration path is future work, not part of this release.

### Authentication and ownership

Production web deployments terminate authentication in a trusted reverse proxy
and pass an identity header. The application fails closed when production mode
is configured without a trusted identity. UI jobs are scoped to the
authenticated identity so one user cannot read another user's job by ID.

The application port must not be exposed directly to an untrusted network. The
proxy must overwrite, not append, the identity header.

### Container boundary

The container runs as UID/GID `10001:10001`, with application files owned by
root and a read-only root filesystem under Compose. Only the data volume and a
`/tmp` tmpfs are writable. Capabilities are dropped and
`no-new-privileges` is enabled.

## Reliability and recovery

- **Schema upgrades** are transactional and reject databases newer than the
  supported schema version.
- **Retention cleanup** removes expired job rows and artifacts only under the
  managed work and output roots; external outputs are left in place.
- **Backup and restore** are documented in the operator runbook and exercised by
  `tests/integration/test_backup_restore.py`.
- **Health checks** use the Streamlit `/_stcore/health` endpoint.
- **Release artifacts** include the wheel, source distribution, SBOM, and
  checksums.

## Extension points and non-goals

The canonical model and adapter boundary are the intended extension points for
future formats and LMS targets. Common Cartridge, QTI, direct LMS APIs, a
React UI, and horizontal scaling are outside the current release scope.

The versioned fidelity scorecard and real-LMS import harness are delivered
against the pinned certification targets. See
[`certification-scorecard.json`](certification-scorecard.json) for results and
[`production-readiness-plan.md`](production-readiness-plan.md) for the current
milestone and decision status.
