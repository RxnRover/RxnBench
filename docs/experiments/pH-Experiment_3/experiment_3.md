# Rxn Bench pH Experiment 3

**Date:** July 24, 2026

**Personnel:** John Brittain, Felisha Kuo

## Objective

Cross-check the automated pH probe against an independent, manually
operated ThermoScientific benchtop meter across 18 samples spread over
three 6-well plates, and adopt two-point calibration (mid + low only) as
recommended out of Experiment 1's action items.

## Equipment & Materials

- Rxn Bench Gantry
- Atlas Scientific pH probe
- ThermoScientific benchtop pH meter (manual reference measurement)
- Calibration buffers: pH 4.00, 7.00 (no pH 10.00 point this run)
- Distilled water (rinse)
- Workspace: `6x3_18-well_wWash.yaml` (three 6-well plates -
  `6-well1`/`6-well2`/`6-well3` - plus a 3-well calibration holder and wash
  station)

## Procedure

1. Loaded the `6x3_18-well_wWash.yaml` workspace (three `6_well_sample_25ml`
   plates arranged side by side, a 3-well calibration holder, and a wash
   station).
2. Ran a **two-point** calibration only - mid (pH 7.00) then low (pH
   4.00) - with the high (pH 10.00) point commented out in the script,
   implementing Experiment 1's recommendation directly.
3. Read all 6 wells of `6-well1`, then `6-well2`, then `6-well3` in turn
   (18 wells total), rinsing the probe at the wash station between every
   well.
4. Each well was also measured manually with a ThermoScientific benchtop
   meter, recorded alongside the automated reading in
   `pH-Experiment 3 (18 samples).xlsx`.

## Results

### Automated vs. manual reference

| Well | RxnBench pH | ThermoScientific pH | \|Δ\| |
|---|---|---|---|
| 6-well1/A1 | 1.56 | 1.57 | 0.01 |
| 6-well1/A2 | 1.56 | 1.57 | 0.01 |
| 6-well1/A3 | 1.55 | 1.57 | 0.02 |
| 6-well1/B1 | 1.02 | 0.99 | 0.03 |
| 6-well1/B2 | 0.96 | 1.00 | 0.04 |
| 6-well1/B3 | 1.01 | 0.99 | 0.02 |
| 6-well2/A1 | 1.70 | 1.74 | 0.04 |
| 6-well2/A2 | 1.72 | 1.72 | 0.00 |
| 6-well2/A3 | 1.70 | 1.72 | 0.02 |
| 6-well2/B1 | 1.73 | 1.73 | 0.00 |
| 6-well2/B2 | 1.68 | 1.71 | 0.03 |
| 6-well2/B3 | 1.70 | 1.71 | 0.01 |
| 6-well3/A1 | 1.51 | - | - |
| 6-well3/A2 | **0.00** | - | - |
| 6-well3/A3 | 3.83 | 4.07 | 0.24 |
| 6-well3/B1 | 2.94 | 3.03 | 0.09 |
| 6-well3/B2 | 1.96 | 2.03 | 0.07 |
| 6-well3/B3 | 1.04 | 1.05 | 0.01 |

16 of 18 wells have a paired manual reading. Over those 16:

- Mean absolute difference: **0.04 pH**
- Median absolute difference: **0.02 pH**
- Largest disagreement: **0.24 pH** at `6-well3/A3` (3.83 vs. 4.07)
- 12 of 16 pairs agree within 0.03 pH

Two wells have no recorded comparison: `6-well3/A1` (automated reading
1.51, no manual pairing recorded) and `6-well3/A2` (automated reading
**0.00**, no manual pairing recorded either). A pH of exactly 0.00 is not
a plausible sample value here - this is almost certainly a failed/invalid
reading (probe not submerged, a dropped connection mid-read, or similar),
not a real measurement.

## Discussion

- **Accuracy is good where it worked:** excluding the one clear failure,
  automated and manual readings agree to within 0.04 pH on average across
  16 samples spanning roughly pH 1-4, which is a solid validation of the
  probe/toolhead setup against an independent instrument.
- **One outlier (`6-well3/A3`, 0.24 pH off):** worth a closer look -
  it's the single largest gap by a wide margin (next-largest is 0.09) and
  sits in the same plate as the failed `A2` reading, which may point to a
  shared cause (e.g., carryover from the failed well, or a probe/mixing
  issue specific to `6-well3`).
- **The `0.00` reading at `6-well3/A2`** should be treated as an
  instrumentation fault, not a data point. It's the same failure mode
  worth watching for in later experiments (see Experiments 4 and 5, which
  also show occasional near-zero or exactly-zero outlier readings).
- **No settling-time record preserved:** the script logs a `settling_time`
  column for each well (same as Experiments 1 and 4), but the archived
  workbook only kept `timestamp, well, ph` - if the raw
  `ph_calibration.csv` / `ph_sample.csv` are still available, worth
  re-exporting with settling time included for consistency with the other
  experiments.

## Action Items (Next Experiment)

- Investigate the `6-well3/A2` zero-reading failure and the adjacent
  `A3` outlier - check whether they're related (e.g., probe fouling,
  incomplete submersion, or a rinse that didn't fully clear carryover).
- Preserve the `settling_time` column when exporting results to Excel, to
  keep timing data comparable across experiments.
- Given two-point calibration performed well here, keep it as the default
  going forward rather than reverting to three-point.

## Appendix: Raw Data

No console log was archived for this run; results were compiled directly
into `pH-Experiment 3 (18 samples).xlsx` (sheet 1: raw
timestamp/well/pH; sheet 2: RxnBench vs. ThermoScientific comparison,
reproduced above). Workflow script: `pH_calibrate_and_sample.py`.
Workspace: `6x3_18-well_wWash.yaml`.
