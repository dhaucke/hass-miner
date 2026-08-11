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

## Current technical debt

### Dependency/runtime handling

- pyasic is installed/reinstalled from integration code at runtime.
- partially imported pyasic modules are deleted from `sys.modules` after reinstall attempts.
- the integration pins one pyasic version in Python code while `pyproject.toml` has a separate version range.
- Home Assistant code directly imports pyasic types and config objects in multiple platforms/services.

Target: dependencies are declared normally and firmware libraries are hidden behind backend adapters.

### Coordinator lifecycle

- the coordinator calls `pyasic.get_miner()` on refresh, recreating the miner object repeatedly.
- credentials and runtime state are applied after rediscovery.
- transient discovery metadata can therefore affect control operations.

Target: detect and create one backend per config entry, reuse it, and let it manage its own connection/session lifecycle.

### Entity model

- capability checks are made against pyasic miner attributes.
- board/fan entities use fallback counts even when hardware topology is unknown.
- device metadata is duplicated across platforms.
- several entity names are assembled directly in Python instead of translation keys.

Target: shared base entity, normalized `MinerSnapshot`, capability-driven entities, translation keys, no invented topology.

### Control operations

- `number.py` calls `miner.set_power_limit()` directly.
- `switch.py` changes state optimistically and catches broad errors.
- `services.py` imports pyasic mining-mode classes and edits firmware configuration directly.

Target: all control methods go through `MinerBackend`; state is confirmed by refresh after commands.

### Braiins legacy safety

pyasic 0.78.8 `BOSMiner.set_power_limit()` obtains the existing config, converts it back into a pyasic model, reconstructs a complete TOML file, generates `[format].model` from transient runtime attributes, stops BOSminer, overwrites `/etc/bosminer.toml`, and restarts BOSminer. If model detection is missing, an invalid `model = " "` can be written.

Target for the S9/Braiins legacy backend:

- identify hardware independently from transient Python metadata;
- require consistent board/model evidence before writes;
- read the existing `/etc/bosminer.toml`;
- change only the intended power-target field;
- preserve pools, fan/temp settings and unknown keys;
- write a separate temporary file;
- validate before replacement;
- maintain a dedicated validated HA backup, not the firmware/pyasic `.bak` file;
- replace atomically and reload BOSminer;
- verify service/API recovery;
- roll back automatically if validation or startup fails;
- never silently repair an ambiguous hardware identity.

For a confidently identified Antminer S9 on the tested legacy Braiins firmware, the practical UI range can default to 400-1000 W in 100 W increments. This is a model/backend-specific default, not a global miner rule.

## Target architecture

```text
Home Assistant
  config_flow / options_flow
  coordinator
  entity platforms
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
        |
        +-- BraiinsLegacyBackend
        +-- future BraiinsModernBackend
        +-- PyasicBackend (generic compatibility)
```

The backend returns a normalized immutable snapshot. Home Assistant does not depend on firmware-specific configuration classes.

## Phases

### Phase 1 - architecture and safety

- [x] Create backend package.
- [x] Define backend protocol, capabilities and normalized snapshot model.
- [ ] Bring the existing Braiins `model = " "` safety guard into the rework branch.
- [ ] Add a generic pyasic adapter that owns one persistent miner object.
- [ ] Refactor coordinator to consume `MinerBackend` while preserving existing data keys during migration.
- [ ] Refactor number/switch/services to call backend operations.

Risk: medium. This changes internal boundaries but should preserve user-visible entities.

### Phase 2 - dedicated Braiins legacy backend

- [ ] Detect legacy Braiins S9 safely.
- [ ] Read telemetry from BOSer/BOSminer RPC without depending on pyasic model state for writes.
- [ ] Implement safe targeted power-limit editing over SSH.
- [ ] Add validation, backup, atomic replacement and rollback.
- [ ] Confirm pause/resume/reboot semantics on real S9 hardware.

Risk: high for write operations. Real S9 validation is required before release.

### Phase 3 - Home Assistant UX

- [ ] Simplify config flow to address first.
- [ ] Auto-detect model, firmware and capabilities.
- [ ] Ask only for credentials required by the detected backend.
- [ ] Validate credentials before saving.
- [ ] Prevent duplicate config entries by stable identity/IP.
- [ ] Move min/max power overrides to advanced options.
- [ ] Add translation keys and localized errors.
- [ ] Add shared device entity base class.
- [ ] Add buttons for stateless operations such as reboot/restart where appropriate.

Risk: low/medium. Needs migration care to avoid changing unique IDs.

### Phase 4 - diagnostics and community hardware support

- [ ] Implement HA diagnostics output.
- [ ] Redact passwords, pool credentials, wallet/user strings and other secrets.
- [ ] Include backend choice, capabilities and sanitized protocol metadata.
- [ ] Add an issue template for unsupported miners with diagnostics attachment instructions.
- [ ] Build parser fixtures from community submissions.

This is the main path for supporting expensive S19/S21-class miners without requiring maintainers to own every device.

### Phase 5 - tests and CI

No pytest suite is currently present in the repository.

Add tests for:

- backend capability contracts;
- normalized snapshot parsing;
- config flow success/authentication/failure/duplicate cases;
- coordinator offline -> recovery behavior;
- preservation of existing unique IDs;
- S9 corrupt/blank model regression;
- targeted TOML power-limit change;
- rejected unsafe writes;
- backup and rollback behavior;
- pause/resume state confirmation;
- sanitized diagnostics.

CI should run on PRs to `develop` as well as `main` and include Ruff, pytest, hassfest/HACS validation where applicable.

## Hardware test matrix

| Hardware / firmware | Support target | Validation source |
| --- | --- | --- |
| Antminer S9 + legacy Braiins OS+ | Tested | maintainer hardware |
| Newer Braiins-capable Antminers | Experimental initially | fixtures + community testers |
| S19/S21 family | Do not claim full support without testing | community diagnostics and hardware testers |
| Other pyasic-supported miners | Compatibility backend | pyasic + community reports |

## Definition of a safe beta

Before a beta release from this fork:

1. existing S9 entities load without changing unique IDs;
2. monitoring works for at least several hours without recreating backend state every poll;
3. repeated S9 power-limit changes cannot generate a blank model field;
4. failed writes restore the previously validated config;
5. stopping/resuming mining reports the actual post-command state;
6. unsupported hardware remains read-only or refuses unsafe controls rather than guessing;
7. diagnostics contain no credentials or pool secrets;
8. CI passes for every change targeting `develop`.
