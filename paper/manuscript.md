# Signal and noise suppression reshape detectability and material fidelity in denoised photon-counting CT spectral images

## Abstract

Purpose: To assess whether denoising changes energy-dependent model-observer detectability and material fidelity in photon-counting computed tomography spectral images.

Methods: A frozen water–iodine simulation generated virtual monoenergetic images at 40–190 keV for three insert diameters and two photon-count levels, with 64 noise realizations per condition. A reconstruction-loss network (D1), a basis-coordinate-loss network (D2), and total variation were compared using fixed-template and amplitude-scaled detectability, iodine deviations, and spectral residuals. A separate walnut reconstruction experiment used correlated Gaussian noise injection and a retrained two-channel network.

Results: Fixed-template D1 detectability peaked at 40 keV versus 60 keV before denoising. Amplitude scaling retained the 40-keV peak in five conditions; the 8-mm, quarter-count condition peaked at 190 keV. D1 reduced iodine variability, contradicting the hypothesis of uniformly worsened quantitation, but retained quarter-count bias. D2 introduced full-count positive bias and increased quarter-count spectral residuals. Across 60 walnut slices, quarter-count mean image error fell from 680.1 to 132.0 HU with the retrained network; pulp bias was −3212.5 on the calibration-table material scale.

Conclusions: Noise suppression, signal preservation, and material fidelity require separate assessment. Background-noise-derived detectability and improved image appearance alone cannot establish quantitative accuracy or clinical benefit. The walnut experiment provides reconstruction-based stress testing, not independent patient validation.

Keywords: photon-counting computed tomography; virtual monoenergetic imaging; denoising; model observer; material decomposition

## 1. Introduction

Photon-counting computed tomography (PCCT) acquires energy-resolved measurements that can support virtual monoenergetic imaging and material decomposition [1]. These outputs serve different purposes. Low-energy virtual monoenergetic images (VMIs) can emphasize iodine contrast, whereas material maps estimate a composition-dependent quantity. Both depend on the statistical properties of the same spectral measurements. Consequently, a postprocessing operation that improves one output need not improve another. The energy that maximizes a specified observer response is a property of the combined acquisition, reconstruction, processing, and task, rather than of photon energy alone.

Prior work already establishes why denoising should be evaluated against a task rather than image similarity alone. Li and colleagues compared ideal and linear observers for binary detection and demonstrated that denoising can remove task-relevant information [2]. In PCCT specifically, Chang and colleagues developed a prior-knowledge-aware network that uses energy-dependent VMI noise characteristics [3]. Thus, neither task-based denoising evaluation nor exploiting spectral noise structure is claimed as new here. The present contribution is a paired analysis of energy selection, material deviation, and two-basis residuals under a fixed experimental design, including a deliberately tested spectral-loss alternative.

Image-domain denoising adds a further complication. A network trained against a noiseless reference can reduce background fluctuations while changing the amplitude or shape of a small signal. A Fourier-domain detectability calculation that retains the original signal template but substitutes the processed background noise power spectrum (NPS) credits noise suppression without necessarily accounting for signal loss. Adding a signal-amplitude correction can reveal part of that discrepancy, although it does not make a nonlinear processor stationary or recover changes in signal shape. Material estimation introduces another distinction: spectral curves can remain close to a two-basis subspace while moving substantially within that subspace. A small spectral fitting residual therefore cannot establish a correct iodine estimate.

The present study examines these distinctions using a controlled spectral simulation and a public cone-beam PCCT walnut dataset. The contribution is an evaluation framework and a measured comparison of processing effects, rather than a new network architecture. A reconstruction-loss network, a network with an additional basis-coordinate penalty, and classical total variation (TV) are evaluated against the same realizations and reference operators. The analysis keeps image noise, signal transfer, material deviation, and spectral fitting residual separate throughout.

