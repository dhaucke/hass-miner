# hass-miner

Local monitoring and control of ASIC miners from Home Assistant.

The 2.x rework separates Home Assistant from firmware-specific miner APIs. The goal is simple onboarding for normal Home Assistant users while keeping advanced controls and diagnostics available when the miner supports them.

> **Development status:** the 2.x backend rework is currently under active development on `feature/backend-rework`. Do not treat the development branch as a stable release yet.

## Why this fork exists

The original integration delegated almost all behavior directly to pyasic. That made broad miner support possible, but it also coupled Home Assistant entities, discovery, configuration writes and firmware quirks tightly to one library.

The 2.x architecture introduces explicit miner backends:

- `braiins_legacy` — dedicated safe path for positively identified legacy Braiins/BOSMiner hardware,
- `pyasic` — compatibility backend for the wider existing miner ecosystem,
- additional native backends can be added without changing Home Assistant entities.

This is especially useful for solar mining, heat reuse, dynamic power control and installations where miners should not simply run at maximum power 24/7.

## Quick start

1. Install the repository as a custom HACS integration.
2. Add the **Miner** integration in Home Assistant.
3. Enter the miner IP address or hostname.
4. hass-miner detects the miner and asks only for credentials exposed by that device.
5. Give the device a friendly name.

The normal setup flow no longer asks ordinary users to guess minimum and maximum power values. Generic overrides remain available under the integration's advanced options.

## Entities

Entities are created from backend capabilities and detected topology. hass-miner does not invent three hashboards or four fans when the miner did not report them.

Typical entities include:

- hashrate and ideal hashrate,
- miner and hashboard temperatures,
- power consumption,
- power limit,
- efficiency,
- fan speed,
- hashboard hashrate,
- mining pause/resume switch.

Not every miner exposes every entity.

## Power control safety

Write operations are backend-specific.

For a legacy Braiins Antminer S9, the dedicated backend requires two independent identity checks before S9-specific power control is enabled:

- `/tmp/sysinfo/board_name` must identify `am1-s9`, and
- `/etc/bosminer_model.json` must identify `Antminer S9`.

The S9 backend does not rebuild the whole `bosminer.toml` file. It validates the existing TOML, changes only an existing `power_target`, creates its own validated backup, writes through a temporary file, atomically replaces the config and rolls back on validation failure.

Current development defaults for this validated S9 path are 400–1000 W in 100 W steps.

## Supported miners

See [SUPPORTED_MINERS.md](SUPPORTED_MINERS.md).

Support levels intentionally distinguish between:

- real-device tested,
- community tested,
- generic pyasic compatibility,
- experimental / awaiting hardware testers.

An S19 or S21 is not claimed as fully supported merely because a library can detect it.

## Diagnostics and unsupported hardware

Home Assistant diagnostics are part of the new support strategy. They are intended to provide backend type, detected model/firmware, capability information and topology without requiring users to post passwords or pool credentials.

For hardware we do not own, open an **Unsupported or untested miner** issue and attach the diagnostics export. This allows recorded fixtures and regression tests to be built before write support is considered production-ready.

Never upload passwords, private keys, pool credentials or wallet addresses.

## Advanced options

The standard setup intentionally stays small. Generic minimum and maximum power overrides are available in the integration options for users who know that their firmware requires them.

Model-specific backends may ignore generic ranges when they have a narrower validated safe range.

## Services

Depending on backend capabilities, hass-miner can expose services for:

- rebooting the miner,
- restarting the mining backend,
- selecting firmware-defined work modes.

Unsupported operations are rejected instead of being guessed.

## Development

The rework plan is documented in [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md).

CI covers Ruff, pytest, HACS validation and hassfest on development branches. New firmware backends should be capability-driven and include recorded fixtures wherever possible.

## Installation during development

In HACS, add this repository as a custom integration repository:

`https://github.com/dhaucke/hass-miner`

For normal users, wait for a tagged 2.x release rather than installing an active feature branch.

## Credits and license

This repository is a fork of the original `Schnitzel/hass-miner` project and remains licensed under the MIT License. The original copyright and license notice are preserved in [LICENSE](LICENSE).

The compatibility backend continues to use [pyasic](https://github.com/UpstreamData/pyasic) for broad miner support while dedicated backends progressively remove unsafe or firmware-specific write behavior from the generic path.
