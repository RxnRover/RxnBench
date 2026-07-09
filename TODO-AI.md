# Rxn Bench TODO Roadmap

## 1. Prototype / First Product Release Blockers

### 1.1 Reliable Z-axis referencing, clearance, and tool engagement

Current status:
Rxn Bench can navigate accurately in the X/Y plane to selected wells, but high-density formats like 96-well plates require very precise calibration. The current Z-reference method probes the bottom of the base plate/tool area, which is finicky and can cause overly strict movement denial even when enough clearance appears to exist.

Needed work:

* Rethink the Z homing/reference model.
* Consider referencing Z from a safe plane slightly above the highest labware or well feature instead of the lowest reachable plate surface.
* Define labware geometry more explicitly:

  * plate height
  * well depth
  * safe travel height
  * operation depth
  * toolhead offset
  * clearance padding
* Add configurable safety padding for human measurement error.
* Ensure the toolhead cannot collide with labware during travel moves.
* Support toolheads with different sizes, lengths, and operation depths.
* Add visual workspace views for:

  * X/Y plane
  * X/Z side view
  * Y/Z side view
* Show configured labware, toolhead clearance, safe travel height, and operation depth visually.

Acceptance criteria:

* User can configure labware/toolhead dimensions without relying on fragile manual Z probing.
* System can calculate safe travel and operation positions.
* Unsafe moves are blocked for clear reasons.
* User can visually inspect whether the workspace is configured correctly.

---

### 1.2 Executable frontend and offline backend installation

Frontend:

* Package the frontend as a standalone executable application.
* Required target:

  * Windows
* Optional targets:

  * Linux
  * macOS

Backend:

* Backend should be easy to install on a Raspberry Pi.
* Installation should work headlessly.
* Installation should be fully offline once the installer/package is prepared.
* One simple install command should:

  * install required packages
  * configure services
  * open/configure required ports
  * install device backends
  * install drivers
  * configure discovery
  * start required SiLA servers
* Backend should run as a service.
* Service should restart automatically after crashes or reboot.

Acceptance criteria:

* Fresh Raspberry Pi can be set up with minimal manual steps.
* Frontend can connect to backend without developer tooling.
* Backend services survive reboot.
* System can run without internet access.

---

### 1.3 Raspberry Pi / IT setup notes

Create a short IT-facing setup document containing:

* Required operating system and version.
* Required packages/imports/install steps.
* Local network requirements.
* Required ports.
* Services used.
* mDNS/discovery behavior.
* What the Raspberry Pi exposes on the network.
* How the backend starts and restarts.
* Security assumptions.
* Offline installation notes.

Acceptance criteria:

* An IT/admin person can understand what the Pi does on the network.
* Required ports and services are clearly documented.
* Setup does not depend on tribal knowledge.

---

### 1.4 Repository cleanup

Clean the codebase before release.

Tasks:

* Remove overly wordy comments.
* Remove temporary notes, TODO clutter, and fix-me text where possible.
* Replace AI-generated-sounding comments with short human-readable explanations.
* Remove redundant code.
* Ensure naming is consistent across the repo.
* Simplify files that became over-engineered.
* Remove evidence of messy prototyping where it does not help future development.

Acceptance criteria:

* Code comments explain why something exists, not obvious behavior.
* Naming is consistent across backend, frontend, devices, and docs.
* Dead/redundant code is removed.
* Repo feels intentional, not like an archaeological dig with Wi-Fi.

---

### 1.5 Documentation cleanup

Tasks:

* Update main documentation to match current behavior and architecture.
* Ensure `current_state.md` is accurate.
* Update per-device READMEs.
* Remove overly device-specific wording from generic device docs.
* Avoid hardcoded language like:

  * “on the Raspberry Pi”
  * “on the SOVOL SV08”
* Make docs describe generic device classes and interfaces where possible.
* Keep device-specific setup only where truly necessary.

Acceptance criteria:

* Documentation matches the actual architecture.
* Generic devices are documented generically.
* Device-specific notes are separated from reusable interface docs.

---

## 2. New Device Implementations

### 2.1 Generic camera device

Initial target: Crowsnest camera stream on the SOVOL SV08.
Architecture should remain generic so other cameras can be supported later.

Tasks:

* Create generic camera interface.
* Implement Crowsnest API/client support.
* Create Camera Feature / SiLA server.
* Add Rxn Bench client support.
* Add logging support.
* Support image capture at intervals.
* Create frontend camera widget.
* Keep implementation boilerplate and consistent with existing device templates.
* Design scaffolding with future machine-vision tasks in mind:

  * error detection
  * run monitoring
  * workspace inspection
  * calibration assistance

Acceptance criteria:

* Camera device works through the same general device architecture as other devices.
* Crowsnest is one implementation, not the whole abstraction.
* UI can view camera output and log images.
* Future CV/error-detection work can build on the interface.

---

### 2.2 New Device Agent Skill