Four hypotheses were specified before their corresponding evaluations. H1 predicted improved detectability and a shift of its energy optimum toward lower energies after denoising. H2 predicted that reconstruction-loss denoising would improve detectability while worsening iodine quantitation. H3 predicted that an additional spectral loss would recover quantitation while retaining detectability gains. H4 asked whether a public walnut reconstruction experiment would show directionally consistent changes. All four are reported, including unsupported predictions. The operational protocol was amended in dated stages to correct physical modeling and evaluation defects; the original hypotheses were retained. This is a version-controlled design freeze, not a claim of registration in a public prospective trial registry.

## 2. Materials and methods

### 2.1. Study design and evaluation scope

The primary arm used a two-dimensional water cylinder containing iodine inserts with known geometry. Six conditions combined insert diameters of 3, 5, and 8 mm with photon-count fractions of 100% and 25%. Each insert contained 5 mgI/mL and lay 3 cm from the cylinder center. Each condition included 64 noise realizations. The VMI grid comprised 16 levels from 40 to 190 keV in 10-keV increments. These complete energy curves were evaluated without selecting a favorable subset of energies. The intermediate 50% level in the initial research plan was included in the training range but was not a primary endpoint condition in the later evaluation freeze. A 12.5% condition was reserved for sensitivity analysis outside the training range.

The secondary arm used 60 contiguous reconstructed slices from a single walnut. It assessed changes relative to the supplied reconstruction after simulated noise was added in image space. This arm did not include a frozen signal-known-exactly detection experiment, patient data, clinical diagnoses, or independently acquired low-dose scans. Accordingly, it cannot validate lesion detectability or a clinical dose-reduction claim. Figure 1 presents the two analysis paths and their distinct endpoints.

### 2.2. Spectral forward model and reconstruction

The primary simulation used a 120-kVp tungsten spectrum with a 12-degree anode angle and 8-mm aluminum-equivalent filtration, generated with SpekPy [4] and retained as a CSV input. Water and iodine mass attenuation coefficients were obtained through xraylib [5], tabulated from 10 to 200 keV and interpolated in log–log space. The forward model integrated exponential attenuation over the polychromatic spectrum. The detector was an ideal threshold counter with Low and High bins separated at 30 keV; charge sharing, pulse pileup, scatter, and scanner-specific electronics were not modeled.

The spectrum was normalized to unit fluence before applying the photon-count parameter. The frozen full-count reference was 4.0 × 10^7 incident photons per detector element; lower-count conditions scaled this quantity. Thus, the count fractions denote simulator exposure settings, not measured patient doses. Poisson noise was generated in projection space. A shifted logarithm, −log[(c + 0.5)/air], made zero-count measurements finite without excluding them. Reconstruction used Hann-filtered backprojection on a 512 × 512 grid at 0.5-mm spacing, with 180 uniformly spaced projection angles over 360 degrees.

The reconstructed bin images were decomposed into water and iodine coordinates using a two-by-two effective-attenuation matrix. The reference water path for the effective coefficients was the mean chord πD/4 for the 25-cm cylinder. VMIs were synthesized from these coordinates using tabulated attenuation ratios. Because effective-energy linearization and beam hardening produce their own systematic effects, denoiser-induced material changes were measured relative to the matched noiseless reconstruction, rather than treating nominal insert concentration as the only reference. The saved noiseless baseline itself varied with count setting because the shifted-log operation also acts on expected counts. This dependence is retained in the reported baselines and limits cross-dose interpretation.

The associated software tests cover photon-count normalization, zero-count behavior, monoenergetic water and iodine recovery, and distinction between photon-counting and energy-integrating detection. Energy-integrating detection is implemented separately with energy-weighted compound-Poisson statistics. No unmeasured energy-integrating comparison is presented as a result of this manuscript.

### 2.3. Denoising arms and training separation

D1 was a small two-dimensional U-Net [6] with two downsamplings, 32 base features, a maximum width of 64, and GroupNorm in the convolution blocks. All 16 energies were input and output channels. Therefore, D1 was not a set of independently trained single-energy networks: its reconstruction loss lacked an explicit material-coordinate term, but its architecture could use cross-energy information. This distinction supersedes the shorthand “single-image denoiser” in the initial plan.

