# Changelog

## Unreleased (2026-10-17) — Sprint 2: task detectability (NPWE port, H1)

- **Model observers ported from taskiq-core** (`pcctvmi/observers.py`, mm-based
  per the S2 freeze): ensemble 2-D NPS measurement (`nps_2d`, integral ==
  variance identity at rtol 1e-10), NPWE / plain NPW and the ideal linear
  observer (closed-form, with the ported guards: zeroed-DC-bin weight check
  for non-prewhitening observers, dynamic-range / noise-floor check for the
  prewhitening one), Burgess eye filter, image scoring, and d'/AUC figures of
  merit. `detrend` now zeroes the DC bin exactly (float residue ~1e-32 made
  the "measured NPS has a zeroed DC" contract unreliable).
- **Closed-form + Monte-Carlo tests** (`tests/test_observers.py`): white-noise
  identity d' = ||s||/sigma, NPW == ideal observer in white noise, ideal
  upper-bounds NPWE on correlated noise, NPWE immunity to the zeroed DC bin,
  floorless-NPS rejection, and simulated-score agreement with the closed form
  (rel 0.05).
- **Detectability spectrum** (`tools/detectability_spectrum.py`,
  `results/detectability_spectrum.json`): NPWE and ideal d'(E) on the frozen
  40-190 keV grid for 0.3/0.5/0.8 cm inserts (5 mgI/mL, r = 3 cm) at 100%/25%
  dose, R = 64 noise realisations per condition. Headline: NPWE d'(E) peaks at
  60 keV for every condition; d' scales as sqrt(dose) (3.78 -> 1.92 at
  60 keV, 0.3 cm); NPWE efficiency vs the ideal observer falls with insert
  size (35% at 0.3 cm vs 10% at 0.8 cm, 70 keV) — efficiency is
  signal-dependent and must not be assumed constant.
- **Projection caching in `simulate`**: optional `projections=` kwarg reuses
  `areal_density_projections` across ensemble realisations (validated shape
  check; bit-identical results — test added).
- Docs: PROTOCOL_FREEZE.md §7 freezes the Sprint-2 evaluation design (S2-1..S2-7)
  and records the measured detectability characteristics.

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
