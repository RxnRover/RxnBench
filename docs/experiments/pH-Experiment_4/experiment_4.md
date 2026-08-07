# Rxn Bench pH Experiment 4

**Date:** August 4, 2026

**Personnel:** John Brittain, Felisha Kuo

## Objective

Run a full two-point calibration followed by pH sampling across three
24-well plates (50 filled wells total), using an updated workflow script
that adds dosing-pump-assisted rinsing and skips known-empty wells.

## Equipment & Materials

- Rxn Bench Gantry
- Atlas Scientific pH probe
- Atlas Scientific EZO-PMP dosing pump (rinse water)
- Calibration buffers: pH 4.00, 7.00
- Workspace with three 24-well plates (`24-well1`, `24-well2`,
  `24-well3`) plus a wash station and calibration holder
- `pH_calibrate_and_sample.py` (updated version, `workflow script/` - adds
  `DosingPump` support and a well filter to skip unfilled column 1)

## Procedure

1. Loaded the active workspace and connected to the gantry, pH probe, and
   dosing pump SiLA servers.
2. Ran a two-point calibration (mid pH 7.00, then low pH 4.00).
3. Read every filled well (column ≥ 2, all rows) across all three 24-well
   plates in turn - 10 wells in `24-well1` (rows A-B only), then 20 wells
   each in `24-well2` and `24-well3` (rows A-D) - rinsing between every
   well.
4. This was the **5th attempt** of the day; the first four failed before
   any sample data was collected (see Discussion).

## Results

### Calibration

| Point | Known pH | Reading before | Reading after | Settling time |
|---|---|---|---|---|
| Mid | 7.00 | 6.99 | 7.01 | 91.3 s |
| Low | 4.00 | 4.21 | 3.99 | 36.7 s |

### Sample readings

All 50 filled wells were read successfully (in the sense that the script
did not error), across a run lasting **4686.3 s (78.1 min)** end to end.
Per-well probe-settling time (the portion of each well spent waiting for
a stable reading, excluding travel/rinse) averaged **38.9 s** overall (min
18.6 s, max 102.1 s), broken down by plate:

| Plate | Wells | Mean settle time | Notes |
|---|---|---|---|
| `24-well1` | 10 (rows A-B) | 44.3 s | pH ~1.55-1.73 |
| `24-well2` | 20 (rows A-D) | 46.9 s | Two bands: ~1.36-1.43 (rows A-B), ~1.55-1.62 (rows C-D) |
| `24-well3` | 20 (rows A-D) | 28.1 s (24.2 s excl. outlier) | See anomaly below |

`24-well3` is the standout: rows A-B read essentially **0.01-0.17 pH**
(10 wells), then rows C-D jump to **0.74-0.85 pH** (10 wells). The
transition well, `24-well3/C2`, also has by far the longest settle time
in the run - 102.1 s vs. a 18-33 s range for its neighbors - consistent
with the probe needing much longer to cross a large actual pH step
between `B6` (0.01) and `C2` (0.74) rather than any external interruption.

Full readings are in `results/ph_sample.csv`; calibration in
`results/ph_calibration.csv`.

## Discussion

- **Four failed attempts before success.** In order:
  1. `150102` - dosing pump SiLA server not discoverable within 5 s
     (not running / not reachable on the network).
  2. `150258` - `SilaConnectionError` mid-rinse, manually interrupted
     (`KeyboardInterrupt` in the log).
  3. `162122` - same `SilaConnectionError` mid-rinse, again manually
     interrupted.
  4. `163530` - `ToolheadNotMountedError`: the pH toolhead's mount
     hadn't been confirmed (`ConfirmToolheadMounted`/`mount_toolhead`)
     before a well-targeted move, which the gantry now enforces as a
     safety interlock.
  5. `164049` - succeeded end to end.

  Two distinct root causes are visible here: an intermittent SiLA/gRPC
  connection drop during rinse moves (attempts 2-3), and a workflow gap
  where the operator needs to explicitly confirm toolhead mounting before
  the first move each session (attempt 4). Both are worth hardening
  before the next long run - see Action Items.
- **The `24-well3` near-zero band (A2-B6, 10 wells at pH 0.01-0.17) is
  worth flagging, not just noting.** A pH this close to 0 is physically
  extreme for a general sample; it may be a real (very concentrated
  acid) sample, or it may indicate the probe was still carrying over
  from a prior very-acidic exposure, or drifting at the low end of its
  range after a long run. The clean, sharp transition to the 0.74-0.85
  band at `C2` argues against simple drift (drift would look gradual, not
  a step), which points more toward the plate genuinely containing two
  distinct sample groups - but this should be confirmed against the
  intended plate layout rather than assumed.
- **This is the same near/at-zero pattern seen in Experiment 3**
  (`6-well3/A2` = exactly 0.00) and recurs again in Experiment 5's
  `24-well1/B3`. Three occurrences across three experiments is enough to
  treat this as a recurring failure mode worth root-causing on its own,
  independent of whatever any individual well's true sample pH is.

## Action Items (Next Experiment)

- Add a startup check (or clearer error message) for the dosing pump
  server before the script proceeds, instead of failing 5 s in with a
  generic discovery error.
- Investigate the intermittent `SilaConnectionError` during rinse moves -
  happened twice in one day.
- Make the toolhead-mount confirmation step an explicit, visible part of
  the script's startup sequence (or the run instructions) so it isn't
  discovered only via a mid-run error.
- Root-cause the recurring near-zero/exactly-zero pH reading (three
  occurrences across Experiments 3-5) - check probe range at very low
  pH, rinse effectiveness after strongly acidic wells, and whether it
  correlates with specific wells/plates or is a genuine sample property.

## Appendix: Raw Console Output

Full logs for all five attempts are preserved in `logs/`. Excerpt from
the successful run (`pH_calibrate_and_sample_20260804_164049.log`):

```text
Starting pH calibration script with 2 points...
Clearing any prior calibration...
Waiting for probe to settle...
Probe settled in 91.3 seconds.
Calibrating mid point in Calibration/A2 (known pH 7.00) - current reading is 6.99
Waiting for probe to settle...
Probe settled in 36.7 seconds.
Calibrating low point in Calibration/A3 (known pH 4.00) - current reading is 4.21
...
Waiting for probe to settle in 24-well3/B6...
Probe settled in 18.6 seconds.
24-well3/B6: pH 0.01
Rinsing probe in Wash-Station/A1...
Waiting for probe to settle in 24-well3/C2...
Probe settled in 102.1 seconds.
24-well3/C2: pH 0.74
...
24-well3/D6: pH 0.83
Rinsing probe in Wash-Station/A1...
Completed in 4686.3 seconds.

# Finished - 2026-08-04T17:58:57.094833
```

Full 50-well readings: `results/ph_sample.csv`. Calibration record:
`results/ph_calibration.csv`. Timelapse video of the run:
`pH-Experiment_4 (Timelapse) .MOV`.