The loss combined image-domain squared error and 0.1 times the absolute gradient difference from the noiseless teacher. Training used 192 simulated water–iodine phantoms with zero to five randomly placed inserts, diameters of 0.2–1.0 cm, concentrations of 0.5–5 mgI/mL, and count fractions sampled over 25–100%. The first 160 phantoms formed the training split and the remaining 32 the validation split. The training-data seed base was 20261019, separate from evaluation seeds. Adam used a learning rate of 10^−3, batches of 16, and 4000 optimization steps on 128 × 128 crops. The principal evaluation also used 128 × 128 crops, with the central 32 × 32 region used for measurements.

Crop inference is a substantive condition of these results. Earlier protocol checks found that full-image inference could change central values substantially because GroupNorm depends on the spatial extent of its input. Being fully convolutional does not imply that this model produces identical values on different input extents. The primary arm therefore retained the crop configuration; the walnut arm used its separately specified whole-image procedure, which is discussed as a limitation.

D2 used the same architecture and reconstruction loss, with an added penalty β mean[(1000Δa)^2 + (1000Δb)^2], where a and b were least-squares water and iodine coordinates relative to the noiseless teacher. The initial proposal to match raw-derived material maps was replaced before D2 training because that target would reward noise retention. Candidate β values of 0.3, 1.0, and 3.0 were compared after 1200 steps using a common validation criterion, val_L2 + val_b2. The selected β was 3.0, followed by 4000-step training. Selection used the validation split rather than evaluation conditions. D1 and D2 training logs use different aggregate validation definitions, so their final aggregate loss values are not directly compared.

D3 used three-dimensional isotropic TV over the two spatial axes and the energy-channel axis, implemented with a Chambolle-type dual algorithm [7]. The channel spacing was treated as one numerical unit; this is not a physical metric equating an energy increment with a spatial displacement. The weight was 0.5σ̂^2, with σ̂ estimated by a robust Laplacian median absolute deviation. The coefficient 0.5 was selected on validation crops. Iterations were fixed at 300. This TV configuration is a specific comparator, not an optimized bound on all classical or physics-aware denoisers.

### 2.4. Detectability and signal-transfer measurements

The primary observer was non-prewhitening with a Burgess eye filter (NPWE), with peak frequency 1.0 cycles/mm and exponent 1.3. Signal and NPS grids were both 32 × 32 pixels. The noiseless signal template was the insert-centered image minus its mirrored water-background image. Noise was measured at the mirrored location across the 64 realizations. Mean-detrended ensemble periodograms were normalized so that their frequency integral equaled measured variance.

For template transform S, eye filter E, and NPS N, the observer calculation was d′² = [∫|S|²E² df]² / ∫|S|²E⁴N df. An ideal linear observer was also calculated as a software-level reference under stationary assumptions. Neither observer is a clinical reader experiment. After nonlinear processing, a background NPS may poorly represent noise at the signal location; very large computed values must therefore be interpreted as properties of this approximation.

Two template conventions were retained. The frozen-template calculation used the original noiseless template with each arm's measured NPS. The amplitude-scaled calculation multiplied that template by the ratio of the ensemble-mean insert-minus-background contrast after processing to its noiseless value. This preserves the original spatial shape and is not a measurement of the complete processed signal template. The quadratic observer expression gives a nonnegative magnitude, equal to the absolute ratio times frozen-template d′. The primary evaluation stores that magnitude, whereas the TV and sensitivity tools store the ratio times d′ with its sign. For consistent comparisons, figures and energy maxima here use magnitudes. Negative signal-transfer ratios, retained separately in the source records, indicate polarity reversal and must not be interpreted as faithful preservation of the original signal. A magnitude alone does not expose that reversal.

Sensitivity analyses varied the eye-filter peak over 0.8, 1.0, and 1.5 cycles/mm and used a nine-channel Gabor channelized Hotelling observer. Channel frequencies were 0.25, 0.5, and 0.75 cycles/mm with orientations 0, 60, and 120 degrees, below the 1.0-cycles/mm Nyquist frequency. Positive-definite channel covariance was required; no silent regularization was used to rescue a singular estimate. These analyses assess dependence on the specified observer, rather than calibrating performance against human readers.

