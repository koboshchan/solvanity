"""Build the published layout, including notebooks, not only the import tree."""
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest


def test_wheel_build_excludes_notebooks_and_keeps_cuda(tmp_path):
    pytest.importorskip("setuptools")
    pytest.importorskip("wheel")
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "source"
    source.mkdir()
    shutil.copy2(root / "pyproject.toml", source)
    shutil.copy2(root / "LICENSE", source)
    shutil.copytree(root / "solvanity_wallet", source / "solvanity_wallet")
    shutil.copytree(root / "notebooks", source / "notebooks")
    dest = tmp_path / "wheels"
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps",
         "--no-build-isolation", "--wheel-dir", str(dest), str(source)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    with zipfile.ZipFile(next(dest.glob("solvanity_wallet-*.whl"))) as wheel:
        names = wheel.namelist()
    assert "solvanity_wallet/core.py" in names
    assert any(name.startswith("solvanity_wallet/cuda/") and name.endswith(".cu") for name in names)
    assert any(name.startswith("solvanity_wallet/cuda/vendor/") for name in names)
    assert not any(name.startswith("notebooks/") for name in names)


def test_notebook_setup_reports_subprocess_errors():
    import json
    root = Path(__file__).resolve().parents[1]
    notebook = json.loads((root / "notebooks/Solvanity.ipynb").read_text())
    cells = ["".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"]
    setup = cells[0]
    assert 'stderr=subprocess.STDOUT' in setup
    assert 'result.check_returncode()' in setup
    assert '"--verbose", "install"' in setup
    assert '"-q"' not in setup
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            compile("".join(cell["source"]), "Solvanity.ipynb", "exec")
