# SV08 Architecture Notes

## Onboard Computer

The SV08 mainboard contains an **Allwinner H616 ARM SoC** running Linux. This is the onboard computer — it is not a separate Raspberry Pi. It runs the full Klipper stack:

| Software | Role |
|----------|------|
| Klipper | Motion planning, communicates with MCU for real-time stepper control |
| Moonraker | REST/WebSocket API — how external software sends commands to the printer |
| Mainsail | Browser-based UI for manual control and config editing |
| Crowsnest | Camera streaming (MJPEG over HTTP) |

## Two-Chip Architecture

The H616 is **not** the chip driving the stepper motors directly. There is a separate MCU on the same board that handles real-time stepper pulse generation. The H616 talks to the MCU over a serial connection (`ttyS3`).

```
H616 (Linux, Klipper host) --> serial --> MCU --> step/dir pulses --> stepper drivers --> motors
```

## Accessing the H616

- **SSH** over the local network (IP shown in Mainsail or via `get_ip.sh`)
- **Mainsail web UI** for config file editing and manual control
- Klipper config changes are made by editing `.cfg` files — no firmware recompile needed

## Moonraker API

The Raspberry Pi sends motion commands to the printer via the Moonraker HTTP/WebSocket API rather than raw G-code over serial. This is the interface `rpi/motion/` and `rpi/pipette/` will use.

- Moonraker docs: https://moonraker.readthedocs.io

## Camera

The onboard camera is managed by Crowsnest and streamed as MJPEG over HTTP on the local network. `rpi/camera/` consumes this stream for CV processing — no direct camera hardware connection needed on the Pi.

## Source

- [Sovol SV08 GitHub](https://github.com/Sovol3d/SV08)