### 2.5. Iodine estimation and spectral residual

At each pixel, the 16-energy stack was fitted to VMI(k) = 1000[a + b r_k − 1], where r_k is the iodine-to-water mass-attenuation ratio. Iodine concentration in g/cm³ was converted to mgI/mL by multiplication by 1000. The insert measurement used an interior disk with radius 0.8 times the insert radius, rounded to pixels with a minimum radius of two pixels. Deviations from the matched noiseless baseline were summarized by their mean and realization SD. These SDs measure variation across noise realizations, not uncertainty across patients or independently trained models.

The spectral residual was the root-mean-square HU discrepancy after projecting a stack onto its two-basis fit. Raw synthesized VMIs lie in that subspace by construction, so an approximately zero raw residual is an algebraic property. A denoised stack may have both an off-subspace residual and an erroneous location within the subspace. We therefore reported residuals alongside material deviations. For a compact trade-off display, sqrt(mean_deviation² + SD²) was used as a descriptive deviation RMS proxy. It is not a newly prespecified clinical endpoint or an exact pooled error estimate across heterogeneous subjects.

### 2.6. Walnut reconstruction stress test

The source was the public cone-beam photon-counting CT dataset [8,9], specifically Walnut 1, series FDK_Dose_1_hann_TV_100_20, slices 500–559. The acquisition used 80 kVp, thresholds of 15 and 30 keV, and 1440 views. Supplied Low and High reconstructions had 1000 × 1000 pixels at 0.05-mm spacing. The series name indicates prior reconstruction processing; the supplied images are a reference reconstruction, not noiseless physical ground truth.

VMI operators at 10–80 keV were obtained by regressing the supplied VMI DICOM values against Low + 1000 and High + 1000, then freezing the coefficients. The relationship was VMI(E) = c_L(E)(Low + 1000) + c_H(E)(High + 1000) − 1000. Recorded agreement was R² ≥ 0.9999988, with checks on slices 500, 530, and 559. Thus this operator reproduces a dataset mapping; it is not an independently validated reconstruction of the scanner's physical calibration procedure. Coefficient fitting on slices within the evaluation range further limits independence.

The provided MD_Pulp_Shell series was not used as material truth because repository checks did not reproduce it as the expected linear mapping from the supplied bins. Instead, both reference and processed material maps were calculated as 1000 DM^−1[Low + 1000; High + 1000], with DM rows (784.34, 890.25) and (1025.52, 1135.36). The matrix condition number was approximately 166.9. Values are reported on this calibration-table mg/cm³-scale; they are not verified biochemical concentrations or iodine measurements. The observed discrepancy does not establish its cause in the source dataset.

Stationary correlated Gaussian noise was generated from a separate simulated 80-kVp, 35-mm water-disk configuration, retaining inter-bin cross-spectral covariance. The noise model used 32 realizations, 256 × 256 central regions, and 3.0 × 10^4 full-count photons per detector element. Noise in inverse centimeters was converted to HU using full-count water coefficients of 0.5575717877 and 0.2553258904 cm^−1. One realization per slice, seeded by 20261020 + slice index, was shared by Raw, D1w, and TV. The labels 25% and 12.5% identify nominal simulator settings. Added noise on an already noisy reconstruction is not equivalent to projection thinning or a measured dose-matched repeat acquisition.

D1w was separately retrained with two input/output channels on scaled water–iodine simulations, using seed base 20261022. It was not the primary 16-channel model transferred unchanged. Training and teacher images were shifted by bin offsets of −228 and −130 HU, estimated from the evaluation slices' pulp means. This adaptation used no denoised target from those slices, but it did use their input distribution; it therefore precludes a fully held-out external validation claim. Water–iodine training materials also differ from walnut pulp and shell. TV used the same weight rule on each noisy two-bin stack.

