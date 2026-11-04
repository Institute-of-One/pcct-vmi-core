"""The merged evaluation result must land beside its own chunks.

Found by re-executing the pipeline: ``--final denoised_eval_d2.json``, the
command in tools/denoised_eval.py's own docstring, wrote the merged D2 result
into the working directory while the six chunk files and the plot went to
``results/``. The committed repository has the file in ``results/``, so the
released code did not reproduce the released layout, and a reader following the
documented command would have looked for a file that was not there.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def _load(name: str):
    """Import a tools/ script by path; they are scripts, not a package."""
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def denoised_eval():
    sys.path.insert(0, str(TOOLS))
    try:
        return _load("denoised_eval")
    finally:
        sys.path.remove(str(TOOLS))


def test_a_bare_name_lands_in_results(denoised_eval):
    resolved = denoised_eval.resolve_final(Path("denoised_eval_d2.json"))
    assert resolved.parent == denoised_eval.OUT
    assert resolved.name == "denoised_eval_d2.json"


def test_a_relative_path_lands_in_results(denoised_eval):
    resolved = denoised_eval.resolve_final(Path("sub/denoised_eval_d2.json"))
    assert denoised_eval.OUT in resolved.parents


def test_an_absolute_path_is_left_alone(denoised_eval, tmp_path):
    elsewhere = tmp_path / "denoised_eval_d2.json"
    assert denoised_eval.resolve_final(elsewhere) == elsewhere


def test_the_merged_file_sits_with_the_chunks_it_is_merged_from(denoised_eval):
    """The merge globs OUT for FINAL.stem + '_part*'; the output must match."""
    final = denoised_eval.resolve_final(Path("denoised_eval_d2.json"))
    chunk = denoised_eval.OUT / f"{final.stem}_part0000_0001.json"
    assert chunk.parent == final.parent


def test_the_default_is_unchanged(denoised_eval):
    assert denoised_eval.resolve_final(denoised_eval.FINAL) == denoised_eval.FINAL
    assert denoised_eval.FINAL.parent == denoised_eval.OUT
