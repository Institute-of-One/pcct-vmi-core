"""Training must start from the same network every time.

Found by re-executing the pipeline on 2026-11-03. Every result that does not
pass through a trained network reproduced bit for bit; no trained result did.
Two 150-step runs on one machine, with one seed and byte-identical training
data, differed in all 46 tensors and in the training loss at step 150
(14209.86 against 14246.38).

The cause is not float non-determinism. ``SEED`` was given to a local
``torch.Generator`` that covers the batch order and the crop offsets, while the
convolution weights are initialised from the global torch RNG, which nothing
seeded. Each run therefore began at a different point.

These tests pin the repair. They do not claim the released weights can be
regenerated: those were trained before the repair and are archived with the
release for exactly that reason.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module", params=["train_denoiser", "train_denoiser_walnut"])
def trainer(request):
    sys.path.insert(0, str(TOOLS))
    try:
        yield _load(request.param)
    finally:
        if str(TOOLS) in sys.path:
            sys.path.remove(str(TOOLS))


def _weights(model):
    return list(model.state_dict().values())


def test_two_models_from_the_script_are_identical(trainer):
    a, b = trainer.seeded_model(2), trainer.seeded_model(2)
    assert all(torch.equal(x, y) for x, y in zip(_weights(a), _weights(b)))


def test_it_is_the_seeding_that_does_it(trainer):
    """Without the seed the same two calls differ, so the test is not vacuous."""
    torch.manual_seed(0)
    a = trainer.VMIDenoiser(n_channels=2)
    b = trainer.VMIDenoiser(n_channels=2)
    assert not all(torch.equal(x, y) for x, y in zip(_weights(a), _weights(b)))


def test_the_seed_is_the_frozen_one(trainer):
    """A model built after the protocol seed must match what the script builds."""
    torch.manual_seed(trainer.SEED)
    expected = trainer.VMIDenoiser(n_channels=2)
    assert all(
        torch.equal(x, y)
        for x, y in zip(_weights(expected), _weights(trainer.seeded_model(2)))
    )


def test_a_different_seed_gives_a_different_start(trainer):
    torch.manual_seed(trainer.SEED + 1)
    other = trainer.VMIDenoiser(n_channels=2)
    assert not all(
        torch.equal(x, y)
        for x, y in zip(_weights(other), _weights(trainer.seeded_model(2)))
    )