VMI root-mean-square error (RMSE) was computed inside the reference Low-bin threshold mask (> −900 HU) intersected with a central disk of radius 250 pixels. Structural similarity (SSIM) [10] was computed over the whole image with the reference image range, not restricted to that mask. Material regions were defined from the reference maps within the central mask: the target material was above its median and the other material below its lower quartile, with a corresponding swapped definition for shell. Pixelwise error means and SDs were calculated within these regions. Summary values were arithmetic means over 60 slices; the reported total-error proxy was calculated from the mean bias and mean SD, rather than pooling all pixels. Adjacent slices from one specimen are not 60 independent biological samples.

### 2.7. Reproducibility and statistical interpretation

Results were read from the version-controlled JSON files rather than transcribed from intermediate protocol narratives. Figure and table generation retained input and script hashes. The two study arms used distinct energy grids and material units. No significance test was used to convert the six designed simulation conditions or the 60 adjacent walnut slices into a population-level claim. Reported standard deviations have their measurement-specific definitions above. Uncertainty from finite NPS estimation, network initialization, and transfer to other objects remains unquantified by confidence intervals in this study.

## 3. Results

### 3.1. Detectability-energy curves and H1

Figure 2 shows all six primary conditions for Raw, D1, D2, and TV under both template conventions. The raw frozen-template optimum was 60 keV in every condition. For 3-, 5-, and 8-mm inserts, the corresponding full-count maxima were approximately 3.78, 4.22, and 4.68, compared with 1.92, 2.08, and 2.35 at quarter count. The approximate twofold ratio is consistent with photon-noise scaling for a fourfold count change.

D1's frozen-template optimum was 40 keV in every condition, a 20-keV downward shift. This does not describe all amplitude-scaled results. Five D1 conditions retained a 40-keV optimum, whereas the 8-mm, quarter-count condition peaked at 190 keV. Raw amplitude-scaled optima also differed from frozen-template optima in two quarter-count conditions. Table 1 provides the matched values, including these exceptions. H1 therefore received support under the frozen-template convention and qualified support after accounting for signal amplitude; its universal directional form was not established.

TV produced the largest frozen-template detectability values, but its amplitude-scaled optima varied across conditions. Suppressed background NPS explains why a high observer estimate can coexist with poor material recovery. Such values do not demonstrate that TV or either network improves true ideal-observer performance beyond the information in the original data. The observable result is improved performance of a particular background-NPS calculation under its assumptions.

{{TABLE1}}

### 3.2. Iodine variability, residual bias, and H2

Figure 3 and Table 2 show iodine deviations relative to the condition-specific noiseless baseline. D1 reduced realization SD strongly in all six conditions. For the 3-mm, quarter-count insert, Raw deviation was −7.281 ± 24.989 mgI/mL and D1 deviation was −1.937 ± 0.096 mgI/mL. At full count, the corresponding values were +0.519 ± 11.683 and +0.034 ± 0.051 mgI/mL. These values differ materially from the obsolete preliminary whole-ROI measurements; the interior-disk results are used here.

Across the three quarter-count conditions, D1 retained negative deviations of approximately −1.94 to −2.59 mgI/mL. A narrow output distribution therefore did not imply unbiased material recovery. Nevertheless, its variability and descriptive RMS proxy improved relative to Raw. The planned H2 prediction of worsened quantitation was not supported for D1 in these experiments. The more limited finding is that variance reduction and residual bias must be reported separately. Residual bias is evidence against quantitative equivalence, not sufficient evidence that denoising worsened every quantitative measure.

{{TABLE2}}

### 3.3. Added spectral loss and H3

D2 retained detectability gains but did not provide a consistent recovery of iodine fidelity relative to D1. At full count, D2's positive deviations were +0.343, +0.629, and +0.387 mgI/mL across increasing insert sizes. D1's corresponding deviations were +0.034, −0.057, and −0.266 mgI/mL. At quarter count, D2 deviations were −1.960, −1.674, and −1.869 mgI/mL: the larger inserts improved relative to D1, while the smallest did not. Thus, the loss did not fail identically in every condition; it failed as a general recovery strategy under the specified selection rule.

