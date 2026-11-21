# Operator Runbook

This runbook covers day-two operation of the self-hosted alpha: health checks,
logs, upgrades, backup and restore, retention cleanup, rollback, and incident
triage. Architecture details are in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Service facts

| Item | Value |
| --- | --- |
| Web health endpoint | `http://127.0.0.1:8501/_stcore/health` |
| Compose service | `web` (UI); `cli` (tools profile) |
| Default data root | `/app/data` in the container |
| Database | `<data>/lms_converter.db` |
| Managed artifacts | `<data>/work`, `<data>/output`, `<data>/uploads`, `<data>/reports` |
| Default retention | 30 days |
| Container user | `10001:10001` |
| Compose volume | `lms-converter_lms-data` by default |

Verify the volume name before backup or restore:

```bash
docker volume ls --filter name=lms-converter
```

## Daily checks

```bash
docker compose ps
curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health
docker compose logs --since=15m web
docker stats --no-stream
```

Check disk space on the Docker host and confirm backups are recent. A healthy
web service should report `ok` from the health endpoint and remain `running` in
`docker compose ps`.

## Start, stop, and restart

```bash
docker compose up -d --build
docker compose ps
docker compose restart web
docker compose stop
```

`docker compose stop` preserves the data volume. Do not use
`docker compose down -v` unless you intend to delete all runtime data.

## Authentication and proxy checks

Production defaults are fail-closed:

```text
LMS_CONVERTER_ENV=production
LMS_CONVERTER_AUTH_MODE=proxy
LMS_CONVERTER_TRUSTED_USER_HEADER=X-Forwarded-User
```

The reverse proxy must authenticate the request and overwrite the identity
header. It must not forward a client-supplied header unchanged. Keep the
application port bound to loopback or a private network.

For a loopback-only evaluation without a proxy, explicitly override both
settings:

```bash
docker run --rm \
  -p 127.0.0.1:8501:8501 \
  -e LMS_CONVERTER_ENV=development \
  -e LMS_CONVERTER_AUTH_MODE=none \
  -v lms-data:/app/data \
  lms-converter:0.1.0a1
```

This mode has no authentication. Never expose it beyond localhost.

## Upgrade procedure

1. Record the currently running image tag or digest.
2. Run a backup using the procedure below.
3. Review the new base-image digest and release notes.
4. Build and start:

```bash
docker compose build --pull
docker compose up -d
docker compose ps
curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health
```

5. Verify that an existing report can still be opened from the UI and that a
   small inspect/migrate smoke test succeeds.
6. Run cleanup in dry-run mode and review the counts before applying it.

`--pull` does not change the pinned base digest. Update the digest in the
`Dockerfile` when applying base-image security updates.

## Backup

### What to back up

Back up the entire managed data root:

- the SQLite database, including any `-wal` and `-shm` files;
- `uploads/`, `work/`, `output/`, and `reports/`;
- any custom paths configured through `LMS_CONVERTER_*_DIR`.

CLI outputs written outside the managed output root are user-managed. Include
them in a separate backup if they are operationally important.

### Preferred: stopped snapshot

Stop the application first so the database and artifact tree are consistent:

```bash
docker compose stop
mkdir -p backups

volume_path=$(docker volume inspect lms-converter_lms-data --format '{{ .Mountpoint }}')
sudo tar -czf "backups/lms-data-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" \
  -C "$volume_path" .

docker compose up -d
```

For a non-container deployment, replace `$volume_path` with the configured
`LMS_CONVERTER_DATA_DIR`. On Docker Desktop, named-volume mountpoints are not
directly exposed on the host; use a volume-aware backup tool or the Docker
Desktop volume export feature instead.

Keep backups encrypted at rest and copy them off the Docker host. Define a
retention policy for backups separately from application retention.

### Optional: hot SQLite backup

If the service cannot be stopped, use SQLite's backup API for the database, then
snapshot the artifact directories. This is not atomic across the database and
files, so the stopped snapshot remains the preferred procedure.

```bash
DATA_DIR=/path/to/data
BACKUP_DIR=$PWD/backups
sqlite3 "$DATA_DIR/lms_converter.db" ".backup '$BACKUP_DIR/lms_converter.db'"
```

Copy `uploads/`, `work/`, `output/`, and `reports/` into the same backup set.

### Verify a backup

