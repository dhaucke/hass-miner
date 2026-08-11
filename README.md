<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="custom_components/miner/brand/dark_logo.png">
  <source media="(prefers-color-scheme: light)" srcset="custom_components/miner/brand/logo.png">
  <img src="custom_components/miner/brand/logo.png" alt="Miner" width="520">
</picture>

### Local ASIC miner monitoring and control for Home Assistant

[![Release](https://img.shields.io/github/v/release/dhaucke/hass-miner?style=flat-square)](https://github.com/dhaucke/hass-miner/releases/latest)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5?style=flat-square)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-18BCF2?style=flat-square)](https://www.home-assistant.io/)
[![License](https://img.shields.io/github/license/dhaucke/hass-miner?style=flat-square)](LICENSE)

**Hashrate · Temperatures · Power · Efficiency · Fans · Mining control · Power limits**

[Install with HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=dhaucke&repository=hass-miner&category=integration) · [Supported miners](SUPPORTED_MINERS.md) · [Report an issue](https://github.com/dhaucke/hass-miner/issues)

</div>

---

## What is Miner?

**Miner** is a local-first Home Assistant integration for monitoring and controlling ASIC miners. It uses a capability-driven backend architecture so Home Assistant entities stay consistent while firmware-specific behavior can be handled safely where required.

No cloud service is required. Communication happens directly between Home Assistant and the miner on your local network.

### Highlights

| Feature | Description |
| --- | --- |
| **Live telemetry** | Hashrate, ideal hashrate, temperatures, board telemetry, fan RPM, consumption and efficiency where supported |
| **Power control** | Backend-validated power limits with native Home Assistant number entities |
| **Mining control** | Start/stop mining, reboot the miner and restart the mining backend where supported |
| **Automation ready** | Native entities and services for PV surplus, storage, load-management and other Home Assistant automations |
| **Resilient polling** | Offline or unavailable miners fail quickly instead of delaying Home Assistant startup |
| **Diagnostics** | Home Assistant diagnostics for troubleshooting and bringing up additional hardware |

## Antminer S9 + legacy Braiins OS+

The dedicated `braiins_legacy` backend has been validated on real **Antminer S9** hardware running **Braiins OS+ 22.08.1**.

For a positively identified S9 it provides:

- safe power-target control from **400 W to 1400 W in 1 W steps**,
- independent hardware validation using `/tmp/sysinfo/board_name` and `/etc/bosminer_model.json`,
- atomic updates of the existing `bosminer.toml` `power_target` only,
- a dedicated validated backup plus automatic rollback on write/restart failure,
- BOSMiner service start/stop through SSH for reliable Home Assistant mining control,
- direct BOSer board/chip temperature and fan telemetry when the firmware returns it,
- short **per-field** telemetry caching to absorb transient BOSer omissions without hiding persistent failures.

> **Why a dedicated backend?**  
> The S9 backend deliberately does not rebuild the complete BOSMiner configuration through pyasic. Only the validated power-target field is changed, preventing legacy configuration corruption of the firmware model metadata.

### Legacy Braiins fan telemetry

Legacy BOSer/BOSMiner can intermittently stop returning fan RPM even while mining continues normally. Miner keeps short dropouts stable; if fan telemetry remains missing, use **Restart mining backend** to restart BOSMiner/BOSer and recover telemetry.

## Other miners

Other miners supported by pyasic use the generic compatibility backend. Detection does **not** mean that every firmware-specific write operation has been independently validated by this project.

See **[SUPPORTED_MINERS.md](SUPPORTED_MINERS.md)** for the current support levels and hardware notes.

## Installation

### HACS

1. Open **HACS**.
2. Open the menu and choose **Custom repositories**.
3. Add `https://github.com/dhaucke/hass-miner` as type **Integration**.
4. Install **Miner** and restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration → Miner**.
6. Enter the miner IP address or hostname and the credentials requested for that device.

You can also use the button below:

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dhaucke&repository=hass-miner&category=integration)

### Manual

Copy `custom_components/miner` to your Home Assistant `custom_components` directory and restart Home Assistant.

## Home Assistant entities

Entities are created from detected backend capabilities and reported topology. Miner does not invent hashboards or fans that the miner has never reported.

Typical entities include:

- **Hashrate** and **ideal hashrate**
- **Power consumption** and **efficiency**
- **Temperature**
- Per-hashboard **temperature**, **chip temperature** and **hashrate**
- **Fan RPM**
- **Power limit**
- **Mining** switch
- **Reboot** button
- **Restart mining backend** button

Not every miner exposes every entity.

## Power-control safety

Power writes are backend-specific. Model-specific backends may enforce a validated range even if generic advanced options are configured.

For the legacy S9, only an existing integer `[autotuning].power_target` is modified. Miner refuses the write when device identity, TOML structure, autotuning state or model metadata do not match the validated S9 path.

## Troubleshooting

If a miner is unsupported or an integration problem is reproducible, open a GitHub issue and attach the Home Assistant diagnostics export when useful.

**Never post passwords, SSH keys, pool credentials, wallet addresses or other secrets.**

## Development

Run the same code checks used by CI:

```bash
python3 -m pip install -r requirements.txt
python3 -m ruff check .
python3 -m pytest -q
```

HACS validation and hassfest run in GitHub Actions.

## Credits & license

Miner is released under the [MIT License](LICENSE).

This repository is a fork and substantial rework of the original `Schnitzel/hass-miner` project. The original MIT copyright notice is preserved in the project history.

The generic compatibility backend uses [pyasic](https://github.com/UpstreamData/pyasic).