The secondary spectral residual also worsened. D1 residuals were about 0.38–0.39 HU at full count and 0.94–0.95 HU at quarter count. D2 residuals were approximately 1.05–1.28 and 5.26–5.29 HU, respectively. The quarter-count increase was approximately 5.6-fold. A material-coordinate penalty does not directly penalize every component orthogonal to those coordinates. H3 was not supported as a joint detectability-and-quantitation claim.

Figure 4 places detectability and the descriptive material-error proxy on separate axes. TV combined high background-noise-derived observer values with large negative material deviations. D2 moved to a different operating point rather than uniformly dominating D1. The figure is a trade-off display, not proof of a globally optimal Pareto frontier: only three specified processing methods and a fixed training protocol were sampled.

### 3.4. Walnut reconstruction experiment and H4

Figure 5 shows a fixed slice, index 530, at 40 keV with a common −500 to +500 HU display window. Selection followed the established central-slice preview index, not a search for favorable performance. Quantitative panels use all 60 slices. Table 3 presents both nominal count settings. At 25%, mean VMI RMSE fell from 680.1 HU for Raw to 132.0 HU for D1w and 196.8 HU for TV. Whole-image SSIM increased from 0.047 to 0.654 and 0.644, respectively.

In the pulp ROI, D1w bias was −3212.5 and mean within-ROI SD was 1989.3 on the calibration-table material scale, compared with Raw bias +2.2 and SD 20439.6. The resulting proxy fell from 20439.6 to 3778.6. The improved total-error proxy therefore accompanied a much larger systematic bias. These are material-map differences relative to the supplied reconstruction, not independently measured walnut composition.

At 12.5%, D1w mean SSIM decreased to 0.318, whereas TV remained approximately 0.641. D1w still reduced RMSE relative to Raw, illustrating that RMSE and structural similarity ranked the extrapolation behavior differently. H4 supports the limited observation that denoising can reduce variability and apparent image error while introducing systematic material shifts. It does not replicate the primary arm's energy-optimum result because no walnut detection task was evaluated, nor does it support D1's unsupported H2 prediction by substitution of a different model and material.

{{TABLE3}}

### 3.5. Sensitivity analyses

Eye-filter changes retained the low-energy frozen-template D1 optimum across the saved conditions, while amplitude scaling and channelized observers exposed additional dependence on signal transfer. The 12.5% analyses showed large attenuation ratios, including polarity reversals at energies where noiseless contrast was small. A ratio with a small denominator can be unstable; it should not be interpreted as a literal amplification factor without the underlying contrast values. These observations reinforce the need to distinguish frozen-template gains from preserved task information. Complete saved sensitivity records accompany the numerical source data; no clinical robustness claim is inferred from the observer sweep.

## 4. Discussion

### 4.1. What changes when spectral images are denoised

The main finding is that strong noise suppression can reshape a detectability-energy curve without preserving all the quantities that curve is intended to represent. Under a frozen signal template, D1 shifted the optimum from 60 to 40 keV in every primary condition. Once measured contrast was included, one optimum moved instead to the high-energy boundary. The appropriate inference is conditional: the low-energy preference was consistent for the specified frozen-template metric, but it was not invariant to how signal preservation was represented.

This matters for energy selection. An “optimal keV” should be accompanied by its task definition, input extent, template convention, observer, and material endpoint. Reporting only the most favorable energy after denoising hides whether processing changed the task itself. In this study, showing the entire grid and both template conventions made an exception visible that a single representative low-energy panel would miss. The high-energy boundary maximum also signals that the sampled grid may truncate the mathematical maximum; it should not be converted into a recommendation to image at 190 keV.

Large observer values deserve particular restraint. A non-prewhitening observer can benefit from preprocessing that suppresses noise components it otherwise handles inefficiently. However, deterministic processing cannot create information absent from the input for an ideal observer with the correct likelihood model. Here, the stationary background-NPS approximation and retained template shape do not supply that likelihood model. The very high TV estimates, despite material suppression, identify a limitation of the evaluation approximation as well as a processing trade-off. Direct observer scores on independent signal-present and signal-absent ensembles would be an appropriate subsequent validation step.

### 4.2. Precision, accuracy, and spectral consistency

