# hass-miner rework plan

This fork is being reworked as a Home Assistant integration with explicit miner backends instead of exposing pyasic objects throughout the Home Assistant layer.

## Principles

1. `main` remains a stable reference until the rework is ready.
2. Home Assistant entities consume normalized data, not firmware-library objects.
3. Firmware-specific writes must fail safe. A failed control action must not corrupt a miner configuration.
4. Entities are created from capabilities reported by the backend.
5. Existing unique IDs should be preserved where practical to avoid breaking user automations.
6. Hardware support is labelled honestly: tested, community-tested, experimental, or generic compatibility.
7. Advanced options should not be required during normal onboarding.

## Current architecture status

The rework now has a firmware-independent `MinerBackend` contract, a normalized immutable snapshot model, one persistent pyasic compatibility backend per config entry, and a dedicated legacy Braiins S9 backend. Home Assistant entity platforms no longer call pyasic configuration methods directly.

The old runtime package installer and `sys.modules` manipulation have been removed. pyasic is a normal Home Assistant manifest requirement instead of being installed or force-reinstalled by integration code at runtime.

Generic legacy `BOSMiner` devices are deliberately read-only for configuration-changing operations. Power-limit and power-mode writes are enabled only by a dedicated backend that has positively validated the hardware identity and implements a safe write path.

## Braiins legacy safety

pyasic 0.78.8 `BOSMiner.set_power_limit()` reconstructs a complete TOML file and derives `[format].model` from transient runtime attributes. If model detection is missing, an invalid `model = " "` can be written and BOSMiner may not restart.

The dedicated S9 backend therefore:

- validates `/tmp/sysinfo/board_name == am1-s9`;
- independently validates `/etc/bosminer_model.json` reports `Antminer S9`;
- validates the existing `/etc/bosminer.toml` before every write;
- requires the existing `[autotuning]` schema to use `mode = "power_target"`;
- changes only the existing `power_target` assignment;
- preserves pools, fan/temp settings, formatting and unknown keys;
- creates a dedicated validated backup instead of trusting firmware/pyasic `.bak` files;
- writes to a temporary file and atomically replaces the active config;
- re-reads and validates the file after replacement;
- restarts BOSMiner and waits for telemetry to recover;
- automatically restores the validated backup if the new config or restart fails;
- verifies the rollback and waits for BOSMiner recovery again;
- never silently applies S9 assumptions to unknown legacy Braiins hardware.

For a positively identified Antminer S9 on the tested legacy Braiins firmware, the UI range is 400-1000 W in 100 W increments. This is backend/model specific, not a global miner rule.

## Target architecture

```text
Home Assistant
  config_flow / options_flow
  coordinator
  sensor / number / switch / button
  services / device actions
  diagnostics
        |
        v
MinerBackend protocol
  - capabilities
  - async_refresh()
  - async_set_power_limit()
  - async_pause()/async_resume()
  - async_reboot()
  - async_restart_backend()
  - async_set_power_mode()
        |
        +-- BraiinsLegacyS9Backend
        +-- future native backends
        +-- PyasicBackend (generic compatibility)
```

## Phases

### Phase 1 - architecture and safety

- [x] Create backend package and normalized data model.
- [x] Add capability contract and backend-specific exceptions.
- [x] Reuse one persistent pyasic miner/backend per config entry.
- [x] Refactor coordinator to consume the backend layer.
- [x] Refactor number/switch/services/device actions to backend operations.
- [x] Block unsafe generic legacy BOSMiner configuration writes.
- [x] Preserve existing Home Assistant unique-ID formats where practical.

### Phase 2 - dedicated Braiins legacy S9 backend

- [x] Detect legacy Braiins S9 from two independent firmware sources.
- [x] Implement targeted `power_target` editing without reconstructing TOML.
- [x] Add dedicated validated backup and rollback.
- [x] Verify written config before restart.
- [x] Poll for BOSMiner recovery after restart.
- [x] Restore and verify the old config if startup/recovery fails.
- [ ] Replace remaining pyasic telemetry dependency with direct BOSer/BOSMiner RPC where this provides a clear reliability benefit.
- [ ] Confirm pause/resume/reboot semantics on real S9 hardware.
- [ ] Run repeated real-device 400-1000 W power-target cycling tests.