```bash
tar -tzf backups/lms-data-<timestamp>.tar.gz >/dev/null
mkdir -p /tmp/lms-restore-check
tar -xzf backups/lms-data-<timestamp>.tar.gz -C /tmp/lms-restore-check
sqlite3 /tmp/lms-restore-check/lms_converter.db "PRAGMA integrity_check; PRAGMA user_version;"
rm -rf /tmp/lms-restore-check
```

The integrity check should return `ok`. Record the schema version with the
backup so it can be matched to the application release.

## Restore

Restore is destructive. Preserve the current data before replacing it.

```bash
docker compose stop

PRE_RESTORE="backups/pre-restore-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
volume_path=$(docker volume inspect lms-converter_lms-data --format '{{ .Mountpoint }}')
sudo tar -czf "$PRE_RESTORE" -C "$volume_path" .

sudo find "$volume_path" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
sudo tar -xzf backups/lms-data-<timestamp>.tar.gz -C "$volume_path"
sudo chown -R 10001:10001 "$volume_path"

docker compose up -d
docker compose ps
curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health
```

After startup, verify:

1. `PRAGMA user_version` matches the expected application schema.
2. A known job report opens in the UI.
3. A known output or report file exists and is readable.
4. `docker compose --profile tools run --rm cli cleanup` reports plausible
   dry-run counts.

If verification fails, stop the service and restore the pre-restore snapshot.

## Rollback

Application rollback and data restore are separate operations.

1. Stop the service.
2. Restore the pre-upgrade backup if a schema migration or data change must be
   reverted.
3. Start the previous image tag against the restored data.
4. Re-run health and report checks.

Keep previous image tags locally until the upgrade has been verified. Do not
attempt to run a newer database schema with an older application image.

## Retention cleanup

Preview first:

```bash
docker compose --profile tools run --rm cli cleanup --dry-run
```

Apply during a maintenance window:

```bash
docker compose --profile tools run --rm cli cleanup --apply
```

Retention removes expired job rows, extracted work directories, managed
outputs, and stale upload sessions. Outputs outside the managed output root are
never deleted. `--retention-days N` overrides the configured retention for one
run.

## Troubleshooting

| Symptom | Checks |
| --- | --- |
| `Authentication is required.` | Confirm production proxy mode, TLS, and that the proxy overwrites `X-Forwarded-User` |
| `Permission denied` under `/app/data` | Confirm the volume is writable by UID/GID `10001` |
| Health check fails | Inspect `docker compose logs web`; check memory/PID limits and startup errors |
| `database is locked` | Stop duplicate writers or CLI containers; do not run cleanup concurrently with heavy jobs |
| Schema-version error | Confirm the image and data backup versions match; roll back if the database is newer |
| Disk usage grows unexpectedly | Check `du -sh` on the volume, backup retention, and `cleanup --dry-run` |
| Missing output or report | Check the job artifact paths and whether a custom path sits outside the managed roots |
| Uploads fail below the app limit | Check reverse-proxy body-size limits as well as `LMS_CONVERTER_MAX_UPLOAD_BYTES` |

## Limitations

- SQLite is single-writer; this is a pilot deployment, not a horizontally
  scalable service.
- There is no built-in backup scheduler, metrics endpoint, or alerting stack.
- Streamlit is the pilot UI and may not meet long-term accessibility or
  multi-user requirements.
- There is no direct Moodle or Open edX API integration; exchange happens
  through package import/export.
- External CLI outputs are outside managed retention and backup unless operators
  include them explicitly.

## Support handoff

Collect this information before escalating:

```bash
docker compose ps
docker compose logs --since=30m web
curl --fail --silent --show-error http://127.0.0.1:8501/_stcore/health
df -h
volume_path=$(docker volume inspect lms-converter_lms-data --format '{{ .Mountpoint }}')
sqlite3 "$volume_path/lms_converter.db" "PRAGMA integrity_check; PRAGMA user_version;"
```

Include the application version, image digest, backup filename, and the failing
job ID. Do not send course packages, student data, or other confidential content
unless the support process explicitly permits it.

## Drill checklist

Run this drill before a release and at least quarterly:

1. Create an inspect or migrate job and generate a report.
2. Stop the web service.
3. Take a data-root backup and record its checksum.
4. Remove or rename the live data root.
5. Restore the backup and correct ownership.
6. Start the service and confirm health.
7. Confirm the job row, course snapshot, report, and output are present.
8. Run the SQLite integrity check and verify the schema version.
9. Run cleanup in dry-run mode.
10. Record the drill date, backup checksum, and result.

The automated equivalent is
`tests/integration/test_backup_restore.py`, which runs in CI.
