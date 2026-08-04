# dosing_pump

Atlas Scientific **EZO-PMP** embedded peristaltic dosing pump, exposed as the `DosingPump` SiLA feature on port **50054**.

- **`backend/`** — `rxn_bench_dosing_pump` SiLA2 server package. See [backend/README.md](backend/README.md) for the command set, wiring, and how to run it.
- **`frontend/`** — PySide6 device plugin: a hand-built widget with dispense / dose-over-time / flow-rate controls, live dispensed volume, and totals.

## Hardware at a glance

| | |
|---|---|
| Flow rate | 0.5 – 105 ml/min open-loop (with the supplied tubing) |
| Metered rate ceiling | Lower than 105, reported by `DC,?`, set by calibration |
| Smallest dispense | 0.5 ml |
| Accuracy | ±1% (after calibration) |
| Data protocol | UART (implemented) or I2C, ASCII |
| UART default | 9600 baud, 8N1, CR-terminated |
| Power | 3.3–5.5 V logic **and** 12–24 V motor (two supplies) |

Datasheet: [docs/datasheets-manuals/EZO-PMP/EZO_PMP_Datasheet.pdf](../../docs/datasheets-manuals/EZO-PMP/EZO_PMP_Datasheet.pdf)

## Operating modes

All four datasheet modes are exposed:

| Mode | SiLA command | EZO command |
|---|---|---|
| Volume dispensing | `Dispense(Volume)` | `D,[ml]` |
| Dose over time | `DoseOverTime(Volume, Minutes)` | `D,[ml],[min]` |
| Constant flow rate | `SetFlowRate(Rate, Minutes)` | `DC,[ml/min],[min\|*]` |
| Continuous dispensing | `DispenseContinuously(Reverse)` | `D,*` / `D,-*` |

Dispense-at-startup (`Dstart`) is deliberately not exposed — it configures the pump to run on power-up without a client, which works against having the bench drive it.

### Two different maxima

These are easy to conflate:

- **~105 ml/min** — the pump's *open-loop* top speed with the supplied tubing, and the datasheet cover's "0.5ml to 105ml/min". This is what **Continuous** (`D,*`) runs at. It takes no rate argument; the motor just runs flat out.
- **`MaxFlowRate` (`DC,?`)** — the fastest rate the pump can *regulate* to in **Constant rate** mode. Substantially lower (the datasheet's example is 58.5 ml/min) and "determined after calibration". Asking `SetFlowRate` for more returns `*TOOFAST`.

So a rate you can *hold* is always below the rate the pump can *reach*. To run continuously **at a chosen rate**, use Constant rate with an open-ended duration (`DC,[rate],*`) — not Continuous:

```python
bench.pump.set_flow_rate(2.0)        # 2 ml/min until stopped
bench.pump.dispense_continuously()   # ~105 ml/min until stopped, rate not settable
```

## Quick start

```bash
# from rxnbench/backend
RXN_BENCH_MOCK=1 uv run --package rxn-bench-dosing-pump rxn-bench-dosing-pump
make test-pump
```

From an experiment script:

```python
from rxn_bench_client import RxnBenchClient, DosingPump

with RxnBenchClient() as bench:
    bench.connect("pump", DosingPump, server="Dosing Pump")
    bench.pump.dispense_and_wait(5.0)      # blocks until delivered
    bench.log(dispensed=bench.pump.total_volume())
```

## Reusing this for a different pump

Everything except the driver is model-agnostic, because the frontend is matched to the **SiLA feature**, not the hardware: `rxn_bench_ui` discovers plugins by comparing advertised feature identifiers against `FEATURE_FRAGMENTS`. Any server advertising `DosingPump` gets this widget.

So a second pump model needs **one new driver class and one registry line** — no new frontend code, proto, connection layer, or client class:

1. Write a driver satisfying [`DosingPumpProtocol`](backend/src/rxn_bench_dosing_pump/interfaces.py) (12 methods).
2. Register a builder for it in `_DRIVERS` in [`server.py`](backend/src/rxn_bench_dosing_pump/server.py), then select it with `RXN_BENCH_PUMP_DRIVER=<key>`.

If the new pump also happens to be a distinct physical device you want running *alongside* the EZO-PMP, give it its own `devices/<name>/` with its own port and config — but still register the same `DosingPump` feature, and it reuses the same widget automatically.

### What the core interface deliberately excludes

`DosingPumpProtocol` covers only what any dosing pump can do (dispense by volume / over time / at a rate / continuously, pause, stop, totals, state). Three things are **opt-in capability protocols**, because they aren't universal:

| Capability protocol | Methods | Why it's optional |
| --- | --- | --- |
| `SupportsCalibration` | `calibrate`, `clear_calibration`, `calibration_status` | Many pumps are calibrated externally or not at all |
| `SupportsDirectionInvert` | `set_inverted`, `is_inverted` | A *persistent* direction flip is an EZO feature; most pumps just take a signed volume |
| `SupportsDiagnostics` | `pump_voltage` | Motor supply sensing; a syringe pump has no equivalent |

They're `runtime_checkable`, so the feature tests them with `isinstance` and rejects just those commands — with a message naming what's missing — on a pump that lacks them. The SiLA surface stays identical for every model, so one proto and one widget serve all of them.

## Two things to check before running real hardware

1. **Serial port.** The reference bench already runs the EZO-pH on the Pi's primary UART (`/dev/serial0` → `/dev/ttyAMA0`). The pump needs its own port — a second PL011 (`dtoverlay=uartN` in `/boot/firmware/config.txt`) or a USB-serial adapter — set via `RXN_BENCH_PUMP_SERIAL_PORT`. On the reference Pi 5, `dtoverlay=uart2` puts UART2 on GPIO4/5 as `/dev/ttyAMA2`; confirmed against the real EZO-PMP 2026-08-04 (`?I`, `?STATUS`, and `PV,?` all responded correctly, motor supply read 11.99 V). `install_service.sh` sets this port automatically for the `pump` service.
2. **Calibration.** An uncalibrated pump's volumes are nominal. Dispense into a graduated container, then send the measured volume with `Calibrate`. `MaxFlowRate` is only meaningful after calibration.
