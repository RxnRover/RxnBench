# Rxn Bench pH Experiment 1

**Date:** July 15, 2026

**Personnel:** John Brittain, Felisha Kuo

## Objective

Perform a fully automated three-point calibration of the Atlas Scientific pH
probe, then use the calibrated probe to read 24 samples spanning pH 1-4 in a
24-well plate.

## Equipment & Materials

- Rxn Bench Gantry
- Atlas Scientific pH probe
- Tecan XLP 6000 syringe pump
- Rxn Rover
- Calibration buffers: pH 4.00, 7.00, 10.00
- Distilled water (rinse)

## Procedure

1. Cleared any prior probe calibration.
2. Ran an automated three-point calibration (mid 7.00, low 4.00, high 10.00), rinsing the probe in the wash station between each point.
3. Read all 24 wells of the sample plate, rinsing between wells.

The Tecan XLP 6000 was set to a dosing rate of 10 mL / 30 s to match the
gantry's 30 s wait time, allowing the probe to be rinsed with distilled water
between wells.

## Results

### Calibration

Slope: **(97.7, 89.5)** - acid 97.7%, base 89.5%.

| Point | Known pH | Reading before | Reading after | Settling time |
|-------|----------|----------------|---------------|---------------|
| Mid   | 7.00     | 7.02           | 7.00          | 93.4 s        |
| Low   | 4.00     | 4.08           | 4.00          | 124.5 s       |
| High  | 10.00    | 9.68           | 10.01         | 155.6 s       |

The high point required the largest correction (9.68 -> 10.01), consistent with
the lower base slope (89.5%).

### pH Sample Readings

All 24 wells read successfully. Values ranged from pH 1.12 to 4.08.

| Well | pH   | Well | pH   | Well | pH   | Well | pH   |
|------|------|------|------|------|------|------|------|
| A1   | 3.19 | B1   | 1.18 | C1   | 2.04 | D1   | 1.12 |
| A2   | 3.09 | B2   | 1.15 | C2   | 3.92 | D2   | 3.89 |
| A3   | 3.07 | B3   | 1.15 | C3   | 1.18 | D3   | 2.05 |
| A4   | 4.01 | B4   | 1.96 | C4   | 1.99 | D4   | 2.97 |
| A5   | 4.06 | B5   | 2.03 | C5   | 2.95 | D5   | 1.12 |
| A6   | 4.08 | B6   | 2.07 | C6   | 3.96 | D6   | 2.88 |

## Discussion

The experiment was mostly successful, though a few non-ideal conditions were
noted:

- **Wash station drain** is not draining properly.
- **Pump synchronization:** the pump cannot be triggered programmatically, so it
  must be left in continuous dosing mode. This drifts out of sync whenever the
  in-chamber reservoir empties and has to refill.
- **Waste capacity:** 500 mL of waste is not enough for a full run with the
  syringe pump. Increase to ~800 mL or use less water per rinse.

## Action Items (Next Experiment)

- Switch to two-point calibration.
- Tighten tolerances for stable readings.
- Fix the crossbar safety.
- Level the gantry.
- Address wash-station drainage and waste-capacity issues above.

## Appendix: Raw Console Output

Results directory:
`~/Documents/John/work/Ames_National_Labs/Automated_Chem_Bench/rxnbench/frontend/dist/Rxn Bench/results`

### Calibration (`ph_calibration.csv`)

```text
Logging results to ~/.../results/ph_calibration.csv
Starting pH calibration script with 3 points...
Note: It is important that the pH probe is fully submerged into the solution, and that the solution is well-mixed before taking a reading.
      If the pH probe is not submerged increase the amount of solution, or adjust the engagement depth
Clearing any prior calibration...
Waiting for probe to settle...
Probe settled in 93.4 seconds.
Calibrating mid point in Calibration/A2 (known pH 7.00) - current reading is 7.02
 mid @ pH  7.00: before=7.02  after=7.00
Rinsing probe in Wash-Station/A1...
Waiting for probe to settle...
Probe settled in 124.5 seconds.
Calibrating low point in Calibration/A3 (known pH 4.00) - current reading is 4.08
 low @ pH  4.00: before=4.08  after=4.00
Rinsing probe in Wash-Station/A1...
Waiting for probe to settle...
Probe settled in 155.6 seconds.
Calibrating high point in Calibration/A1 (known pH 10.00) - current reading is 9.68
high @ pH 10.00: before=9.68  after=10.01
Rinsing probe in Wash-Station/A1...

[Finished]
```

### pH Readings (`ph_samples.csv`)

```text
Logging results to ~/.../Rxn Bench/results/ph_samples.csv
Reading pH of 24 wells in the 24-Well plate...
24-well/A1: pH 3.19
24-well/A2: pH 3.09
24-well/A3: pH 3.07
24-well/A4: pH 4.01
24-well/A5: pH 4.06
24-well/A6: pH 4.08
24-well/B1: pH 1.18
24-well/B2: pH 1.15
24-well/B3: pH 1.15
24-well/B4: pH 1.96
24-well/B5: pH 2.03
24-well/B6: pH 2.07
24-well/C1: pH 2.04
24-well/C2: pH 3.92
24-well/C3: pH 1.18
24-well/C4: pH 1.99
24-well/C5: pH 2.95
24-well/C6: pH 3.96
24-well/D1: pH 1.12
24-well/D2: pH 3.89
24-well/D3: pH 2.05
24-well/D4: pH 2.97
24-well/D5: pH 1.12
24-well/D6: pH 2.88

[Finished]
```
