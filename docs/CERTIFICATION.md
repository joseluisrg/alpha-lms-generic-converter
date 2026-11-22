# LMS certification

The certification harness imports generated Moodle and Open edX packages into
fresh, pinned LMS environments and then re-exports them. A feature is verified
only when the re-export still contains the expected structure, questions, assets,
or manifest records.

## Targets

| LMS | Release | Runtime |
| --- | --- | --- |
| Moodle | 5.3 LTS, patch 5.3.1 | Moodle 5.3.1 tarball, PHP 8.4, MariaDB 11.4, Docker Compose |
| Open edX | Verawood, patch Verawood.2 | Tutor 22.0.4 |

The certification scope is defined by `tests/fixtures/golden/format-matrix.json`.
The current plan covers 57 import-checked features across two golden cases:

- `openedx/core` to Moodle: 23 features, including 17 verified checks and 6
  expected-placeholder gaps.
- `moodle/core` to Open edX: 34 features, including 22 verified checks and 12
  expected-placeholder gaps.

Placeholder features are reported as `expected_gap`. Native and transformed
features must pass their verifier; a missing or failed verifier fails the case.

## Current certified results

Two consecutive workflow-dispatched `all` runs passed at commit `8e993d3`:

| Run | Moodle | Open edX | Result |
| --- | --- | --- | --- |
| [44935886680](https://github.com/olgakazarina-guds/Team-Delta/actions/runs/44935886680) | 17/23 verified | 22/34 verified | passed |
| [44937445755](https://github.com/olgakazarina-guds/Team-Delta/actions/runs/44937445755) | 17/23 verified | 22/34 verified | passed |

Aggregate: 39 verified features (6 native, 33 transformed), 18 expected gaps,
and 0 failures. The machine-readable scorecard is
[`docs/certification-scorecard.json`](certification-scorecard.json).

## Run flow

1. Build a deterministic target archive from a golden case.
2. Import it into the pinned LMS.
3. Re-export the imported course.
4. Parse both artifacts into comparable evidence.
5. Verify each matrix feature against the original and re-exported evidence.
6. Write a schema-versioned JSON report and retain command logs.

Each import report includes the original artifact hash and size. Successful
imports also include `reimport` evidence with the re-export hash, size, command,
exit code, duration, and log file. Reports are schema version 2.

## Local Moodle run

Prerequisites: Docker Engine with Compose v2, at least 25 GB free disk, and the
Moodle 5.3.1 tarball.

```bash
curl --fail --location --retry 3 \
  --output tests/certification/environments/moodle/moodle-5.3.1.tgz \
  https://download.moodle.org/download.php/direct/stable503/moodle-5.3.1.tgz
echo "820ee2bcd89acc6b91df255b2010bbbab108f29952ab78895a79c4feabf541e7  tests/certification/environments/moodle/moodle-5.3.1.tgz" \
  | sha256sum --check

uv run python scripts/run_lms_certification.py \
  --target moodle \
  --workspace data/certification/moodle \
  --output data/reports/certification-moodle.json
```

The target creates a unique Compose project, installs Moodle, restores the
artifact, re-backs up the restored course, and removes the Compose project and
volumes on close. Default database and administrator passwords are test-only;
override them with `MOODLE_DB_PASSWORD`, `MOODLE_DB_ROOT_PASSWORD`, and
`MOODLE_ADMIN_PASSWORD`. The Moodle port defaults to `18080` and can be changed
with `MOODLE_PORT`.

## Local Open edX run

Prerequisites: Docker, at least 25 GB free disk, and Tutor 22.0.4 on `PATH`.

```bash
uv tool install tutor==22.0.4
export PATH="$HOME/.local/bin:$PATH"

uv run python scripts/run_lms_certification.py \
  --target openedx \
  --workspace data/certification/openedx \
  --output data/reports/certification-openedx.json
```

The target enables the forum plugin, disables SMTP, launches the Tutor stack,
runs `./manage.py cms xlint`, imports the course through the target-aware
`import_course_from_xml` path, and exports it again. Passing the destination
course key keeps SCORM package storage keyed to the imported block. Tutor
startup and image pulls can take several minutes.

## Nightly and manual runs

`.github/workflows/lms-certification.yml` runs both targets nightly and through
`workflow_dispatch`. Each job:

- frees runner disk space and refuses to continue below 25 GB;
- pins the LMS patch and verifies the Moodle tarball checksum;
- keeps generated reports, artifacts, and sanitized command logs as workflow
  artifacts;
- runs separately so a Moodle regeneration does not spend the Open edX disk
  budget.

Use a workflow-dispatch input to run only `moodle`, only `openedx`, or `all`.

## Pass criteria

A case passes when the import and re-export commands succeed, re-export evidence
is present, and every native or transformed feature has a `verified` outcome. A
report passes when all selected cases pass.
Exit codes are:

- `0`: report passed;
- `1`: certification failed;
- `2`: plan, configuration, or environment setup error.

Expected gaps do not fail a case, but their count is included in the summary.
Certification is eligible as a release gate after two consecutive green `all`
runs against the pinned patches; the two runs recorded above satisfy that
check. The nightly schedule remains the ongoing regression monitor.

## Evidence and troubleshooting

Reports default to `data/reports/certification-results.json` and include:

- environment release, patch, and component versions;
- original and re-export artifact hashes and sizes;
- import and re-export commands, exit codes, durations, and log names;
- per-feature expected status, verification outcome, and failure details;
- aggregate counts for verified, expected-gap, not-verified, and failed features.

Command logs are written under the workspace. Credential-like command arguments
and messages are redacted before they enter the report. Raw LMS logs should still
be reviewed before publishing artifacts.

Common failure modes:

- Moodle restore rejects backup metadata: check the generated
  `moodle_backup.xml` version and module records against the pinned release.
- A re-export loses an activity: inspect the re-exported `moodle_backup.xml`,
  `files.xml`, or OLX component tree and add or correct the verifier.
- Tutor runs out of disk: remove unused runner tooling before launch and avoid
  running both certification jobs on one runner.
- `./manage.py cms xlint` fails: inspect `xlint.log`; the import is not attempted
  after a policy error.

## Known limitations

- LTI launch data, raw XML fragments, and placeholder activities are not
  certified as functional target features.
- The Moodle target is a synthetic high-fidelity fixture, not a complete
  production backup; module metadata is updated iteratively against the first
  live restore.
- Open edX certification depends on Tutor's local Docker stack and is not
  representative of every Open edX deployment topology.
- Open edX SCORM uses Tutor's bundled `openedx-scorm-xblock` (`scorm` block type);
  the third-party `scormxblock` component is not installed.
