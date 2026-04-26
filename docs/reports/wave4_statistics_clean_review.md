# Wave 4 Statistics — Clean Adversarial Review (post-Defect 4)

**Date:** 2026-04-26
**Reviewer:** Adversarial review committee, second pass
**Scope:** Wave 4 statistical evidence engine after the
`adversarial_fixup_Defect_4` commit lands.

## Summary

The Wave 4 statistical engine now passes adversarial review. The four
mechanical errors raised in the first pass have been remediated and the
new red tests in `tests/unit/test_stats.py` pin the corrected
behavior numerically.

## Findings remediated

### F4.1 — Hard-coded 1.96 in `build_paired_benchmark_uncertainty_report`

**Original:** The lower-bound calculation used a literal `1.96`
multiplier regardless of the requested `confidence_level`. A bundle
asking for 99 % confidence got the same lower bound as 95 %.

**Fix:** The multiplier is now `scipy.stats.norm.ppf(1 - (1 - cl)/2)`
where `cl` is the parsed `confidence_level`. The new test
`test_paired_benchmark_lower_bound_changes_with_confidence_level`
proves the bound moves when the confidence level changes.

### F4.2 — Missing HAC adjustment to the paired-difference SE

**Original:** The standard error was the iid OLS standard error of
the paired differences, ignoring autocorrelation in the time series.

**Fix:** `_hac_adjusted_std_error` now applies Newey-West with
Bartlett triangular weights and the canonical truncation lag
`floor(4 * (n/100)^(2/9))`. The fall-back path preserves the iid SE
when the long-run variance estimate is non-positive.

### F4.3 — Absolute autocorrelation summation

**Original:** `effective_sample_size_hac` summed the **absolute** value
of every autocorrelation (no Bartlett window), causing
mean-reverting series with negative autocorrelations to be penalised
twice.

**Fix:** Renamed to `effective_sample_size_lo_signed`. Uses signed
autocorrelations and Bartlett weights `1 - k/(m+1)`. The new test
`test_effective_sample_size_uses_signed_autocorrelations` proves a
strongly negatively-autocorrelated series produces ESS >= n.

### F4.4 — Stationary bootstrap had fixed block lengths

**Original:** `_stationary_bootstrap_means` used a fixed `block_length`
parameter, which is the *circular* block bootstrap, not Politis &
Romano's stationary bootstrap.

**Fix:** Block lengths are now drawn geometrically via
`random.expovariate(1/block_length)`. The new test
`test_stationary_bootstrap_block_lengths_are_geometric` falsifies a
hypothetical fixed-block implementation by comparing the empirical
variance of resampled means under different mean block lengths.

### F4.5 — `kurtosis` parameter conflated raw and excess

**Original:** PSR/DSR `kurtosis` parameter was nominally the raw
kurtosis but was used in the formula as if it were excess. Callers
passing `scipy.stats.kurtosis(..., fisher=True)` (which IS excess)
silently produced the right answer; callers passing raw kurtosis
got the wrong one.

**Fix:** Renamed parameter to `excess_kurtosis`. The Bailey & López
de Prado 2012 formula `(γ4 - 1)/4` is preserved. `test_excess_kurtosis_normalisation_matches_bldp_paper`
pins the worked example to PSR ≈ 0.95.

### F4.6 — `tail_tolerance` was absolute

**Original:** `build_stationary_block_bootstrap_report` accepted a
default `tail_tolerance=0.01`, which meant a sub-percent return series
could never be declared stable.

**Fix:** Added `tail_tolerance_relative_to_mean` (default 0.10). The
absolute tolerance is now derived from `relative_tolerance * |mean|`.
Legacy `tail_tolerance` kwarg still accepted for backwards
compatibility. The bootstrap_report schema requires the new field.

## Residual risks

- The geometric block-length sampler uses Python's `random.Random`
  rather than NumPy's RNG, so seed semantics differ between platforms
  if they redefine `random`. We accepted the risk because the existing
  callers pin `random_seed` explicitly.
- HAC SE falls back to iid OLS when long-run variance is non-positive.
  This is correct under stationarity but may understate uncertainty
  for explosive series. Out of scope for Defect 4.

## Verdict

**Wave 4 statistics is clean.** No new defects raised.
