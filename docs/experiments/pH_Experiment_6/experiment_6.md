# Rxn Bench pH Experiment 6

**Date:** August 6, 2026

**Personnel:** John Brittain, Felisha Kuo

## Objective

Run a full two-point calibration followed by pH sampling across all 72
wells of three complete 24-well plates (all rows A-D, all columns 1-6 -
unlike Experiments 4 and 5, column 1 was included this time), and, in
doing so, gather the settling-time data needed to confirm the row-start
elevation effect flagged as an open question in Experiment 5.

## Equipment & Materials

- Rxn Bench Gantry
- Atlas Scientific pH probe
- Calibration buffers: pH 4.00, 7.00
- Workspace with three full 24-well plates (`24-well1`, `24-well2`,
  `24-well3`) plus a wash station and calibration holder
- `pH_calibrate_and_sample.py`, run from the **packaged Windows build**
  (`Rxn Bench.exe`) rather than a dev checkout - the first experiment in
  this series run from the installed application instead of source,
  which is itself a useful data point for the packaging work described in
  the project's architecture notes.

## Procedure

1. Ran a two-point calibration (mid pH 7.00, then low pH 4.00).
2. Read every well, all 6 columns × 4 rows, on `24-well1`, then
   `24-well2`, then `24-well3` - 72 wells total, rinsing between every
   well. The run completed in one continuous attempt (no failed prior
   attempts, unlike Experiment 4).

## Results

### Calibration

| Point | Known pH | Reading before | Reading after | Settling time |
|---|---|---|---|---|
| Mid | 7.00 | 7.17 | 6.98 | 51.4 s |
| Low | 4.00 | 4.03 | 4.01 | 63.1 s |

### Sample readings

All 72 wells were read successfully over **9880.5 s (164.7 min ≈ 2 h 45
min)**. Values cluster around three nominal levels depending on column -
roughly pH 4.0, pH 6.8-7.0, and pH 7.6-8.3 - repeating in a consistent
column-wise pattern across most rows; full readings are in
`results/ph_sample_3.csv`.

### Settling-time pattern: row-start wells confirmed

This run settles the question raised in Experiment 5. **Column-1 wells -
the first well read in each row - took on average 2.6× longer to settle
than every other well:**

| Group | n | Mean settle time |
|---|---|---|
| Column-1 wells (row start) | 12 | **188.1 s** |
| All other wells | 60 | 73.2 s |
| Overall | 72 | 92.3 s (min 21.9 s, max 383.5 s) |

And the effect fades over the course of the run:

| Plate | Mean settle time (all wells) | Mean settle time (column-1 only) |
|---|---|---|
| `24-well1` (1st plate) | 140.3 s | **350.4 s** |
| `24-well2` (2nd plate) | 71.0 s | 147.5 s |
| `24-well3` (3rd plate) | 65.7 s | 66.5 s (effect essentially gone) |

On `24-well1`, every single column-1 well (`A1`, `B1`, `C1`, `D1`) took
326-384 s to settle, roughly 6-7× the plate's typical mid-row well; by
`24-well3`, column-1 wells settle in the same range as everything else.

## Discussion

- **This confirms Experiment 5's row-start hypothesis with much cleaner
  data.** Because this run included column 1 (Experiments 4-5 skipped
  it), the row-start well and the "large gantry move" well are the same
  well here, and the settling-time data shows the effect directly rather
  than inferring it from pH values. Whatever causes it, it's tied to the
  row-to-row transition - the largest single move in the sampling
  sequence - not to sample chemistry.
- **The effect fades plate over plate**, not row over row: `24-well1`'s
  row starts stay slow all the way through (`D1` is just as slow as
  `A1`), but by `24-well3` the effect is gone entirely. That points more
  toward something that improves with sustained operation over the
  session (probe/toolhead warming up, wetting in, or the rinse cycle
  settling into a steady rhythm) than a per-row mechanical cause, since a
  purely mechanical (gantry-move-distance) explanation would predict the
  same slowdown on every plate, not just the first one.
- **Two occasional anomalies within otherwise-declining rows**
  (`24-well1/C3` at 226.4 s and `D3` at 337.7 s, both well above their
  immediate neighbors) don't fit the row-start pattern - those are
  mid-row, not column 1. Worth a second look, but not enough evidence
  here to say more than "flagged."
- **Clean run, packaged build:** unlike Experiment 4, this run completed
  on the first attempt with no connection drops or toolhead-confirmation
  errors, and it's the first of this series run from the installed
  Windows executable rather than a source checkout - a useful positive
  data point for the packaging work.

## Action Items (Next Experiment)

- Treat the row-start settling penalty as a real, load-bearing effect:
  either budget for it explicitly (don't assume a fixed settle timeout
  works equally well for every well position), or investigate adding a
  brief "pre-soak" dwell before starting a new row so the first reading
  isn't the slowest one.
- Since the effect fades after the first plate, consider whether a short
  warm-up sequence before the first plate (e.g., one throwaway read-and-
  discard cycle) would remove it entirely rather than just tolerating it
  on plate 1.
- Look into the two off-pattern mid-row spikes (`24-well1/C3`, `D3`) -
  possibly the same large-composition-jump effect seen in Experiment 4's
  `24-well3/C2`.

## Appendix: Raw Console Output

Full log: `logs/pH_calibrate_and_sample_20260806_132301.log`. Excerpt
showing the column-1 slowdown at the start of the run:

```text
Starting pH calibration script with 2 points...
Clearing any prior calibration...
Waiting for probe to settle...
Probe settled in 51.4 seconds.
Calibrating mid point in Calibration/A2 (known pH 7.00) - current reading is 7.17
 mid @ pH  7.00: before=7.17  after=6.98
Waiting for probe to settle...
Probe settled in 63.1 seconds.
Calibrating low point in Calibration/A3 (known pH 4.00) - current reading is 4.03
 low @ pH  4.00: before=4.03  after=4.01
Reading pH of 24 wells in the 24-well1 plate...
Waiting for probe to settle in 24-well1/A1...
Probe settled in 383.5 seconds.
24-well1/A1: pH 6.83
Rinsing probe in Wash-Station/A1...
Waiting for probe to settle in 24-well1/A2...
Probe settled in 220.4 seconds.
24-well1/A2: pH 7.64
...
Reading pH of 24 wells in the 24-well3 plate...
Waiting for probe to settle in 24-well3/A1...
Probe settled in 38.3 seconds.
24-well3/A1: pH 6.97
...
24-well3/D6: pH 4.02
Rinsing probe in Wash-Station/A1...
Completed in 9880.5 seconds.

# Finished - 2026-08-06T16:07:46.323139
```

Full 72-well readings: `results/ph_sample_3.csv`. Calibration record:
`results/ph_calibration_6.csv`.
