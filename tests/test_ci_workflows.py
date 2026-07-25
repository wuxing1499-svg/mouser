"""Tests for .github/workflows/*.yml structure.

Source: plan/mouser 阶段 7 step 35-37, 阶段 8 (CI workflow verification)
Verifies that the three CI workflow files exist and contain the expected
jobs/steps so that AC-13 (three-platform artifacts) can be satisfied.

We parse the YAML (no GitHub Actions execution) so this is fast and works
on every dev machine. Full build validation happens in CI itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

MACOS_YML = WORKFLOWS_DIR / "build-macos.yml"
WINDOWS_YML = WORKFLOWS_DIR / "build-windows.yml"
TEST_YML = WORKFLOWS_DIR / "test.yml"


def _load(path: Path) -> dict:
    if not path.exists():
        pytest.fail(f"Workflow file missing: {path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _steps_text(job: dict) -> str:
    """Concatenated text of all step names + run blocks + uses, for substring checks."""
    chunks: list[str] = []
    for step in job.get("steps", []):
        if step.get("name"):
            chunks.append(step["name"])
        if "run" in step:
            chunks.append(step["run"])
        if "uses" in step:
            chunks.append(step["uses"])
    return "\n".join(chunks)


# ---------- test.yml ----------


def test_test_workflow_exists() -> None:
    assert TEST_YML.exists()


def test_test_workflow_has_lint_and_test_job() -> None:
    """test.yml has a single lint-and-test job."""
    wf = _load(TEST_YML)
    jobs = wf.get("jobs", {})
    assert "lint-and-test" in jobs, f"missing job; got {list(jobs)}"


def test_test_workflow_runs_ruff_and_pytest() -> None:
    """test.yml runs both `ruff check` and `pytest`."""
    wf = _load(TEST_YML)
    steps_text = _steps_text(wf["jobs"]["lint-and-test"])
    assert "ruff check" in steps_text, "ruff check step missing"
    assert "pytest" in steps_text, "pytest step missing"


# ---------- build-macos.yml ----------


def test_macos_workflow_exists() -> None:
    assert MACOS_YML.exists()


def test_macos_workflow_has_arm_and_x86_matrix() -> None:
    """AC-13: build-macos.yml covers macos-14 (arm64) AND macos-13 (x86_64).

    Spec drift D8 forces two separate builds since PyInstaller cannot
    produce universal2.
    """
    wf = _load(MACOS_YML)
    job = wf["jobs"]["build"]
    matrix = job.get("strategy", {}).get("matrix", {})
    includes = matrix.get("include", [])
    archs = {entry.get("arch") for entry in includes}
    runners = {entry.get("runner") for entry in includes}
    assert "arm64" in archs, f"arm64 missing; matrix={matrix}"
    assert "x86_64" in archs, f"x86_64 missing; matrix={matrix}"
    assert "macos-14" in runners, "macos-14 runner missing"
    assert "macos-13" in runners, "macos-13 runner missing"


def test_macos_workflow_runs_codesign() -> None:
    """AC-11: build-macos.yml must run ad-hoc codesign (spec drift D7)."""
    wf = _load(MACOS_YML)
    steps_text = _steps_text(wf["jobs"]["build"])
    assert "codesign" in steps_text, "codesign step missing"
    assert "--sign -" in steps_text, "ad-hoc signing flag missing"


def test_macos_workflow_creates_dmg() -> None:
    """AC-13: build-macos.yml must produce a DMG artifact."""
    wf = _load(MACOS_YML)
    steps_text = _steps_text(wf["jobs"]["build"])
    assert "hdiutil create" in steps_text, "DMG creation step missing"


def test_macos_workflow_uploads_artifact() -> None:
    """AC-13: build-macos.yml uploads the DMG via upload-artifact action."""
    wf = _load(MACOS_YML)
    steps = wf["jobs"]["build"]["steps"]
    upload_steps = [
        s for s in steps if s.get("uses", "").startswith("actions/upload-artifact")
    ]
    assert upload_steps, "upload-artifact step missing"
    assert upload_steps[0].get("with", {}).get("if-no-files-found") == "error", (
        "upload-artifact must fail if no DMG produced (if-no-files-found=error)"
    )


# ---------- build-windows.yml ----------


def test_windows_workflow_exists() -> None:
    assert WINDOWS_YML.exists()


def test_windows_workflow_runs_on_windows_2022() -> None:
    """AC-13: build-windows.yml targets windows-2022 runner."""
    wf = _load(WINDOWS_YML)
    assert wf["jobs"]["build"]["runs-on"] == "windows-2022"


def test_windows_workflow_uploads_zip_artifact() -> None:
    """AC-13: build-windows.yml uploads a portable zip artifact."""
    wf = _load(WINDOWS_YML)
    steps = wf["jobs"]["build"]["steps"]
    has_compress = any("Compress-Archive" in s.get("run", "") for s in steps)
    assert has_compress, "Compress-Archive step missing"
    upload_steps = [
        s for s in steps if s.get("uses", "").startswith("actions/upload-artifact")
    ]
    assert upload_steps, "upload-artifact step missing"


def test_windows_workflow_uses_qt_install_action() -> None:
    """build-windows.yml uses jurplel/install-qt-action to install Qt."""
    wf = _load(WINDOWS_YML)
    steps = wf["jobs"]["build"]["steps"]
    qt_steps = [
        s for s in steps if s.get("uses", "").startswith("jurplel/install-qt-action")
    ]
    assert qt_steps, "jurplel/install-qt-action step missing"
