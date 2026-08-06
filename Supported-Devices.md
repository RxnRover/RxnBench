# Supported devices registry

Rxn Bench splits each device into a **capability** (a SiLA feature + Protocol
interface + Qt widget, hardware-agnostic) and one or more **drivers** (a
concrete implementation of that capability's Protocol, registered under a
`rxn_bench.<capability>_drivers` entry-point group). A driver also owns
anything specific to its physical product: the vendor's wire protocol, its
hardware CAD (`hardware_models/`), and its toolhead config if it mounts on
the gantry. See [docs/ai/CURRENT_STATE.md](docs/ai/CURRENT_STATE.md) §1-2 for
the full architecture writeup.

This table is the index: which capability a driver plugs into, and which
repo each half lives in (`devices/<name>/{capability,driver}` in this
checkout - currently git submodules pointing at local paths pending GitHub
hosting).

| Capability | Package | Driver | Package | Entry point | Hardware |
| --- | --- | --- | --- | --- | --- |
| Gantry (motion) | `rxn-bench-gantry` | Moonraker/Klipper | `rxn-bench-moonraker-driver` | `moonraker` | SOVOL SV08 3D printer |
| pH sensing | `rxn-bench-ph` | Atlas Scientific EZO-pH | `rxn-bench-atlas-ezo-ph-driver` | `atlas_ezo` (I2C or UART) | Atlas Scientific EZO-pH circuit + Spear Tip probe |
| Camera | `rxn-bench-camera` | Crowsnest webcam stream | `rxn-bench-crowsnest-camera-driver` | `crowsnest` | Any Crowsnest-managed USB webcam |
| Dosing pump | `rxn-bench-dosing-pump` | Atlas Scientific EZO-PMP | `rxn-bench-atlas-ezo-pmp-driver` | `atlas_ezo_pmp` (+ `atlas_ezo_pmp_mock`) | Atlas Scientific EZO-PMP peristaltic pump |

Each capability is reusable beyond its current reference driver - a different
pH probe, camera, or dosing pump brand plugs in by adding a new driver
package that implements the same Protocol and registers under the same
entry-point group, with **zero changes** to the capability's feature, proto,
client, or Qt widget. `devices/device_template/capability/` is the reference
scaffold for a brand-new capability that doesn't fit any of the above; see
the `new-device` dev-agent skill for the checklist (existing-interface check
first, template copy only if it's a genuine misfit).
