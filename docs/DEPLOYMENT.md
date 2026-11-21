# Deploying LMS Converter

This guide covers the hardened container deployment for the self-hosted alpha.
The image contains the CLI and the optional Streamlit UI. It runs as an
unprivileged user and writes runtime data only to `/app/data`.

For component boundaries and data flows, see
[`ARCHITECTURE.md`](ARCHITECTURE.md). For backup, restore, rollback, retention,
and incident procedures, see [`OPERATOR_RUNBOOK.md`](OPERATOR_RUNBOOK.md).

## Requirements

- Docker Engine with BuildKit.
- Docker Compose v2 for the provided `compose.yaml`.
- A reverse proxy that authenticates users and injects the trusted identity
  header when running in production.

## Build the image

```bash
docker build --pull -t lms-converter:0.1.0a1 .
```

The base image is pinned by digest and runtime dependencies are installed from
the hash-locked `uv.lock` export. `--pull` only refreshes the pinned digest.
To pick up base-image security updates, review the new image digest and update
the `FROM` lines in the `Dockerfile` before rebuilding.

## Run with Compose

The supplied `compose.yaml` starts the web service on `127.0.0.1:8501`, uses a
named data volume, and applies the hardening controls listed below.

```bash
docker compose up -d --build
docker compose ps
curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health
```

The default Compose environment is production mode with proxy authentication.
The UI fails closed until a trusted reverse proxy supplies the configured
identity header. Do not publish port 8501 directly to an untrusted network.

The proxy must authenticate the request and overwrite, not append, the identity
header:

```nginx
proxy_set_header X-Forwarded-User $remote_user;
```

Use TLS between the client and the proxy. Restrict access to the proxy and keep
the application port bound to loopback or a private network.

### Local evaluation only

For a loopback-only evaluation without a reverse proxy, override the
authentication mode:

```bash
docker run --rm \
  -p 127.0.0.1:8501:8501 \
  -e LMS_CONVERTER_ENV=development \
  -e LMS_CONVERTER_AUTH_MODE=none \
  -v lms-data:/app/data \
  lms-converter:0.1.0a1
```

This mode has no authentication. Never expose it beyond localhost.

## Run the CLI

The image defaults to the web UI. Override the command to run the CLI:

```bash
docker run --rm \
  -v "$PWD:/work:ro" \
  -v lms-data:/app/data \
  lms-converter:0.1.0a1 \
  lms-converter inspect /work/course.mbz --source moodle
```

With Compose, use the `tools` profile:

```bash
docker compose --profile tools run --rm \
  -v "$PWD:/work:ro" \
  cli inspect /work/course.mbz --source moodle
```

Input archives can be mounted read-only. Migration outputs should be written to
a mounted volume or the managed `/app/data` tree, not into the read-only image
filesystem.

## Hardening controls

| Control | Implementation |
| --- | --- |
| Pinned base image | `python:3.12.16-slim-bookworm` by digest |
| Reproducible dependencies | Hash-locked production export installed with `--require-hashes` |
| Non-root runtime | UID/GID `10001:10001`, no login shell |
| Read-only source | Application files are root-owned; Compose uses `read_only: true` |
| Writable paths | Named volume at `/app/data`; `noexec`, `nosuid`, `nodev` `tmpfs` at `/tmp` |
| Capabilities | `cap_drop: ALL` and `no-new-privileges:true` |
| Resource limits | 2 GiB memory, 1 CPU, 256 PIDs for the web service |
| Health check | Streamlit `/_stcore/health` endpoint |
| Log rotation | Docker `json-file` driver with size and file limits |
| Network exposure | Port bound to `127.0.0.1` by default |

The application still enforces its own upload, archive, XML, output-path, and
authentication controls. Container limits are an additional boundary, not a
replacement for those controls.

## Data and upgrades

Runtime data, including the SQLite database, uploads, work directories, outputs,
and reports, lives in the `lms-data` volume. Back up the volume with a platform
snapshot or a volume-aware backup tool before upgrades. Do not use
`docker compose down -v` unless you intend to delete the data.

The operator runbook defines the stopped-snapshot backup procedure, restore and
verification steps, and the pre-restore safety copy. CLI outputs written outside
the managed output directory are user-managed and are not covered by retention
or application backups.

Upgrade procedure:

```bash
docker compose build --pull
docker compose up -d
docker compose ps
curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health
```

`--pull` does not change the pinned base digest; update the digest in the
`Dockerfile` when applying base-image security updates.

If a schema migration or release regression requires rollback, stop the
service, restore the pre-upgrade volume snapshot, and start the previous image
tag. Follow the full backup, restore, and rollback procedure in
[`OPERATOR_RUNBOOK.md`](OPERATOR_RUNBOOK.md).

## Supply chain

Generate a CycloneDX SBOM for the production Python dependency set:

```bash
uv run python scripts/generate_sbom.py --output dist/sbom.json
uv run python scripts/validate_sbom.py dist/sbom.json
```

CI validates and publishes the SBOM as an artifact, and the release workflow
validates it before attaching it to the GitHub Release with the wheel, source
distribution, and checksums. The SBOM
covers Python dependencies; scan the pinned base image with your registry or
container scanner for operating-system packages.

## Troubleshooting

- `Authentication is required.` — production mode is active and the proxy did
  not supply the configured identity header.
- `Permission denied` under `/app/data` — verify the data volume is writable by
  UID/GID `10001`.
- Health check fails — inspect `docker compose logs web` and confirm the
  container is not being killed by the memory or PID limits.
- Uploads fail below the configured limit — check proxy body-size limits as well
  as `LMS_CONVERTER_MAX_UPLOAD_BYTES`.
