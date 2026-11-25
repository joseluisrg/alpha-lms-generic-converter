# Preflight Migration Advisor

The Advisor checks a Moodle package for known migration issues before an Open edX export. The first rule identifies essay questions that the current Open edX exporter represents as placeholders.

For a synthetic Moodle package named `essay.mbz`, run:

```powershell
uv run --no-sync lms-converter inspect essay.mbz --source moodle --validate-for openedx --preflight --output preflight.json
```

Use `--output` for a JSON file. When the output path is omitted, the command displays the report alongside its progress output. Standard inspection uses the existing output format for calls that omit `--preflight`.

The report starts at `schema_version` 1. It contains the inspection `job_id`, source, target, validation error codes, and Advisor findings. Each `OPENEDX_ESSAY_PLACEHOLDER` finding contains a stable finding ID and question ID, a warning severity, the `placeholder` status, and a recommendation to recreate the question and verify its grading.

A `MOODLE_PACKAGE_FILE_MISSING` finding identifies a file that the Moodle parser represents as an asset and that is absent from the extracted backup. The warning contains the existing `asset_id`, the `missing` status, and a recommendation to create a backup that includes the file. The lookup resolves the referenced path inside the backup directory.

The Advisor uses the existing inspection job and ledger event. It reports the manual work for the target course and includes existing error codes in `validation_error_codes`. Standard inspection shows the full validation messages.

## Test

```powershell
uv run --no-sync pytest tests/integration/test_moodle_essay_export.py tests/integration/test_preflight_package_files.py
```

The test fixture creates `essay.mbz` in the test's temporary directory with one multiple-choice question and one essay question. The tests cover the generated placeholder, the single Advisor finding, stable IDs across runs, the standard inspection JSON, and the ledger event. The package-file test removes the PDF payload from a copy of the test archive while preserving the activity reference and file record. An import into an Open edX instance requires a separate check.

### SCORM packages

The Moodle parser checks the activity directory first, then looks up the
activity's ZIP through `inforef.xml` and `files.xml`. It uses the original ZIP
filename when resolving a package from the Moodle file store. A missing or
ambiguous package produces an HTML fallback. The Advisor's package-file rule
checks the files represented as assets in the course model.

```powershell
uv run --no-sync pytest tests/integration/test_moodle_scorm_package.py
```

The synthetic test cases cover both storage layouts, missing and ambiguous
packages, and the SCORM component's link to the ZIP in the Open edX export.

## Demo with both findings

Run the block from the repository root in PowerShell. The demo uses the
existing `.venv` and creates a fresh directory alongside the repository.
The synthetic package keeps the essay question and the activity's PDF
reference and omits the PDF payload. The report is saved as `preflight.json`
in the demo directory.

```powershell
$projectRoot = Split-Path -Parent (Get-Location).Path
$demoId = [guid]::NewGuid().ToString('N').Substring(0, 8)
$demoRoot = Join-Path $projectRoot "demo-$demoId"
$testRoot = Join-Path $demoRoot 'test'
New-Item -ItemType Directory -Path $demoRoot -ErrorAction Stop | Out-Null

$env:TEMP = $demoRoot
$env:TMP = $demoRoot
$env:TMPDIR = $demoRoot
$env:LMS_CONVERTER_DATA_DIR = Join-Path $demoRoot 'data'
$env:LMS_CONVERTER_DB_PATH = $null
$env:LMS_CONVERTER_WORK_DIR = $null
$env:LMS_CONVERTER_OUTPUT_DIR = $null
$env:LMS_CONVERTER_UPLOAD_DIR = $null
$env:LMS_CONVERTER_REPORT_DIR = $null
$env:PYTEST_ADDOPTS = $null

.\.venv\Scripts\python.exe -m pytest --basetemp $testRoot 'tests/integration/test_moodle_essay_export.py::test_preflight_demo'
if ($LASTEXITCODE -ne 0) { throw 'The Preflight demo test failed.' }

$archive = Get-ChildItem -LiteralPath $testRoot -Recurse -File -Filter 'preflight-demo.mbz' |
    Select-Object -First 1
if ($null -eq $archive) { throw 'The synthetic Moodle package was not generated.' }

$reportPath = Join-Path $demoRoot 'preflight.json'
.\.venv\Scripts\python.exe -m cli.main inspect $archive.FullName --source moodle --validate-for openedx --preflight --output $reportPath --log-level ERROR
if ($LASTEXITCODE -ne 0) { throw 'The Preflight CLI demo failed.' }

$report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
$codes = @($report.findings.code | Sort-Object)
$expectedCodes = 'MOODLE_PACKAGE_FILE_MISSING|OPENEDX_ESSAY_PLACEHOLDER'
if ($report.schema_version -ne 1 -or ($codes -join '|') -ne $expectedCodes) {
    throw 'Expected the two Preflight findings in a schema version 1 report.'
}

"Schema $($report.schema_version) | $($report.source) -> $($report.target) | $($codes.Count) findings"
$report.findings | Format-Table code, severity, status -AutoSize
git rev-parse HEAD
```

The version 1 report contains the following two warnings.

| Code | Reference | Status |
| --- | --- | --- |
| `OPENEDX_ESSAY_PLACEHOLDER` | `question_id` | `placeholder` |
| `MOODLE_PACKAGE_FILE_MISSING` | `asset_id` | `missing` |

The recommendations describe the work required. Effort estimates remain open
until the checks have been evaluated on representative courses.
