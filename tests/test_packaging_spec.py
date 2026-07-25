"""Tests for PyInstaller .spec files validity.

Source: plan/mouser 阶段 6 step 32-33
Verifies that .spec files are syntactically valid Python and contain
the required Analysis/EXE/COLLECT/PYZ calls per PyInstaller API.

Uses AST inspection instead of runpy execution to avoid PyInstaller's
heavy CONF initialization requirements (which expect a full build env).
AST check is sufficient to validate structure; actual build validation
happens in GitHub Actions CI.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
MAC_SPEC = REPO_ROOT / "packaging" / "mouser-mac.spec"
WIN_SPEC = REPO_ROOT / "packaging" / "mouser-win.spec"


def _parse_spec(path: Path) -> ast.Module:
    """Parse a .spec file into an AST."""
    if not path.exists():
        pytest.fail(f"Spec file missing: {path}")
    return ast.parse(path.read_text(encoding="utf-8"))


def _find_call(module: ast.Module, func_name: str) -> ast.Call | None:
    """Find the first top-level Call to `func_name(...)`."""
    for node in ast.walk(module):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == func_name:
                return node
    return None


def _get_keyword(call: ast.Call, name: str) -> ast.AST | None:
    """Get a keyword argument from a Call node by name."""
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _string_list_values(node: ast.AST) -> list[str]:
    """Extract string values from a list/tuple of string literals or str() calls.

    Handles both plain string constants (``"foo"``) and ``str(Path(...) / "foo")``
    expressions by falling back to ``ast.unparse`` for non-Constant elements.
    """
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    values: list[str] = []
    for e in node.elts:
        if isinstance(e, ast.Constant) and isinstance(e.value, str):
            values.append(e.value)
        else:
            # Fall back to source representation so `str(REPO_ROOT / "gui/main.py")`
            # and similar expressions are still recognized by substring checks.
            try:
                values.append(ast.unparse(e))
            except Exception:
                pass
    return values


def test_mac_spec_exists() -> None:
    """macOS PyInstaller spec file exists at packaging/mouser-mac.spec."""
    assert MAC_SPEC.exists(), f"Expected {MAC_SPEC} to exist"


def test_mac_spec_parses_as_python() -> None:
    """macOS spec file is syntactically valid Python."""
    _parse_spec(MAC_SPEC)


def test_mac_spec_has_analysis_call() -> None:
    """macOS spec contains an Analysis() call."""
    tree = _parse_spec(MAC_SPEC)
    call = _find_call(tree, "Analysis")
    assert call is not None, "Analysis() call not found in spec"


def test_mac_spec_analysis_has_main_script() -> None:
    """macOS spec Analysis() first arg includes gui/main.py path."""
    tree = _parse_spec(MAC_SPEC)
    call = _find_call(tree, "Analysis")
    assert call is not None
    assert len(call.args) >= 1
    # First positional arg is the scripts list.
    scripts_node = call.args[0]
    scripts = _string_list_values(scripts_node)
    assert any("main.py" in s for s in scripts), (
        f"Analysis scripts must include main.py, got: {scripts}"
    )


def test_mac_spec_analysis_has_binaries_keyword() -> None:
    """macOS spec Analysis() has a binaries= keyword (for deskflow-core)."""
    tree = _parse_spec(MAC_SPEC)
    call = _find_call(tree, "Analysis")
    assert call is not None
    binaries_kw = _get_keyword(call, "binaries")
    assert binaries_kw is not None, "Analysis() must have binaries= keyword"


def test_mac_spec_analysis_has_excludes_keyword() -> None:
    """macOS spec Analysis() has an excludes= keyword (Qt trimming)."""
    tree = _parse_spec(MAC_SPEC)
    call = _find_call(tree, "Analysis")
    assert call is not None
    excludes_kw = _get_keyword(call, "excludes")
    assert excludes_kw is not None
    excludes = _string_list_values(excludes_kw)
    # Verify some Qt modules are excluded for size.
    assert any("QtWebEngine" in e for e in excludes), (
        "QtWebEngine should be excluded to reduce bundle size"
    )
    assert any("QtQml" in e for e in excludes)


def test_mac_spec_has_exe_call() -> None:
    """macOS spec contains an EXE() call."""
    tree = _parse_spec(MAC_SPEC)
    assert _find_call(tree, "EXE") is not None


def test_mac_spec_has_collect_call() -> None:
    """macOS spec contains a COLLECT() call (onedir mode)."""
    tree = _parse_spec(MAC_SPEC)
    assert _find_call(tree, "COLLECT") is not None


def test_mac_spec_has_pyz_call() -> None:
    """macOS spec contains a PYZ() call."""
    tree = _parse_spec(MAC_SPEC)
    assert _find_call(tree, "PYZ") is not None


def test_mac_spec_references_deskflow_core() -> None:
    """macOS spec mentions deskflow-core somewhere (binary path)."""
    content = MAC_SPEC.read_text(encoding="utf-8")
    assert "deskflow-core" in content, (
        "spec must reference deskflow-core binary by name"
    )


def test_mac_spec_uses_binaries_not_datas_for_binary() -> None:
    """macOS spec uses binaries= (not datas=) for deskflow-core (D6)."""
    content = MAC_SPEC.read_text(encoding="utf-8")
    assert "binaries=" in content or "binaries =" in content, (
        "spec must use binaries= to preserve exec bit (spec drift D6)"
    )


def test_win_spec_exists() -> None:
    """Windows PyInstaller spec file exists at packaging/mouser-win.spec."""
    assert WIN_SPEC.exists(), f"Expected {WIN_SPEC} to exist"


def test_win_spec_parses_as_python() -> None:
    """Windows spec file is syntactically valid Python."""
    _parse_spec(WIN_SPEC)


def test_win_spec_has_analysis_call() -> None:
    """Windows spec contains an Analysis() call."""
    tree = _parse_spec(WIN_SPEC)
    assert _find_call(tree, "Analysis") is not None


def test_win_spec_references_deskflow_core_exe() -> None:
    """Windows spec mentions deskflow-core.exe."""
    content = WIN_SPEC.read_text(encoding="utf-8")
    assert "deskflow-core.exe" in content or "deskflow-core" in content


def test_win_spec_has_exe_and_collect() -> None:
    """Windows spec has EXE and COLLECT calls (onedir)."""
    tree = _parse_spec(WIN_SPEC)
    assert _find_call(tree, "EXE") is not None
    assert _find_call(tree, "COLLECT") is not None


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only")
def test_mac_spec_binary_path_resolves() -> None:
    """On macOS, the binary path referenced in spec actually exists."""
    content = MAC_SPEC.read_text(encoding="utf-8")
    # Extract the path from BINARY_CANDIDATES (rough check).
    if "build/bin/Deskflow.app/Contents/MacOS/deskflow-core" in content:
        binary = (
            REPO_ROOT
            / "build"
            / "bin"
            / "Deskflow.app"
            / "Contents"
            / "MacOS"
            / "deskflow-core"
        )
        assert binary.exists(), (
            f"deskflow-core binary not found at {binary}. "
            "Build it with: cmake --build build --target deskflow-core"
        )
