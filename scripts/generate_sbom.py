"""Generate a CycloneDX SBOM for the production dependency set."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "sbom.json",
        help="SBOM output path (default: dist/sbom.json)",
    )
    parser.add_argument("--uv", default="uv", help="uv executable")
    parser.add_argument("--cyclonedx-py", default="cyclonedx-py", help="cyclonedx-py executable")
    args = parser.parse_args()

    uv = shutil.which(args.uv) or args.uv
    cyclonedx_py = shutil.which(args.cyclonedx_py) or args.cyclonedx_py
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="lms-converter-sbom-") as tmp:
        tmp_path = Path(tmp)
        requirements = tmp_path / "requirements.txt"
        venv = tmp_path / "venv"
        venv_python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        run(
            [
                uv,
                "export",
                "--quiet",
                "--frozen",
                "--no-dev",
                "--extra",
                "ui",
                "--no-emit-project",
                "--output-file",
                str(requirements),
            ]
        )
        run([uv, "venv", "--quiet", "--python", "3.12", str(venv)])
        run(
            [
                uv,
                "pip",
                "install",
                "--quiet",
                "--python",
                str(venv_python),
                "--require-hashes",
                "--requirements",
                str(requirements),
            ]
        )
        run(
            [
                cyclonedx_py,
                "environment",
                str(venv_python),
                "--pyproject",
                str(ROOT / "pyproject.toml"),
                "--output-file",
                str(output),
                "--output-reproducible",
            ]
        )

    print(f"Wrote SBOM: {output}")


if __name__ == "__main__":
    main()
