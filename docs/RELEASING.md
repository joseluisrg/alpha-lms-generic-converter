# Releasing lms-converter

The project publishes self-hosted releases through GitHub Releases. It does not
publish to PyPI. Every release is built from a tag that points to a commit on
`main`, and the release workflow repeats the quality gates before publishing.

## Version policy

- Use PEP 440 versions in `pyproject.toml`: `0.1.0`, `0.1.0a1`, `0.1.0rc1`.
- Tags are `v` plus the exact project version: `v0.1.0`, `v0.1.0a1`, `v0.1.0rc1`.
- Pre-release versions (`a`, `b`, `rc`, `dev`) are published as GitHub
  pre-releases automatically.
- The tag commit must be an ancestor of `origin/main`.

## Release checklist

1. Confirm `main` is green and the working tree is clean.
2. Set the release version in `pyproject.toml`.
3. In `CHANGELOG.md`, rename `## Unreleased` to `## [X.Y.Z] - YYYY-MM-DD` and add
   a fresh `## Unreleased` section for the next cycle.
4. Validate the metadata locally:

   ```bash
   uv run python scripts/check_release.py --tag vX.Y.Z
   ```

5. Commit and merge through a pull request:

   ```bash
   git commit -am "chore(release): vX.Y.Z"
   ```

6. Tag and push the tag:

   ```bash
   git tag -a vX.Y.Z -m "lms-converter vX.Y.Z"
   git push origin vX.Y.Z
   ```

7. Watch the `Release` workflow and verify:
   - the wheel, source distribution, CycloneDX SBOM, and `SHA256SUMS` are attached;
   - release notes match the changelog section;
   - pre-release flags are correct;
   - the wheel installs and the CLI smoke test passes.
8. Install the published wheel once and run `lms-converter --version`.

## Dry run

Run the workflow without creating a GitHub Release:

```bash
gh workflow run release.yml -f tag=vX.Y.Z -f dry_run=true
```

The dry run still verifies the tag, runs lint, types, and tests, builds and
installs the wheel, and uploads workflow artifacts.

## What the workflow checks

- The tag version matches `pyproject.toml`.
- `CHANGELOG.md` contains an `## Unreleased` section and a non-empty section for
  the release version.
- The tag commit is reachable from `origin/main`.
- Ruff, formatting, mypy, and the test suite pass on the tagged commit.
- Wheel and source distribution filenames contain the release version.
- The wheel installs in a clean virtual environment and passes the CLI smoke
  test.
- A CycloneDX SBOM is generated and validated for the production dependency set.
- The hardened container image builds and runs as a non-root user.
- Checksums are generated for every published artifact, including the SBOM.

## Rollback

If a release is broken:

1. Delete the GitHub Release and the tag:
   ```bash
   gh release delete vX.Y.Z --yes
   git push origin :refs/tags/vX.Y.Z
   ```
2. Do not rewrite `main`. Fix the issue and publish a new patch release
   (`X.Y.Z+1`).

## Notes

- The `package` job in `.github/workflows/ci.yml` also uploads `dist/*` as a
  workflow artifact for every CI run.
- Release notes come from the changelog section, so keep entries user-facing and
  free of internal-only details.