The results also distinguish precision from accuracy without presuming that denoising must damage quantitation. H2 was a plausible concern, but D1 reduced both variability and the descriptive RMS deviation in these experiments. Its remaining quarter-count bias should be reported, while the unsupported worsening prediction should be rejected. Recasting all residual bias as confirmation of H2 would replace the original hypothesis after observing the results.

Spectral residuals add a different kind of information. A stack lying in the two-basis subspace can still encode the wrong material concentration. Conversely, a stack with a modest residual may yield a useful material estimate after projection. The primary raw residual is zero because the images were constructed from two bases, not because the raw measurements are perfect. D2's additional coordinate penalty did not guarantee a smaller off-subspace residual and introduced full-count material bias. The failure is specific to the implemented loss, β grid, validation criterion, and training duration; it does not establish that all physics-informed or spectral-consistency losses fail.

The practical response is to choose processing against explicit acceptance criteria for each intended use. For visual review, an image-similarity endpoint may be relevant. For iodine measurement, bias and variability against a suitable reference are required. For task detection, signal transfer and task-specific noise should be checked. A small subspace residual is a supporting diagnostic rather than a substitute for these endpoints. The framework supplies the measurements needed for that choice; it does not derive a universal operating point.

### 4.3. Meaning of the walnut evidence

The walnut arm adds measured object structure and a different acquisition system, but several adaptations prevent it from being a conventional external validation. Its low-count conditions are simulated by adding stationary noise to an already processed reference. Its VMI coefficients were fitted to supplied images, and its network input offsets were estimated from evaluation slices. The model was retrained for two bins and a different spectrum. These steps are transparent components of a reconstruction-based stress test, not evidence that an unchanged model transfers to a new scanner.

Within that scope, the material bias–variance exchange is informative. The noisy material inversion amplified fluctuations because the calibration matrix was ill-conditioned. Denoising greatly reduced those fluctuations while moving regional means. At the lower nominal count level, the disagreement between D1w RMSE and SSIM further showed that one aggregate appearance metric could conceal structural degradation. The appropriate next experiment is a locked pipeline evaluated on separate specimens or measured repeat acquisitions, with calibration and distribution adaptation completed before opening the test set.

### 4.4. Limitations

The primary simulator used ideal two-bin detection, parallel-beam geometry, water and iodine, and a single tube spectrum. It omitted detector imperfections, scatter, anatomical clutter, motion, and scanner reconstruction complexity. Its very high incident-count parameter was selected to avoid an extremely starved low-energy bin after heavy filtration; its count fractions are not a patient-dose calibration. VMIs above the tube endpoint are basis-model extrapolations, rather than directly measured monoenergetic acquisitions. These factors limit transfer of absolute values and energy optima to clinical systems.

Nonlinear signal and noise behavior is only partially captured by background NPS and a scalar template correction. The latter cannot represent shape changes or signal-dependent covariance. The mean contrast used for amplitude scaling is estimated from the same finite ensemble; this analysis does not quantify uncertainty in its resulting energy maximum. The study also evaluated one trained realization per final model and did not measure training-seed variability. No human-reader comparison or clinical lesion-detection endpoint was acquired.

The walnut arm contains one specimen and adjacent slices, with one injected realization per slice. Its material reference is a calibration-table transformation of the same bins, not independent chemical truth. The supplied material-series mismatch requires clarification with the dataset maintainers before any claim about the source's correctness. NPS-profile outputs in the walnut tool use a custom discrete normalization; they are retained as secondary descriptive records and are not presented here as calibrated physical NPS measurements. Whole-image SSIM includes background, whereas RMSE and material measurements use restricted regions; this difference must be retained when comparing metrics.

Finally, the original plan contained broader or provisional descriptions that differ from the executable study: independent single-energy networks became a joint-channel model; the D2 target was redefined before training; 50% was not a primary endpoint condition; and the optional clinical NPS comparison was not included. These differences are disclosed to prevent the plan from being mistaken for completed evidence. They do not justify changing the frozen hypotheses or suppressing unsupported outcomes.

## 5. Conclusions