Real S9 hardware is required before declaring this backend release-tested.

### Phase 3 - Home Assistant UX

- [x] Simplify onboarding to IP/hostname first.
- [x] Stop automatically scanning entire local subnets during normal setup.
- [x] Detect miner before requesting credentials.
- [x] Ask only for credential types exposed by the detected miner.
- [x] Validate connectivity and SSH credentials before saving where applicable.
- [x] Prevent duplicate entries for the same configured host.
- [x] Move generic min/max power overrides to advanced options.
- [x] Add a version-1 to version-2 config-entry migration for old power-range data.
- [x] Add translation keys and German translations.
- [x] Add shared device entity base class.
- [x] Add capability-driven reboot/restart buttons for stateless maintenance actions.
- [x] Stop inventing three boards/four fans when topology is unknown.
- [x] Add regression coverage for duplicate-host normalization and safe setup placeholders.
- [ ] Improve credential/error classification beyond string matching where backend APIs expose typed authentication errors.
- [ ] Consider migrating runtime coordinator storage from `hass.data` to typed `ConfigEntry.runtime_data` after the current beta path is stable.

### Phase 4 - diagnostics and community hardware support

- [x] Implement Home Assistant config-entry diagnostics.
- [x] Redact host/IP/MAC/hostname from public diagnostics by default.
- [x] Exclude passwords, pool credentials and raw miner config from generic diagnostics.
- [x] Include backend choice, capabilities, topology and safety status.
- [x] Add unsupported/untested miner GitHub issue template.
- [x] Add explicit support-level documentation.
- [x] Add diagnostics regression tests for network-identity redaction and backend reuse.
- [ ] Add sanitized protocol samples when a native backend can expose them without secrets.
- [ ] Add recorded community fixtures for S19/S21-class devices as submissions arrive.

This is the primary route for supporting expensive hardware the maintainer does not own.

### Phase 5 - tests and CI

Implemented tests currently cover:

- [x] backend power-range validation;
- [x] S9 targeted TOML editing and text preservation;
- [x] blank/corrupt model regression;
- [x] wrong-model rejection;
- [x] schema-change rejection;
- [x] rollback after failed BOSMiner restart;
- [x] generic legacy BOSMiner configuration-write blocking;
- [x] service device-ID normalization;
- [x] config-entry migration behavior;
- [x] duplicate-host and config-flow helper behavior;
- [x] coordinator transient-failure and rediscovery thresholds;
- [x] diagnostics redaction and backend-reuse behavior;
- [x] switch/button command refresh semantics.

Still required:

- [ ] full config-flow success/auth/failure tests with Home Assistant flow fixtures;
- [ ] entity unique-ID migration/regression tests;
- [ ] recorded protocol fixture tests for community hardware.

CI is now verified on the fork. Ruff, pytest, HACS validation and hassfest all pass on the backend rework pull request. The test suite is expected to remain green before any beta hardware run or merge into `develop`.

## Hardware test matrix

| Hardware / firmware | Support target | Current evidence |
| --- | --- | --- |
| Antminer S9 + legacy Braiins OS+ | Tested target | maintainer hardware available; write path still needs beta run |
| Newer Braiins-capable Antminers | Experimental initially | community fixtures/testers required |
| S19/S21 family | No full-support claim without testing | community diagnostics and hardware testers required |
| Other pyasic-supported miners | Compatibility backend | pyasic capability + community reports |

## Definition of a safe beta

Before a beta release from this fork:

1. existing S9 entities load without unexpected unique-ID changes;
2. monitoring runs for several hours without recreating backend state every poll;
3. repeated S9 power-limit changes cannot generate a blank model field;
4. failed writes restore the previously validated config and BOSMiner recovers;
5. stopping/resuming mining reports actual post-command state;
6. unsupported legacy BOSMiner hardware remains configuration-read-only rather than guessing;
7. diagnostics contain no credentials or pool secrets;
8. Ruff, pytest, HACS validation and hassfest pass;
9. the S9 power-write path passes real-hardware cycling tests before the draft PR is promoted.
