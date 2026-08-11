# hass-miner

<p align="center">
  <img src="custom_components/miner/brand/icon.png" alt="hass-miner icon" width="128">
</p>

<p align="center">
  Local monitoring and control of ASIC miners from Home Assistant.
</p>

hass-miner provides a capability-driven Home Assistant integration for ASIC miners. It keeps the Home Assistant entity model independent from firmware-specific APIs and uses dedicated backends where a miner needs safer or more reliable handling than a generic library can provide.

## Highlights

- Local polling; no cloud service is required.
- UI-based setup by IP address or hostname.
- Hashrate, ideal hashrate, temperatures, board telemetry, fan RPM, power consumption and efficiency where supported.
- Power-limit control with backend-specific validation.
- Mining on/off control, miner reboot and mining-backend restart where supported.
- Diagnostics for troubleshooting and unsupported hardware.
- Fast failure handling so an offline miner does not hold up Home Assistant startup.

## Antminer S9 with legacy Braiins OS+

The dedicated `braiins_legacy` backend has been tested on real Antminer S9 hardware running Braiins OS+ 22.08.1.

For a positively identified S9 it provides:

- safe power-target control from **400 W to 1400 W in 1 W steps**,
- independent hardware validation using `/tmp/sysinfo/board_name` and `/etc/bosminer_model.json`,
- atomic updates of the existing `bosminer.toml` `power_target` only,
- a dedicated validated backup and automatic rollback on write/restart failure,
- BOSMiner service start/stop through SSH for reliable Home Assistant mining control,
- direct BOSer board/chip temperature and fan telemetry when the firmware returns it,
- short per-field telemetry caching to mask transient BOSer omissions without hiding persistent failures.

The S9 backend deliberately does **not** rebuild the complete BOSMiner configuration through pyasic. This avoids the legacy configuration-corruption failure mode that can overwrite the firmware model metadata.

Fan telemetry on legacy Braiins firmware can occasionally disappear even while mining continues. The integration keeps the last valid values for short dropouts. If the firmware stops returning fan RPM persistently, the **Restart mining backend** button can be used to recover BOSMiner/BOSer telemetry.

## Other miners

Other miners supported by pyasic use the generic compatibility backend. Detection does not imply that every firmware-specific write operation has been independently validated by this project. See [SUPPORTED_MINERS.md](SUPPORTED_MINERS.md) for the current support matrix.

## Installation

### HACS

1. Open HACS.
2. Add `https://github.com/dhaucke/hass-miner` as a custom **Integration** repository.
3. Install **Miner**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration → Miner**.
6. Enter the miner IP address or hostname and the credentials requested for that device.

### Manual

Copy `custom_components/miner` into your Home Assistant `custom_components` directory and restart Home Assistant.

## Entities

Entities are created from detected backend capabilities and reported topology. The integration does not invent hashboards or fans that the miner has not reported.

Typical entities include:

- Hashrate / ideal hashrate
- Power consumption
- Efficiency
- Temperature
- Hashboard temperature / chip temperature / hashrate
- Fan RPM
- Power limit
- Mining switch
- Reboot button
- Restart mining backend button

Not every miner exposes every entity.

## Power-control safety

Power writes are backend-specific. Model-specific backends can enforce a validated range even when generic advanced options are configured.

For the legacy S9, only an existing integer `[autotuning].power_target` is modified. The integration refuses the write if the device identity, TOML structure, autotuning state or model metadata does not match the validated S9 path.

## Diagnostics and support

For an untested miner or a reproducible integration problem, open a GitHub issue and attach the Home Assistant diagnostics export where useful.

Do not post passwords, SSH keys, pool credentials, wallet addresses or other secrets.

## Development

Run the same checks used by CI:

```bash
python3 -m pip install -r requirements.txt
python3 -m ruff check .
python3 -m pytest -q
```

HACS validation and hassfest run in GitHub Actions.

## Credits and license

hass-miner is released under the [MIT License](LICENSE).

This repository is a fork and substantial rework of the original `Schnitzel/hass-miner` project. The original MIT copyright notice is preserved in the license history.

The generic compatibility backend uses [pyasic](https://github.com/UpstreamData/pyasic).

The integration brand icon uses the Google Material Icons `memory` glyph, distributed under the Apache License 2.0 and recolored for hass-miner branding.
