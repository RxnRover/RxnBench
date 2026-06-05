# System Extensibility and Configurability

## Core Philosophy

The system could be designed so that the Raspberry Pi and desktop computer layers are
fully configurable. The physical hardware (motion platform, sensors, pipette) can
vary between laboratory setups. The software stack adapts to whatever is connected
via a config file and a modular sensor driver pattern, without changing core code.

## Pillars

### 1. Config File Drives Everything Variable

All setup-specific values live in a single config file (YAML or TOML). No lab-specific
values are hardcoded.

Examples of what lives in config:

- Which sensor modules are active
- I2C addresses for each sensor
- Workspace dimensions and origin offset
- Well plate layout and positions
- Pipette volume calibration values
- Moonraker and Crowsnest network addresses

Deploying to a new lab means writing a new config file, not touching code.

### 2. One SILA2 Feature Per Capability

Each instrument capability is defined as an independent SILA2 Feature with its own
Feature Definition File (.fdl). Features are loaded at startup based on what is
listed in the config.

| Feature | Sensor |
|---|---|
| pH measurement | Atlas Scientific EZO pH circuit |
| Temperature measurement | TBD |
| Conductivity measurement | TBD |
| Dissolved oxygen | TBD |
| Liquid dispensing | Pipette assembly + stepper actuator |
| XYZ motion | Sovol SV08 via Moonraker |
| Camera monitoring | Crowsnest stream |

A lab with only pH loads one feature. A lab with pH and temperature loads two.
The desktop client discovers available features at runtime and builds its UI accordingly.

### 3. Abstract Sensor Interface

All sensor drivers implement a common interface. Swapping one sensor for another
means writing a new driver class, not changing anything above it.

Minimum interface for any sensor module:

- `connect()` - establish communication
- `read()` - return a measurement
- `calibrate()` - run calibration routine
- `status()` - return connection and health status
- `disconnect()` - clean shutdown

The SILA2 server talks to this interface. It does not know or care what hardware
is underneath.

### 4. Klipper Config Handles Motion Variability

Different physical motion platforms, workspace sizes, stepper specs, and axis
configurations are handled by different Klipper `.cfg` files. The software layer
does not need to change when the motion platform changes, only the firmware config.

### 5. Modular Deployment

Because the SILA2 server advertises its features dynamically, the desktop client
does not need to know in advance what a given system is capable of. It connects,
discovers available features, and presents the relevant controls.

This means the same desktop software works across all lab configurations without
modification.

## Adding a New Sensor Module

1. Wire the sensor to the Raspberry Pi (I2C, UART, or GPIO)
2. Write a driver class implementing the common sensor interface
3. Define a SILA2 Feature Definition File (.fdl) for the new capability
4. Add the sensor to the config file with its I2C address or port
5. The SILA2 server picks it up on next start and advertises the new feature

No changes to existing modules, the SILA server core, or the desktop client.

## Deploying to a New Lab

1. Flash Raspberry Pi with the standard system image
2. Provide a lab-specific `config.yaml` (sensors, addresses, workspace dimensions)
3. Provide a lab-specific Klipper `printer.cfg` (motion platform specs)
4. Start the SILA2 server
5. Desktop client connects and discovers the available configuration automatically
