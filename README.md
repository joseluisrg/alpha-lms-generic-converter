# LMS Converter

Vendor-neutral course migration between Moodle and Open edX.

LMS Converter parses course packages, maps them to a canonical course model, validates migration readiness, and generates restore-shaped Moodle backups or Open edX exports. Every migration produces a report describing what was preserved, what changed, and what needs human review.

> Status: alpha. The conversion pipeline is usable and deployment operations are documented, but real-LMS certification, the format matrix, and pilot sign-off are still in progress. See [`docs/production-readiness-plan.md`](docs/production-readiness-plan.md).

## Features

- Moodle `.mbz` and Open edX `.tar.gz` inspection.
- Canonical, deterministic course model.
- Moodle to Open edX and Open edX to Moodle conversion.
- Archive, path, and XML input hardening.
- HTML and JSON migration reports.
- SQLite job history with lifecycle states.
- Configurable retention cleanup for jobs and artifacts.
- Optional Streamlit UI.

## Architecture and operations

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): runtime components, pipeline, module map, trust boundaries, and extension points.
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): hardened container deployment, proxy authentication, upgrades, and SBOM checks.
- [`docs/OPERATOR_RUNBOOK.md`](docs/OPERATOR_RUNBOOK.md): health checks, backup, restore, rollback, retention, troubleshooting, and the recovery drill.

## Requirements

- Python 3.12 or newer.
- [uv](https://docs.astral.sh/uv/) for development and reproducible installs.
- Docker with Compose v2 for container deployment.

## Install

```bash
git clone https://github.com/olgakazarina-guds/Team-Delta.git
cd Team-Delta
uv sync
```

Install the optional Streamlit UI:

```bash
uv sync --extra ui
```

Install development tools:

```bash
uv sync --group dev
```

## CLI

```bash
uv run lms-converter --help
uv run lms-converter --version

uv run lms-converter inspect course.mbz --source moodle --report
uv run lms-converter inspect course.tar.gz --source openedx --validate-for moodle

uv run lms-converter migrate course.mbz --target openedx --output course.tar.gz
uv run lms-converter migrate course.tar.gz --target moodle --output course.mbz

uv run lms-converter report <job-id> --format html --output report.html

uv run lms-converter cleanup --dry-run
uv run lms-converter cleanup --apply --retention-days 7
```

## Streamlit UI

```bash
uv run --extra ui streamlit run streamlit_app.py
```

## Container

The hardened image runs the Streamlit UI as a non-root user with a read-only
source tree and a single writable data volume:

```bash
docker build --pull -t lms-converter:0.1.0a1 .
docker run --rm \
  -p 127.0.0.1:8501:8501 \
  -e LMS_CONVERTER_ENV=development \
  -e LMS_CONVERTER_AUTH_MODE=none \
  -v lms-data:/app/data \
  lms-converter:0.1.0a1
```

Development mode has no authentication and must remain bound to localhost. For
production, use `compose.yaml` behind an authenticating reverse proxy. See
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for production settings, CLI usage,
resource limits, upgrades, and SBOM generation, and
[`docs/OPERATOR_RUNBOOK.md`](docs/OPERATOR_RUNBOOK.md) for backup, restore, and
rollback procedures.

## Configuration

All runtime paths and limits are controlled by environment variables. By default, data lives in the platform application data directory (for example `~/.local/share/lms-converter` on Linux), not in the repository.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LMS_CONVERTER_DATA_DIR` | platform data dir | Root for all runtime data |
| `LMS_CONVERTER_DB_PATH` | `<data>/lms_converter.db` | SQLite job database |
| `LMS_CONVERTER_OUTPUT_DIR` | `<data>/output` | Default migration output |
| `LMS_CONVERTER_WORK_DIR` | `<data>/work` | Per-job extraction and build directories |
| `LMS_CONVERTER_UPLOAD_DIR` | `<data>/uploads` | UI upload staging |
| `LMS_CONVERTER_REPORT_DIR` | `<data>/reports` | Generated migration reports |
| `LMS_CONVERTER_MAX_UPLOAD_BYTES` | `536870912` | UI upload limit |
| `LMS_CONVERTER_MAX_EXTRACT_BYTES` | `2147483648` | Archive expansion budget |
| `LMS_CONVERTER_MAX_EXTRACT_MEMBER_BYTES` | `536870912` | Single archive member limit |
| `LMS_CONVERTER_MAX_EXTRACT_MEMBERS` | `50000` | Archive entry limit |
| `LMS_CONVERTER_MAX_COMPRESSION_RATIO` | `250` | Decompression-bomb guard |
| `LMS_CONVERTER_MAX_XML_BYTES` | `67108864` | XML document limit |
| `LMS_CONVERTER_MAX_XML_DEPTH` | `256` | XML nesting limit |
| `LMS_CONVERTER_UPLOAD_TTL_SECONDS` | `86400` | Upload staging retention |
| `LMS_CONVERTER_RETENTION_DAYS` | `30` | Job and artifact retention period |
| `LMS_CONVERTER_ENV` | `development` | Runtime environment |
| `LMS_CONVERTER_AUTH_MODE` | `none` | `none` or trusted `proxy` identity |
| `LMS_CONVERTER_TRUSTED_USER_HEADER` | `X-Forwarded-User` | Proxy identity header |
| `LMS_CONVERTER_LOG_LEVEL` | `INFO` | Default log level |

`lms-converter cleanup` previews expired data by default. Pass `--apply` to remove job rows older than the retention period, extracted directories and outputs under the managed data roots, and stale upload sessions. Outputs written outside the managed roots are left in place.

## Security

- In development, the UI uses the local identity.
- In production, set `LMS_CONVERTER_ENV=production` and terminate authentication in a trusted reverse proxy. Configure `LMS_CONVERTER_AUTH_MODE=proxy` and the identity header; the UI fails closed when no identity is present.
- Do not expose Streamlit directly to the internet.
- UI jobs are scoped to the authenticated identity, so one user cannot open another user's job by ID.
- Uploads and migration outputs are written only under the configured server-owned directories.
- Retention cleanup removes expired jobs and server-owned artifacts; external CLI output paths are never deleted.

For local development with repository-local data:

```bash
LMS_CONVERTER_DATA_DIR=./data uv run lms-converter inspect course.mbz
```

## Development

```bash
uv run pytest
uv run pytest --cov=core --cov=adapters --cov=persistence --cov=cli
uv build
```

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for contribution guidance and
[`docs/RELEASING.md`](docs/RELEASING.md) for the release checklist.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
