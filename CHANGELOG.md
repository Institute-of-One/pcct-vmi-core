# Changelog

## Unreleased (2026-10-16) — Sprint 1 physics/statistics audit

- **Photon economy fixed (S1-6):** the forward model now uses the sum-to-one
  normalised spectrum, so the `n0` parameter is physically "incident photons per
  detector element". Frozen reference `REFERENCE_N0 = 4.0e7` photons/element at
  100% dose, chosen so the Low bin keeps >=5 mean photons at 25 cm water and
  25% dose (measured: Low 6.0e-7, High 6.1e-3 per unit n0). Auditors'
  independent estimate (0.89 photons) is consistent.
- **EID model separated from 1-bin PCD (S1-5):** `simulate(..., detector="pcd"|"eid")`.
  EID requires `thresholds_kev=()`, integrates signal with `fluence*E` weights
  (energy weighting), and uses a compound Poisson (sum of per-energy Poisson
  variates, float64 weights). `spectrum.effective_mu_rho(..., energy_weighted=True)`
  added.
- **Zero-count handling (S1-7):** log-linearisation is now shifted-log
  `-log((c + 0.5)/air)` (`LOG_SHIFT = 0.5`). Zero counts give a finite value;
  only negative counts raise.
- **Quantitation baseline** (`tools/quantitation_baseline.py`,
  `results/quantitation_baseline.json`): noiseless and repeated (N=6, seeds
  derived from base 20261016) iodine recovery across insert size
  0.3/0.5/0.8 cm, concentration 0.5-5 mgI/mL, central/peripheral placement,
  at 100%/25% dose. Key findings recorded in docs/PROTOCOL_FREEZE.md:
  concentration-independent background cross-talk of about +0.8-1.8 mgI/mL,
  and noise SD up to ~10 mgI/mL for small/low-contrast/peripheral inserts
  (cond(M) ~140-206 noise amplification).
- **New audit tests** (`tests/test_physics_audit.py`): photon conservation per
  bin, Z-score checks of all sinograms, shifted-log bias vs closed form,
  EID vs 1-bin PCD signal ratio vs closed form, EID compound-Poisson variance
  vs theory, EID+thresholds rejection.
- Docs: PROTOCOL_FREEZE.md S1-5/S1-6/S1-7 revised (dated), measured-characteristics
  section extended with the quantitation baseline, real-data arm annotated
  (walnut condition mismatch -> qualitative confirmation only; noise injection
  must preserve inter-energy noise correlation), new section 6 freezes the D1/D2
  evaluation design (teacher = noiseless baseline decomposition; primary metric =
  deviation from noiseless recovery, not nominal concentration). README real-data
  wording corrected to "planned". Example re-run at the frozen N0.

## v0.1.0 (2026-10-09)

- Initial release: spectral simulator (polyenergetic forward model, two-bin
  photon-counting detection, Poisson noise, mAs scaling), FBP reconstruction,
  water/iodine basis decomposition, VMI synthesis on a 40-190 keV grid.
- Closed-form validation tests (known HU / known iodine concentration recovery,
  K-edge monotonicity, beam-hardening cupping, bit-exact determinism).
- Protocol freeze (docs/PROTOCOL_FREEZE.md) committed before first simulation
  results.
