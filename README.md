# Rxn Bench - DIY Automated Chemistry Bench

![Rxn Bench logo](docs/images/resized/logo.png)

## Overview

Rxn Bench is a DIY automated chemistry bench built on a repurposed Sovol SV08 3D printer as the XYZ motion platform, with a pipette toolhead for liquid handling and an Atlas Scientific probe for pH sensing. A Raspberry Pi on the printer runs Klipper/Moonraker plus SiLA2 device servers for the gantry and pH sensor; a separate operator machine runs a PySide6 frontend that talks to those servers over gRPC/SiLA, and experiment scripts drive the bench through a Python client package.

## Requirements

- A Sovol SV08 3D printer (or similar Klipper-based motion platform) and a Raspberry Pi 5 to control it
- Python 3.10+ and [`uv`](https://docs.astral.sh/uv/) on both the Pi (backend) and the operator machine (frontend)
- Atlas Scientific EZO pH kit and 3D-printed mounts (see Component List below) for pH sensing hardware

## Usage

See [docs/usage.md](docs/usage.md) for commands to install dependencies and start the backend servers (real or mocked) and the frontend UI.

## Implementation and design

![Rxn Bench high-level system block diagram: operator UI talks to the Raspberry Pi's SILA server, which drives the Sovol SV08 MCU (XYZ motion + liquid handler arm), an onboard camera, and the EZO pH circuit/probe](docs/images/resized/system-block-diagram.jpg)

See [docs/ai/CURRENT_STATE.md](docs/ai/CURRENT_STATE.md) for the current architecture, package layout, and active gaps.

### Component List

**Motion Platform**

| Name | Link | Purpose |
| ---- | ---- | ------- |
| SV08 3D Printer | [MatterHackers](https://www.matterhackers.com/store/l/sovol-sv08-enclosed-pre-assembled-3d-printer/sk/MQ7MC2AK?rcode=PMAX_GENPOP3DP&gad_source=1&gad_campaignid=20506454105) | XYZ motion platform base for liquid handler automation |
| Raspberry Pi 5 | [PiShop](https://www.pishop.us/product/raspberry-pi-5-8gb/?src=raspberrypi) | Main controller for coordinating motion and sensors |

**pH Sensor**

| Name | Link | Purpose |
| ---- | ---- | ------- |
| Atlas Scientific EZO Micro pH Kit | [Atlas Scientific](https://atlas-scientific.com/kits/micro-ph-kit/)| Complete kit for pH measurement |
| Atlas Scientific EZO pH Circuit | [Atlas Scientific](https://atlas-scientific.com/embedded-solutions/ezo-ph-circuit/) | Embedded pH signal processing circuit |
| pH Isolation Board | [Atlas Scientific](https://atlas-scientific.com/carrier-boards/electrically-isolated-ezo-carrier-board-gen-2/) | Electrically isolates pH circuit to prevent noise/interference |
| Half-Cell pH Isolation Board | [Atlas Scientific](https://atlas-scientific.com/carrier-boards/half-cell/) | Carrier board for half-cell pH probe configurations |
| Spear Tip pH Probe | [Atlas Scientific](https://atlas-scientific.com/probes/spear-tip-ph-probe/) | Soil/spear-tip combination electrode; male SMA connector, mates directly to isolation carrier board |

**Liquid Handler**

| Name | Link | Purpose |
| ---- | ---- | ------- |
| Pipette Cone Assembly   | [PipetteSupplies](https://www.pipettesupplies.com/product/e1-clip-tip-tip-cone-assembly-single-channel-1250-l-t/) | Actual liquid displacement mechanism |
| Stepper Linear Actuator | [Haydon Kerk Pittman](https://www.haydonkerkpittman.com/products/linear-actuators/can-stack-stepper)              | Pushes the pipette plunger to aspirate/dispense liquid         |

**Extra Peripherals**

| Name | Link | Purpose |
| ---- | ---- | ------- |
| SMA Male-to-Female Extender Cable | [Atlas Scientific](https://atlas-scientific.com/accessories/sma-extender/) | Extends the probe cable reach from the carrier board to the mounted probe |
| | |
 
**Other components/items**

| Name | Link | Purpose |
| ---- | ---- | ------- |
| Bambu Lab A1 | [BambuLabs](https://bambulab.com/en-us/a1) | Unmodified used to 3D print platforms, plates, etc. |

## Gallery

### Assembled bench

| Assembled, pipette over a well plate | Running on the bench next to the operator laptop |
| --- | --- |
| ![Assembled Rxn Bench with the pipette toolhead positioned over a well plate](docs/images/resized/assembled-bench-1.jpg) | ![Rxn Bench running on the lab bench next to the operator laptop running the frontend UI](docs/images/resized/assembled-bench-2.jpg) |

### pH probe toolhead

CAD design next to the assembled 3D-printed housing around the Atlas Scientific EZO pH circuit and probe.

| CAD design | Assembled |
| --- | --- |
| ![CAD render of the pH probe toolhead, exploded to show the EZO pH circuit board inside](docs/images/resized/ph-toolhead-cad.jpg) | ![Assembled 3D-printed pH probe toolhead housing](docs/images/resized/ph-toolhead-assembled.jpg) |

### Toolhead docking mount

The gantry docks toolheads via a 3D-printed linear-rail mount, in the spirit of the tool-changer designs linked below.

| CAD design | Assembled |
| --- | --- |
| ![CAD render of the toolhead docking mount with linear rail bearings](docs/images/resized/docking-mount-cad.jpg) | ![Assembled 3D-printed toolhead docking mount](docs/images/resized/docking-mount-assembled.jpg) |

### Rxn Bench UI

#### Main interface

![Rxn Bench UI main screen showing the Gantry widget, pH Sensor widget, and Experiment Runner widget](docs/images/resized/ui-main.jpg)

#### Sensor and control widgets

| Gantry | pH Probe | Experiment Runner |
| --- | --- | --- |
| ![Gantry view](docs/images/resized/ui-gantry.jpg) | ![pH Probe view](docs/images/resized/ui-ph-probe.jpg) | ![Experiment Runner view](docs/images/resized/ui-experiment-runner.jpg) |

#### Adding a device

![Add Device view](docs/images/resized/ui-add-device.jpg)

## References and helpful material

**Core**
- [How to convert a 3D printer to a personal automated liquid handler for life science workflows](https://www.sciencedirect.com/science/article/pii/S2472630324001213#bib0043)
- [SILA Standard](https://sila-standard.com/standards/)
- [SILA Standard GitLab](https://gitlab.com/SiLA2)
- [Klipper Firmware](https://www.klipper3d.org/)
- [SOVOL SV08 GitHub](https://github.com/Sovol3d/SV08)
- [Raspberry Pi Docs](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)
- [Crowsnest](https://docs.mainsail.xyz/crowsnest/)
- [Moonraker](https://moonraker.readthedocs.io/en/latest/)
- [Pipette Clip Tip](https://www.thermofisher.com/us/en/home/life-science/lab-plasticware-supplies/pipettes-pipette-tips/pipette-tips/products/cliptip-pipette-system.html)

**Related open-source lab automation projects**
- [Rxn Rover](https://rxnrover.github.io/) - Ames National Lab Automation Platform
- [Science Jubilee](https://science-jubilee.readthedocs.io/) - open-source tool-changing lab robot with pipette, camera, and sensor tools
- [Jubilee: An Extensible Machine for Multi-tool Fabrication (paper)](https://www.researchgate.net/publication/341697828_Jubilee_An_Extensible_Machine_for_Multi-tool_Fabrication)
- [Automated Liquid Handler from a 3D Printer - Journal of Chemical Education](https://pubs.acs.org/doi/10.1021/acs.jchemed.3c00855)
- [E3D Tool Changer R&D](https://e3d-online.com/blogs/news/research-and-development-motion-system-and-tool-changer) - commercial tool-changer that inspired Jubilee's docking mechanism
- [GitHub - totaldesaster/toolchanger](https://github.com/totaldesaster/toolchanger) - low-cost 3D-printed tool changer mechanism
- [EvoBot: Open-Source Modular Liquid Handling Robot](https://www.mdpi.com/2076-3417/10/3/814)
- [Open-source personal pipetting robots (Nature Communications)](https://www.nature.com/articles/s41467-022-30643-7)


## Authors and Contributors

John Brittain

Felisha Kuo

Zachery Crandall

Lun An

David Lee

Long Qi