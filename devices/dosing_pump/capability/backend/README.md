# rxn-bench-dosing-pump

SiLA2 server for the **Atlas Scientific EZO-PMP** embedded peristaltic dosing pump. Runs on port 50054.

## Layout

```text
src/rxn_bench_dosing_pump/
├── server.py                       ← create_app(); selects mock vs real UART
├── _cli.py                         ← rxn-bench-dosing-pump entry point
├── feature.py                      ← DosingPump SiLA feature
├── interfaces.py                   ← DosingPumpProtocol (hardware contract)
├── atlas_dosing_pump.py            ← Protocol implementation over a command driver
├── ezo_pmp_commands.py             ← transport-agnostic EZO-PMP command set
├── atlas_scientific_uart_driver.py ← EZO-PMP over UART/serial
├── mock_uart.py                    ← EZO-PMP protocol emulator (simulates dispensing)
├── mock_device.py                  ← MockDosingPump: the real stack over the emulator
└── session_log.py                  ← append-only JSONL event log
```

The layering mirrors `rxn_bench_ph`: a transport-agnostic command set plus one transport class. That structure is duplicated rather than imported from the pH package on purpose — the two share a *vendor protocol family*, not a command set, and per `docs/ai/CURRENT_STATE.md` §8 device backends stay independently deployable.

## Running

```bash
# Mock (no hardware; dispensing is simulated against the wall clock)
RXN_BENCH_MOCK=1 uv run --package rxn-bench-dosing-pump rxn-bench-dosing-pump

# Real hardware (from rxnbench/backend)
make start-pump

# Tests
make test-pump
```

### Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `RXN_BENCH_MOCK` | unset | `1` uses the simulated pump |
| `RXN_BENCH_PUMP_SERIAL_PORT` | `/dev/serial0` | Serial device for the EZO-PMP |
| `RXN_BENCH_PUMP_BAUD` | `9600` | EZO UART default |

> **Serial port contention:** the bench's EZO-pH already owns `/dev/serial0`. Give the pump its own UART (`dtoverlay=uartN` in `/boot/firmware/config.txt`) or a USB-serial adapter and set `RXN_BENCH_PUMP_SERIAL_PORT`, or the two will fight over the same bytes. On the reference Pi 5, `dtoverlay=uart2` brings up UART2 on GPIO4/5 as `/dev/ttyAMA2` — confirmed against real EZO-PMP hardware 2026-08-04. `install_service.sh` sets `RXN_BENCH_PUMP_SERIAL_PORT=/dev/ttyAMA2` for the `pump` service automatically.

## SiLA surface

**Observable properties** — `VolumeDispensed` (ml, polled 1 Hz), `Dispensing` (bool).

**Unobservable properties** — `TotalVolume`, `AbsoluteTotalVolume`, `PumpVoltage`, `MaxFlowRate`, `Paused`, `Inverted`.

**Commands** — `Dispense`, `DoseOverTime`, `DispenseContinuously`, `SetFlowRate`, `Stop` (returns the volume delivered), `SetPaused`, `SetInverted`, `ClearTotalVolume`, `Calibrate`, `ClearCalibration`, `GetCalibrationStatus`.

Dispense commands return as soon as the pump accepts them; the pump keeps running. Watch `Dispensing` to know when a dose is actually finished.

### Driver-only commands (not on the SiLA feature)

`find()`, `set_led()`/`get_led()`, `sleep()`/`wake()`, and `set_protocol_lock()`/`get_protocol_lock()` exist on the driver and `AtlasDosingPump` but are deliberately not exposed over SiLA — they identify or power-manage the *circuit* rather than dose liquid. This matches `rxn_bench_ph`, which keeps the same group driver-level only.

- `find()` blinks the LED to tell this circuit apart from the pH one on the same bench. Per the datasheet it also disables continuous reporting — harmless, since the driver already turns that off at startup.
- `sleep()` drops the control system from ~13.4 mA to ~0.415 mA at 5 V. It does **not** cut the 12–24 V motor supply, so it is not a way to make the pump safe to handle.
- **`wake()` is required after `sleep()`.** The byte that wakes a sleeping EZO is consumed doing so and is not executed — the circuit replies `*WA` instead of the expected answer, so the command is silently lost. `wake()` absorbs that throwaway exchange; without it, the first command after sleeping fails with a timeout. `MockEZOPumpUart` reproduces this, so the path is tested rather than assumed.

Deliberately **not** implemented: `Baud`, `Factory`, `Name`, and the I2C-mode switch (they reconfigure the circuit in ways that can strand the connection mid-run), `O` (enable/disable output parameters — it changes the output string format that `R` parsing depends on), and `Dstart` (dispense-at-startup makes the pump run on power-up without a client, working against having the bench drive it).

## Protocol notes worth knowing

- **`*DONE` is both a reply and an interrupt.** It is the only response to `X` (stop), *and* it arrives unsolicited whenever a dispense finishes on its own. The driver treats it as a reply only when the command in flight expects one (`done_terminates`); otherwise it is recorded in `last_completed_volume` and skipped, so a dose completing mid-query can't corrupt an unrelated reading.
- **`P` and `Invert` are toggles.** `AtlasDosingPump.set_paused` / `set_inverted` read the current state first, so callers can assert a desired state instead of tracking parity.
- **Rejections aren't plain `*ER`.** `*MINVOL` (below the 0.5 ml minimum) and `*TOOFAST` (above the calibrated maximum) are raised as `ValueError` with the cause spelled out.
- **Continuous reporting is disabled at startup** (`C,0`), like the pH driver, so reads stay clean request/response.
- Every command uses a uniform 300 ms processing delay — unlike the EZO-pH, where reads need 900 ms.
- **`MaxFlowRate` is not the pump's top speed.** `DC,?` reports the fastest rate the pump can *regulate* to in constant-rate mode (datasheet example: 58.5 ml/min, "determined after calibration"). Continuous dispensing (`D,*`) bypasses regulation and runs open-loop at ~105 ml/min — the cover spec's figure. `MockEZOPumpUart` keeps the two separate: `max_flow_rate` (default 58.5) gates `DC`, while `_CONTINUOUS_RATE` (105) drives `D,*`. To run continuously at a *chosen* rate, use `DC,[rate],*` — Continuous takes no rate argument.

## Calibration

Single-point, against the volume actually delivered:

1. `Dispense(10)` into a graduated container.
2. Measure what really came out, e.g. 9.4 ml.
3. `Calibrate(9.4)`.

`GetCalibrationStatus` returns 0 uncalibrated, 1 fixed volume, 2 volume-over-time, 3 both. `MaxFlowRate` is only meaningful once the pump is calibrated.
