# LMS Converter

Vendor-neutral course migration between Moodle and Open edX.

LMS Converter parses course packages, maps them to a canonical course model, validates migration readiness, and generates restore-shaped Moodle backups or Open edX exports. Every migration produces a report describing what was preserved, what changed, and what needs human review.

> Status: alpha. The conversion pipeline is usable, but real-LMS certification and production hardening are still in progress. See [`docs/production-readiness-plan.md`](docs/production-readiness-plan.md).

# Feature addition ledger-rollback
This branch we start working on the ledger-rollback feature.

## Features

- Moodle `.mbz` and Open edX `.tar.gz` inspection.
- Canonical, deterministic course model.
- Moodle to Open edX and Open edX to Moodle conversion.
- Archive, path, and XML input hardening.
- HTML and JSON migration reports.
- SQLite job history with lifecycle states.
- **Provenance ledger** — every job transition is recorded as an immutable event with a tamper-evident hash chain, so you always know what happened and when.
- **Rollback** — restore a job to any previous artifact version without deleting history.
- **Accessibility check** — flags images without a meaningful alt text (missing, or only a file name) and videos without captions or a transcript (where verifiable) in Open edX and Moodle courses; on request, it also checks whether external links are still reachable. Findings (codes `ALT_ATTRIBUTE_MISSING`, `VIDEO_CAPTIONS_MISSING`, `EXTERNAL_LINK_UNREACHABLE`) appear in their own "Accessibility & Content Quality" section of the HTML/JSON report, each with the affected course component (`source_object`) and a recommendation.
- Optional Streamlit UI.

## Requirements

- Python 3.12 or newer.
- [uv](https://docs.astral.sh/uv/) for development and reproducible installs.

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

# Inspect a course package
uv run lms-converter inspect course.mbz --source moodle --report
uv run lms-converter inspect course.tar.gz --source openedx --validate-for moodle

# Migrate between LMS platforms
uv run lms-converter migrate course.mbz --target openedx --output course.tar.gz
uv run lms-converter migrate course.tar.gz --target moodle --output course.mbz

# Generate a migration report (HTML or JSON), including the full event ledger
uv run lms-converter report <job-id> --format html --output report.html
uv run lms-converter report <job-id> --format json

# Show the immutable provenance ledger for a job
uv run lms-converter ledger <job-id>
uv run lms-converter ledger <job-id> --owner alice

# Roll back a job to its most recent artifact version
uv run lms-converter rollback <job-id>

# Roll back to a specific earlier version
uv run lms-converter rollback <job-id> --version 1
```

### Command reference

| Command | What it does |
| --- | --- |
| `inspect` | Parse a course package, build the canonical model, validate migration readiness |
| `migrate` | Convert a course from one LMS to another and produce an output archive |
| `report` | Render an HTML or JSON report for a completed job, including ledger history |
| `ledger` | Print the full event history for a job: each transition, actor, timestamp, and output fingerprint |
| `rollback` | Copy a previous artifact into a new version slot, reset the job to `inspected`, and record a `rolled_back` event |

## Streamlit UI

```bash
uv run --extra ui streamlit run streamlit_app.py
```

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
| `LMS_CONVERTER_ENV` | `development` | Runtime environment |
| `LMS_CONVERTER_AUTH_MODE` | `none` | `none` or trusted `proxy` identity |
| `LMS_CONVERTER_TRUSTED_USER_HEADER` | `X-Forwarded-User` | Proxy identity header |
| `LMS_CONVERTER_LOG_LEVEL` | `INFO` | Default log level |

## Security

- In development, the UI uses the local identity.
- In production, set `LMS_CONVERTER_ENV=production` and terminate authentication in a trusted reverse proxy. Configure `LMS_CONVERTER_AUTH_MODE=proxy` and the identity header; the UI fails closed when no identity is present.
- Do not expose Streamlit directly to the internet.
- UI jobs are scoped to the authenticated identity, so one user cannot open another user's job by ID.
- Uploads and migration outputs are written only under the configured server-owned directories.

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

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for contribution guidance.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
