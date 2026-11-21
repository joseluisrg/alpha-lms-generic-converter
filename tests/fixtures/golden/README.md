# Golden migration corpus

This directory is the deterministic regression corpus for the Moodle and Open
edX adapters. It answers three questions on every pull request:

1. Does every supported source feature still parse into the canonical model?
2. Does every target export still contain the expected files and structures?
3. Are malformed, malicious, or boundary inputs still rejected?

The corpus is synthetic. Do not add real course exports, student data, names,
email addresses, grades, institution identifiers, or production archives.

## Layout

```text
tests/fixtures/golden/
  manifest.json                 corpus contract and expected-error map
  README.md                     this file
  openedx/<case>/source/        sanitized Open edX source tree
  openedx/<case>/expected/      committed snapshots
  moodle/<case>/source/         sanitized Moodle source tree
  moodle/<case>/expected/       committed snapshots
  binaries/                     frozen packages and attack archives
  invalid/                      malformed or hostile raw payloads
```

Each valid case produces three snapshot types:

- `course.json` - normalized canonical IR (course, content nodes, assessments,
  questions, assets, raw fragments)
- `report.json` - normalized validation and migration report
- `export-<target>.json` - normalized target export tree (file names, XML
  structure, text, and archive index)

Snapshots are compared exactly. Volatile values are removed or replaced during
normalization: timestamps, backup IDs, stamps, versions, job IDs, extraction
paths, source file paths, raw source text, and generated UUIDs. Do not widen the
normalizer to hide a real fidelity regression.

## Running the corpus

```bash
uv run pytest tests/golden -q
uv run python scripts/update_golden.py --check
```

`--check` is read-only and fails when a source digest, snapshot, or manifest
digest is stale. It is suitable for CI and pre-commit checks.

## Updating snapshots

```bash
uv run python scripts/update_golden.py --write
uv run python scripts/update_golden.py --write --case openedx/core
```

Review the resulting diff before committing. A snapshot change is a fidelity
change: explain it in the pull request, including whether the old or new output
is correct and which LMS version or mapping rule motivated it.

Never run `--write` automatically from tests or CI. A broken snapshot must fail
loudly instead of silently accepting new output.

## Manifest contract

`manifest.json` is the source of truth. Its `schema_version`, `corpus_version`,
and `snapshot_version` must match the values expected by the harness. Every
valid case declares:

- `id`, `kind`, `source`
- `source_dir`, `source_sha256`
- `targets` and optional `roundtrip`
- `features` covered by the case
- `expected` snapshot paths

Every invalid case declares:

- `id`, `kind`, `source`
- `check` - the test dispatch key
- the payload, source file, source directory, or binary it needs
- `expected_error` - the typed exception the pipeline must raise
- `features` covered by the case

`tests/golden/test_features.py` asserts that the union of all declared feature
IDs exactly equals `tests/golden/features.py`. Add a feature ID only when the
pipeline actually supports the behavior and a fixture exercises it. `--check`
also reports expected snapshots that are no longer declared by a case; a full
`--write` removes them.

## Binary fixtures

Source trees are the default because they are reviewable and diff cleanly.
Commit a binary only when the exact archive bytes matter:

- the bytes are needed to reproduce a parser or security behavior
- the archive bytes are deterministic; source packages use the documented
  packer and hostile packages freeze exact attack bytes
- the file is at most 64 KiB and the whole `binaries/` directory is at most
  256 KiB
- `manifest.json` records the SHA-256, size, and reason
- `.gitattributes` marks the directory as binary

The two `*-contract` packages freeze a valid Open edX and Moodle archive for
parser compatibility. The `binaries/invalid/` packages freeze exact hostile
bytes for encrypted ZIP and symlink TAR handling. Other attack archives
(duplicates, device entries, compression bombs) are generated deterministically
at test time so the corpus does not store large payloads.

After an intentional binary update, run:

```bash
uv run python scripts/update_golden.py --write --allow-binary-change
```

The `--allow-binary-change` flag is required so a binary swap cannot pass
silently. Binary fixtures are immutable after merge unless a reviewed change
explains why the bytes must change.

## Adding a case

1. Add a small synthetic source tree under `openedx/<case>/source/` or
   `moodle/<case>/source/`.
2. Add the case to `manifest.json` with feature IDs and expected snapshot paths.
3. Run `uv run python scripts/update_golden.py --write --case <id>`.
4. Inspect every generated snapshot and the source digest update.
5. Run `uv run pytest tests/golden -q` and
   `uv run python scripts/update_golden.py --check`.
6. Update `tests/golden/features.py` only when a new supported behavior is
   intentionally covered.

## Determinism rules

- The deterministic packer sorts entries, fixes mtimes to epoch 0, clears
  owner/group names, and normalizes modes and gzip metadata.
- Source trees must not depend on filesystem iteration order.
- Generated identifiers must come from `core.identity.stable_id`; do not add
  random UUIDs to parsers or target adapters.
- Snapshot normalization must not depend on the order in which random tokens
  happen to appear.
- `--check` must pass twice in a row before a corpus change is committed.

## Security cases

Invalid cases cover XML entity expansion, malformed XML, XML size and depth
limits, package path traversal, TAR symlinks, encrypted ZIPs, duplicate TAR
entries, device entries, ZIP compression bombs, and upload size/type/session
boundaries. Each case asserts the typed exception and that traversal attempts do
not write outside the extraction root.

## Privacy and hygiene

`tests/golden/test_hygiene.py` scans text fixtures for email addresses, private
home paths, and common secret patterns, and verifies source and binary digests.
It also enforces the binary size budget. If a legitimate fixture needs an
`@`-containing Open edX asset path, keep the synthetic `asset+block@` form; do
not relax the scan for arbitrary addresses.
