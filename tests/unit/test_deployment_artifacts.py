import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_pins_base_image_and_runs_unprivileged():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    base = r"python:3\.12\.16-slim-bookworm@sha256:[0-9a-f]{64}"
    assert re.search(rf"^FROM {base} AS builder$", dockerfile, flags=re.MULTILINE)
    assert re.search(rf"^FROM {base} AS runtime$", dockerfile, flags=re.MULTILINE)
    assert "ARG PYTHON_IMAGE" not in dockerfile
    assert "ARG APP_UID" not in dockerfile
    assert "ARG APP_GID" not in dockerfile
    assert "--require-hashes" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "LMS_CONVERTER_ENV=production" in dockerfile
    assert "LMS_CONVERTER_AUTH_MODE=proxy" in dockerfile
    assert ":latest" not in dockerfile


def test_compose_applies_runtime_hardening():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    required = [
        "read_only: true",
        "cap_drop:",
        "- ALL",
        "no-new-privileges:true",
        "pids_limit: 256",
        "mem_limit: 2g",
        'user: "10001:10001"',
        "tmpfs:",
        "healthcheck:",
        "127.0.0.1:8501:8501",
        "lms-data:/app/data",
        "LMS_CONVERTER_ENV: production",
        "LMS_CONVERTER_AUTH_MODE: proxy",
    ]
    for item in required:
        assert item in compose
    assert ":latest" not in compose


def test_dockerignore_excludes_development_and_runtime_data():
    ignored = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert {".git", ".venv", ".env", "data", "dist", "tests", "scripts"} <= ignored


def test_sbom_generator_uses_production_requirements():
    script = (ROOT / "scripts" / "generate_sbom.py").read_text(encoding="utf-8")

    assert '"--no-dev"' in script
    assert '"--extra"' in script
    assert '"ui"' in script
    assert '"cyclonedx-py"' in script
    assert '"environment"' in script
    assert '"pip"' in script
    assert '"install"' in script
    assert '"--require-hashes"' in script


def _run_sbom_validator(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_sbom.py"), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_sbom_validator_accepts_expected_cyclonedx_shape(tmp_path):
    path = tmp_path / "sbom.json"
    path.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "metadata": {"component": {"name": "lms-converter"}},
                "components": [{"name": "defusedxml", "version": "0.7.1"}],
            }
        ),
        encoding="utf-8",
    )

    result = _run_sbom_validator(path)

    assert result.returncode == 0, result.stderr
    assert "1 components" in result.stdout


def test_sbom_validator_rejects_missing_components(tmp_path):
    path = tmp_path / "sbom.json"
    path.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "metadata": {"component": {"name": "lms-converter"}},
            }
        ),
        encoding="utf-8",
    )

    result = _run_sbom_validator(path)

    assert result.returncode != 0
    assert "components" in result.stderr
