# Rxn Bench pH Experiment 5

**Date:** August 5, 2026

**Personnel:** John Brittain, Felisha Kuo

## Objective

Repeat Experiment 4's three-plate, 50-well layout (`24-well1` rows A-B,
`24-well2` and `24-well3` rows A-D) the next day, as a reproducibility
check on both the sample readings and the near-zero anomaly seen in
`24-well3` the day before.

## Equipment & Materials

Same as Experiment 4: Rxn Bench Gantry, Atlas Scientific pH probe,
dosing pump, wash station, and the same three-plate workspace.

## Procedure

Same well sequence as Experiment 4 - `24-well1` (rows A-B, columns 2-6),
then `24-well2` and `24-well3` (rows A-D, columns 2-6) - rinsing between
every well. No calibration record (`ph_calibration.csv`) was preserved
for this run, so it's unclear from the data alone whether calibration was
re-run or the prior day's calibration was reused.

## Results

All 50 wells produced a reading; total run time was **3931.5 s (65.5
min)** from the first to the last timestamp, averaging 78.6 s/well
end-to-end (no per-well settling time was logged this run, unlike
Experiment 4).

### The `24-well3` two-band pattern reproduces

Exactly like Experiment 4, `24-well3` splits cleanly into two bands: rows
A-B read low (**0.11-0.23**) and rows C-D read high (**0.82-0.97**):

| Row | pH range (Exp 4) | pH range (Exp 5) |
|---|---|---|
| A-B | 0.01-0.17 | 0.11-0.23 |
| C-D | 0.74-0.85 | 0.82-0.97 |

Seeing the same two-band split, in the same rows, on a different day
strengthens the reading from Experiment 4: this looks like a genuine
property of what's loaded into `24-well3` (two distinct sample groups in
rows A-B vs. C-D), not a one-off drift or fault.

### A new pattern: elevated readings at the start of each row

Lining Experiment 4 and 5 up side by side, the first well sampled in each
row (`A2`, `B2`, `C2`, `D2` - since column 1 is skipped) reads noticeably
higher than the rest of that row, and this effect is much more
pronounced in Experiment 5:

| Well | Exp 4 pH | Exp 5 pH | Rest-of-row pH (Exp 5) |
|---|---|---|---|
| `24-well2/A2` | 1.43 | **1.89** | 1.40-1.41 (A3-A6) |
| `24-well2/B2` | 1.43 | **1.91** | 1.41-1.53 (B3-B6) |
| `24-well2/C2` | 1.62 | **2.53** | 1.59-1.62 (C3-C6) |
| `24-well2/D2` | 1.62 | **2.52** | 1.61-1.68 (D3-D6) |
| `24-well1/A2` | 1.73 | **2.89** | 1.64-1.69 (A3-A6) |
| `24-well1/B2` | 1.65 | **2.74** | 0/1.64-1.67 (B3-B6, B3 failed) |

Each row transition is also the largest single gantry move in the
sequence (column 6 of one row back to column 2 of the next), so the
probe spends the longest stretch away from a sample between these
readings. That's a plausible instrumentation explanation - more time at
the wash station or in transit before the first read of a row - but it's
a hypothesis from the timing pattern, not a confirmed cause.

### Recurring zero-reading fault

`24-well1/B3` read exactly **0.00**, the same failure signature seen in
Experiment 3 (`6-well3/A2` = 0.00) and the near-zero cluster in
Experiment 4. This is now the **second exact 0.00 reading** across three
experiments.

## Discussion

- **Reproducibility is good where the readings are trustworthy:** the
  `24-well3` two-band structure held up on a repeat run, which is a
  genuinely useful confirmation.
- **The row-start elevation effect is new information from having two
  runs to compare** - it wasn't visible as anything more than noise in
  Experiment 4 alone. It should be checked directly rather than
  theorized about further: instrument identical wells at a row-start
  position vs. a mid-row position and compare.
- **Zero-reading fault is now a 2-for-3 pattern** across Experiments 3-5
  (exact 0.00 in Experiments 3 and 5, near-zero cluster in Experiment 4).
  This has crossed the threshold from "one weird reading" to something
  that should be actively debugged rather than filtered out after the
  fact.

## Action Items (Next Experiment)

- Test the row-start elevation hypothesis directly: add a short
  "settle and discard" read at the first well of each row before logging
  it, or log the full pre-read trace (as in Experiment 2) for row-start
  wells specifically to see whether they're still drifting when read.
- Root-cause the recurring 0.00 fault (see Experiment 4's action items -
  now higher priority given a second occurrence).
- Preserve `ph_calibration.csv` for every run, even when calibration is
  skipped/reused, so that assumption doesn't have to be inferred later.

## Appendix: Raw Data

`results/ph_sample_08052026.csv` - 50 rows, `timestamp,well,ph`. No
calibration log or console log was archived for this run.