Create an AI/dev-agent skill for implementing new Rxn Bench devices.

Tasks:

* Create `skills.md`.
* Have the skill read the generic device template.
* Have the skill read the new-device user manual/context.
* Require the skill to check existing interfaces before creating new ones.
* If a device fits an existing interface, reuse it.

  * Example: a pH probe should use the existing pH device interface/UI/mock server if available.
* Keep generated implementations simple.
* Avoid over-engineering.

Acceptance criteria:

* Agent can scaffold a new device in the existing project style.
* Agent does not create unnecessary new abstractions.
* Agent prefers existing interfaces and UI patterns.

---

### 2.3 AI-assisted New Device client

Create a small chatbox-style UI that helps implement new devices using an active AI model.

Tasks:

* Add frontend chatbox UI.
* Let the AI assistant reference the New Device Agent Skill.
* Guide the user through:

  * choosing an existing interface
  * creating a new device scaffold
  * adding mock server behavior
  * adding client support
  * adding UI support
* Keep this feature isolated so it does not complicate the main architecture.

Acceptance criteria:

* User can describe a new device and get guided implementation help.
* Feature supports the existing project conventions.
* It does not become a giant “AI magic box” glued into core logic.

---

### 2.4 Support non-SiLA device connections

Explore connecting to devices through protocols other than SiLA.

Possible targets:

* Direct USB / serial COM devices.
* ROS2 nodes.
* Other local service APIs.

Questions to answer:

* What minimum interface should every device expose to Rxn Bench?
* Can non-SiLA devices still provide enough metadata for generic UI generation?
* Does ROS2 have a useful equivalent to FDL-style descriptions?
* Should non-SiLA devices be wrapped into Rxn Bench device interfaces?
* Should the UI care about protocol, or only about capabilities?

Acceptance criteria:

* Clear proposal for how non-SiLA devices fit into the architecture.
* No major UI rewrite is required for each protocol.
* Protocol-specific logic stays below the generic device layer.

---

## 3. Frontend UI Features

### 3.1 Save and restore workspaces

Tasks:

* Allow users to save an entire frontend workspace.
* Saved state should include:

  * active widgets
  * widget layout
  * connection info
  * selected devices
  * relevant UI configuration
* Allow restoring a workspace later.

Acceptance criteria:

* User can close and reopen Rxn Bench without rebuilding their layout.
* Workspace files are portable where possible.
* Missing/disconnected devices are handled gracefully.

---

## 4. General Features

### 4.1 Experiment scripting with CSV and Python

Goal: Support both simple CSV-driven workflows and more advanced Python scripts.

Tasks:

* Study existing `resources/chemspeed_workflow/...` CSVs.
* Define what a CSV workflow can express.
* Define what requires Python scripting.
* Ensure experiment runner can execute:

  * `.csv`
  * `.py`
* Consider an abstraction layer between workflow files and device execution.

Possible architecture:

* CSV and Python both compile/translate into a common internal experiment plan.
* The runner executes the plan through device interfaces.
* This keeps the runner from becoming two separate systems.

Acceptance criteria:

* Simple workflows can be written as CSV.
* Advanced workflows can be written in Python.
* Both use the same safety and device execution layer.
* Workflow execution is inspectable before running.

---

### 4.2 Improved homing and calibration

Current issue:
Manual jogging to corners and manually setting toolhead offsets works, but introduces human error. Safety depends heavily on accurate configuration.

Tasks:

* Study current Rxn Bench homing/calibration methods.
* Compare against common approaches used in CNC, 3D printers, liquid handlers, and lab automation systems.
* Improve calibration while preserving safety.
* Account for:

  * different toolhead sizes
  * multi-toolhead systems
  * labware height differences
  * user measurement error
  * mechanical tolerances
* Consider camera-assisted calibration.
* Define acceptable tolerance ranges.
* Make calibration mistakes easier to detect before motion begins.

Acceptance criteria:

* Calibration process is safer and less fragile.
* User has clear feedback when calibration values seem wrong.
* System avoids destructive moves even with imperfect user input.

---

### 4.3 Active error management and run monitoring

Explore whether Rxn Bench can detect and respond to problems during operation.

Possible signals:

* Camera image analysis.
* Toolhead position mismatch.
* Device communication failure.
* Unexpected motion failure.
* Timeout.
* Missed command response.
* Unsafe calculated move.
* User emergency stop.

Tasks:

* Diagnose current safety/error-handling behavior under real-world conditions.
* Test failures outside of perfect mock scenarios.
* Define what errors should stop the device immediately.
* Define what errors should warn the user.
* Define what errors can be retried.
* Consider camera-based detection for:

  * collision risk
  * failed tool engagement
  * blocked workspace
  * unexpected object in build area
  * visible liquid/toolhead issues

Acceptance criteria:

* Critical errors stop motion safely.
* User receives clear explanations of what happened.
* Failures are logged.
* Safety behavior works in real-world messy scenarios, not only in mocks.