In the specified PCCT simulation, denoising changed energy-dependent observer estimates and substantially reduced iodine variability, while residual bias and signal transfer remained condition dependent. A basis-coordinate loss did not consistently recover material fidelity, and a walnut reconstruction stress test showed improved image error together with systematic material shifts and poorer extrapolation SSIM. Energy selection after denoising should therefore be evaluated jointly with signal preservation and material accuracy. The present evidence supports that evaluation strategy; it does not establish clinical benefit, a universal optimal energy, or a validated patient-dose reduction.

## Acknowledgements

The public dataset and open-source software used in this work are cited in the reference list. No additional individual acknowledgement is included in this draft.

## Author Contributions

Proposed for author confirmation: Shuji Yamamoto — conceptualization, methodology, software, investigation, formal analysis, visualization, and writing. Final responsibility for the manuscript rests with the author.

## Statements and Declarations

### Ethical considerations

This study used synthetic phantoms and publicly available walnut reconstruction data. No human participants, human tissue, or patient records were included. Institutional human-research approval was not required for these materials; this statement requires author confirmation before submission.

### Consent to participate

Not applicable.

### Consent for publication

Not applicable.

### Declaration of conflicting interest

Author confirmation required: disclose relevant employment, ownership, financial interests, and other potential conflicts. The proposed institutional affiliation is LISIT Co., Ltd.; a blanket no-conflict statement has not been inferred from the study design.

### Funding statement

Author confirmation required: identify all financial and in-kind support, or confirm that no specific grant supported this research.

### Data availability

The source walnut dataset is available at https://doi.org/10.5281/zenodo.17328375. The study code and frozen result JSON files are held in the pcct-vmi-core repository. A public, reachable code locator and the exact version archive DOI must be verified and inserted before submission. Source images are not redistributed in this manuscript package. Acquisition instructions are provided in docs/DATA.md.

### Declaration of generative AI use

OpenAI Codex assisted with manuscript drafting, code preparation, and local checks. The author must verify all claims, citations, numerical outputs, and final wording and confirm the complete list of tools used during the earlier research stages. Generative AI is not an author. Independent Codex–Claude review of this manuscript package has not been completed.

## References

{{REFERENCES}}

## Figure captions

Figure 1. Two analysis paths. The primary simulation evaluates model-observer response and iodine deviations across 40–190 keV. The walnut arm adds simulated correlated noise to supplied two-bin reconstructions and evaluates VMI and material-map differences across 10–80 keV. The networks are separately trained, and the walnut experiment does not include a detection endpoint.

Figure 2. Complete primary detectability curves for all insert sizes and count settings. Solid/dashed lines denote frozen noiseless templates; dotted lines use measured contrast to scale the same spatial template. All curves display nonnegative magnitudes, harmonizing the primary and TV output conventions. A symmetric logarithmic axis with a linear region below one displays the large dynamic range. Signal-transfer signs remain in the source data. Background-NPS assumptions after nonlinear processing limit interpretation of absolute values.

Figure 3. Iodine deviation from matched noiseless baselines, by insert size and count setting. Points show means across 64 realizations and error bars show realization SD, not confidence intervals. The estimate is obtained from the full 16-energy basis fit and therefore is not a separate per-energy concentration measurement.

Figure 4. Descriptive detectability–material trade-off. Each point represents one insert size (labels in mm). The horizontal coordinate is maximum amplitude-scaled detectability magnitude across the full energy grid; the vertical coordinate is sqrt(mean deviation² + realization SD²), converted to mgI/mL. Polarity reversals are not distinguished by the magnitude coordinate and require the signal-transfer records. The sampled methods do not define a universal Pareto frontier.

Figure 5. Walnut reconstruction stress test at nominal 25% count setting. Top: fixed slice 530, the established central preview index within slices 500–559, with common 40-keV window −500 to +500 HU and identical field of view for reference, Raw, D1w, and TV. Selection was not based on method performance. Bottom: mean regional bias and mean within-region pixel SD across all 60 slices, on the calibration-table material scale; these error bars are not inter-specimen uncertainty. The images contain measured walnut structure plus simulated added noise.
