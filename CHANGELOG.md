# Changelog

## Unreleased (2026-10-19) — Sprint 5: sensitivity analysis (eye sweep, CHO, TV control, 12.5% extrapolation)

- **CHO observer** (`pcctvmi/observers.py`, `tests/test_cho.py`): channelized
  Hotelling observer with the frozen Gabor bank (frequencies {0.25, 0.5, 0.75}
  cy/mm x 3 orientations, one-wavelength envelopes, PROTOCOL_FREEZE.md S5-2).
  Channel covariance from mean-detrended noise ROIs (ddof=1); raises rather
  than regularises when the covariance is not PD. Closed-form white-noise
  test (single channel: d' = |<s,g>| / (sigma ||g||)); channel-scale
  invariance pinned. Review finding: a carrier at exactly 1 cycle/pixel
  samples cos(2 pi k) = 1, erasing orientation dependence and making the
  covariance singular — frequencies are frozen below the pixel Nyquist and
  the builder guards against it.
- **Eye-filter sweep + extrapolation** (`tools/sensitivity_eval.py`,
  `results/sensitivity_eval.json`): NPWE d'(E) at Burgess peaks {0.8, 1.0,
  1.5} cy/mm and the CHO, on the 6 frozen conditions plus 3 conditions at
  12.5% dose (outside the denoiser training range, S5-4). Peak keV stays at
  40 keV for every eye peak; CHO confirms the peak on the frozen template
  and tracks the processed-signal attenuation. At 12.5% the attenuation
  ratios diverge (signal sign flips per keV) and processed d' degrades
  below the 25% level — honest limit for the paper.
- **3-D TV control arm** (`pcctvmi/tv.py`, `tools/tv_weight_selection.py`,
  `tools/tv_eval.py`, `results/tv_eval.json`): Chambolle-dual isotropic TV
  over (keV, y, x), weight = 0.5 x sigma_hat^2 (sigma_hat = 3-D Laplacian
  MAD; constant selected on the S3 validation split only, S5-3). Review
  finding: the dual-ascent sign convention matters — the '+' variant
  converges to -p and *amplifies* variance; KKT-verified fix (stationarity
  ~1e-14, |p - gx/|gx|| ~3e-8). TV suppresses insert contrast to ~35% at
  every dose, biases quantitation by -4 to -7 mgI/mL and leaves 3.6-6.6 HU
  2-basis residual — UNet dominates it on quantitation and spectral
  fidelity while TV shows higher apparent d': the Pareto control axis.
- Docs: PROTOCOL_FREEZE.md §10 freezes the sensitivity design (S5-1..S5-4)
  and §10.2 records the measured results.

## Unreleased (2026-10-19) — Sprint 4: evaluation revisions and EID audit fix

- **EID air normalisation fix** (`pcctvmi/forward.py`): `air_counts` for the
  energy-integrating detector was `n0` (photon count) instead of the
  zero-path *signal* `n0 * sum(E w_E)`; the ratio signal/air then exceeded 1
  at clinical paths (1.47 through 20 cm water) and the line integral went
  negative. Fixed and pinned by three closed-form tests, confirmed to FAIL
  on the pre-fix code (tests/test_physics_audit.py). Shifted-log bias on
  EID float signals quantified as negligible (<= 1e-7 HU shift, <= 0.001 HU
  Jensen) at the worst frozen condition; LOG_SHIFT unchanged.
- **Processed-signal d'** (`tools/denoised_eval.py`): the frozen d' feeds the
  noiseless difference template, so a denoiser that suppresses insert
  contrast would go unnoticed. Added d' variants whose template amplitude is
  the signal actually present in the processed images (per-arm ROI means,
  saved as `signal_eff_*` / `signal_attenuation_*` / `*_processed`), keeping
  the frozen d' for the Sprint-2 consistency gate.
- **Quantitation disk mask** (same tool): ROI mean restricted to the insert
  interior disk (radius 0.8 x insert radius px), matching the Sprint-1
  quantitation rule; full-32x32 mean dropped.
- **Crop vs full-image inference check**: max difference in the central ROI
  reaches ~300 HU at 40 keV (GroupNorm sample statistics; the model was
  trained on 128^2 crops). Crop inference (S3-8) confirmed as the canonical
  protocol; full-image inference is out-of-distribution for this model.
- Docs: PROTOCOL_FREEZE.md §9 freezes the hypothesis-to-metric mapping
  (H1-H4) and the Sprint-4 revisions (S4-1..S4-4). Reduced-replicate pilots
  no longer trip the Sprint-2 consistency gate (warning only for R < 64).

## Unreleased (2026-10-19) — Sprint 3: AI denoiser (D1/D2) and its evaluation

- **Denoiser** (`pcctvmi/denoiser.py`, `tools/train_denoiser.py`): small
  frozen UNet (308k params, GroupNorm, fully convolutional with reflect
  padding) mapping the 16-keV VMI stack to itself. Teacher = noiseless
  baseline decomposition (S6.1); loss = L2 + 0.1 x L1 on first differences
  (S3-4). Trained 4000 steps, Adam 1e-3, batch 16, on 160 random-insert
  phantoms (S3-5, seeds 20261019, disjoint from evaluation); final val loss
  78.2 from ~1e4. Weights and training log committed
  (`results/denoiser_weights.pt`, `results/denoiser_log.jsonl`); resumable
  checkpoint stays gitignored.
- **2-basis projection** (`pcctvmi/projection.py`): closed-form per-pixel
  least-squares fit of any VMI stack back to (water, iodine) densities, with
  the RMS off-manifold residual — the quantitation path for denoised stacks
  and the spectral-consistency metric. Exact-recovery tests included.
- **Evaluation** (`tools/denoised_eval.py`, `results/denoised_eval.json`):
  Raw / denoised / noiseless compared on the frozen Sprint-1/2 conditions
  with identical seeds. Built-in consistency check: the Raw arm must
  reproduce the Sprint-2 detectability spectrum (0.00% deviation observed;
  output refused above 1%). Headline results recorded in
  PROTOCOL_FREEZE.md §8: d'(E) shape inverts (raw peaks at 60 keV, denoised
  peaks at 40 keV); quantitation bias shrinks ~3x and can flip sign; 2-basis
  residual 0.38-0.95 HU where raw is exactly zero.
- Docs: PROTOCOL_FREEZE.md §8 freezes the Sprint-3 design (S3-1..S3-9) and
  records the measured denoising effects. torch added as a dependency
  (CPU build).

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
