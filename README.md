![Miner - Lokale ASIC-Miner-Integration für Home Assistant](https://raw.githubusercontent.com/dhaucke/hass-miner/main/assets/miner-banner.png)

# Miner

**Lokale Überwachung und Steuerung von ASIC-Minern für Home Assistant.**

[![Release](https://img.shields.io/github/v/release/dhaucke/hass-miner?style=flat-square)](https://github.com/dhaucke/hass-miner/releases/latest)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5?style=flat-square)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-18BCF2?style=flat-square)](https://www.home-assistant.io/)
[![License](https://img.shields.io/github/license/dhaucke/hass-miner?style=flat-square)](https://github.com/dhaucke/hass-miner/blob/main/LICENSE)

**Hashrate · Temperaturen · Leistung · Effizienz · Lüfter · Mining-Steuerung · Leistungslimits**

[Mit HACS installieren](https://my.home-assistant.io/redirect/hacs_repository/?owner=dhaucke&repository=hass-miner&category=integration) · [Unterstützte Miner](https://github.com/dhaucke/hass-miner/blob/main/SUPPORTED_MINERS.md) · [Problem melden](https://github.com/dhaucke/hass-miner/issues)

**Sprache:** [Deutsch](#deutsch) · [English](#english)

---

# Deutsch

## Was ist Miner?

**Miner** ist eine lokal arbeitende Home-Assistant-Integration zur Überwachung und Steuerung von ASIC-Minern. Die Integration verwendet eine fähigkeitsbasierte Backend-Architektur, damit die Home-Assistant-Entitäten konsistent bleiben und firmware-spezifisches Verhalten sicher behandelt werden kann.

> Kein Cloud-Dienst erforderlich. Die Kommunikation erfolgt direkt zwischen Home Assistant und dem Miner im lokalen Netzwerk.

## Highlights

| Funktion | Beschreibung |
| --- | --- |
| **Live-Telemetrie** | Hashrate, Ideal-Hashrate, Temperaturen, Board-Telemetrie, Lüfterdrehzahl, Verbrauch und Effizienz, sofern unterstützt |
| **Leistungssteuerung** | Vom Backend validierte Leistungslimits über native Home-Assistant-Number-Entitäten |
| **Mining-Steuerung** | Mining starten/stoppen, Miner neu starten und Mining-Backend neu starten, sofern unterstützt |
| **Automatisierungsbereit** | Native Entitäten und Dienste für PV-Überschuss, Speicher, Lastmanagement und weitere Home-Assistant-Automatisierungen |
| **Robustes Polling** | Offline oder nicht erreichbare Miner blockieren den Home-Assistant-Start nicht unnötig |
| **Diagnose** | Home-Assistant-Diagnosedaten zur Fehlersuche und Unterstützung weiterer Hardware |

---

## Antminer S9 + Legacy Braiins OS+

Das dedizierte Backend `braiins_legacy` wurde auf echter **Antminer-S9-Hardware** mit **Braiins OS+ 22.08.1** validiert.

Für einen eindeutig erkannten S9 bietet es:

- sichere Leistungsvorgaben von **400 W bis 1400 W in 1-W-Schritten**,
- unabhängige Hardwarevalidierung über `/tmp/sysinfo/board_name` und `/etc/bosminer_model.json`,
- atomare Änderung ausschließlich des vorhandenen `power_target` in `bosminer.toml`,
- ein dediziertes validiertes Backup mit automatischem Rollback bei Schreib- oder Neustartfehlern,
- Start/Stopp des BOSMiner-Dienstes über SSH für zuverlässige Mining-Steuerung aus Home Assistant,
- direkte BOSer-Telemetrie für Board-/Chip-Temperaturen und Lüfter, sofern die Firmware diese liefert,
- kurzes **feldweises Telemetrie-Caching**, um vorübergehende BOSer-Aussetzer abzufangen, ohne dauerhafte Fehler zu verstecken.

> **Warum ein eigenes Backend?**  
> Das S9-Backend baut die vollständige BOSMiner-Konfiguration bewusst nicht über pyasic neu auf. Es wird ausschließlich das validierte Leistungslimit geändert. Dadurch werden Beschädigungen älterer Konfigurationen und Modellmetadaten vermieden.

### Legacy-Braiins-Lüftertelemetrie

Legacy BOSer/BOSMiner kann zeitweise keine Lüfterdrehzahlen zurückgeben, obwohl das Mining normal weiterläuft. Miner stabilisiert kurze Aussetzer über das Telemetrie-Caching. Wenn die Lüfterwerte dauerhaft fehlen, kann **Mining-Backend neu starten** verwendet werden, um BOSMiner/BOSer neu zu starten und die Telemetrie wiederherzustellen.

## Weitere Miner

Andere von pyasic unterstützte Miner verwenden das generische Kompatibilitäts-Backend. Eine erfolgreiche Erkennung bedeutet **nicht**, dass jede firmware-spezifische Schreiboperation für dieses Projekt separat validiert wurde.

Siehe **[SUPPORTED_MINERS.md](https://github.com/dhaucke/hass-miner/blob/main/SUPPORTED_MINERS.md)** für den aktuellen Unterstützungsstatus und Hardwarehinweise.

---

## Installation

### HACS

1. **HACS** öffnen.
2. Das Menü öffnen und **Benutzerdefinierte Repositories / Custom repositories** wählen.
3. `https://github.com/dhaucke/hass-miner` als Typ **Integration** hinzufügen.
4. **Miner** installieren und Home Assistant neu starten.
5. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Miner** öffnen.
6. IP-Adresse oder Hostname des Miners sowie die für das Gerät benötigten Zugangsdaten eingeben.

[![Dieses Repository in HACS öffnen.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dhaucke&repository=hass-miner&category=integration)

### Manuelle Installation

`custom_components/miner` in das `custom_components`-Verzeichnis von Home Assistant kopieren und Home Assistant neu starten.

---

## Home-Assistant-Entitäten

Entitäten werden anhand der erkannten Backend-Fähigkeiten und der vom Miner gemeldeten Topologie erstellt. Miner erfindet keine Hashboards oder Lüfter, die vom Gerät nie gemeldet wurden.

| Entität / Fähigkeit | Verfügbarkeit |
| --- | --- |
| **Hashrate / Ideal-Hashrate** | Wenn vom Miner gemeldet |
| **Leistungsaufnahme / Effizienz** | Wenn unterstützt |
| **Temperatur** | Geräte- und Hashboard-Temperaturen, sofern verfügbar |
| **Chip-Temperatur** | Wenn vom Backend bereitgestellt |
| **Lüfterdrehzahl** | Wenn vom Miner gemeldet |
| **Leistungslimit** | Unterstützte schreibfähige Backends |
| **Mining-Schalter** | Wenn unterstützt |
| **Neustart** | Wenn unterstützt |
| **Mining-Backend neu starten** | Backends, die diese Funktion bereitstellen |

Nicht jeder Miner stellt jede Entität bereit.

## Sicherheit bei der Leistungssteuerung

Leistungsvorgaben sind backend-spezifisch. Modellspezifische Backends können einen validierten Wertebereich erzwingen, selbst wenn generische erweiterte Optionen anders konfiguriert sind.

Beim Legacy-S9 wird ausschließlich ein vorhandener ganzzahliger `[autotuning].power_target` geändert. Miner verweigert die Änderung, wenn Geräteidentität, TOML-Struktur, Autotuning-Status oder Modellmetadaten nicht dem validierten S9-Pfad entsprechen.

---

## Fehlerbehebung

Wenn ein Miner nicht unterstützt wird oder sich ein Integrationsproblem reproduzieren lässt, bitte ein GitHub-Issue öffnen und bei Bedarf den Home-Assistant-Diagnoseexport anhängen.

> **Sicherheit:** Niemals Passwörter, SSH-Schlüssel, Pool-Zugangsdaten, Wallet-Adressen oder andere Geheimnisse veröffentlichen.

## Entwicklung

Die gleichen Prüfungen wie in CI können lokal ausgeführt werden:

```bash
python3 -m pip install -r requirements.txt
python3 -m ruff check .
python3 -m pytest -q
```

HACS-Validierung und hassfest laufen über GitHub Actions.

---

## Credits & Lizenz

Miner wird unter der [MIT-Lizenz](https://github.com/dhaucke/hass-miner/blob/main/LICENSE) veröffentlicht.

Dieses Repository ist ein Fork und eine umfassende Überarbeitung des ursprünglichen Projekts `Schnitzel/hass-miner`. Der ursprüngliche MIT-Copyright-Hinweis bleibt in der Projekthistorie erhalten.

Das generische Kompatibilitäts-Backend verwendet [pyasic](https://github.com/UpstreamData/pyasic).

---

# English

## What is Miner?

**Miner** is a local-first Home Assistant integration for monitoring and controlling ASIC miners. It uses a capability-driven backend architecture so Home Assistant entities stay consistent while firmware-specific behavior can be handled safely where required.

> No cloud service is required. Communication happens directly between Home Assistant and the miner on your local network.

## Highlights

| Feature | Description |
| --- | --- |
| **Live telemetry** | Hashrate, ideal hashrate, temperatures, board telemetry, fan RPM, consumption and efficiency where supported |
| **Power control** | Backend-validated power limits with native Home Assistant number entities |
| **Mining control** | Start/stop mining, reboot the miner and restart the mining backend where supported |
| **Automation ready** | Native entities and services for PV surplus, storage, load-management and other Home Assistant automations |
| **Resilient polling** | Offline or unavailable miners fail quickly instead of delaying Home Assistant startup |
| **Diagnostics** | Home Assistant diagnostics for troubleshooting and bringing up additional hardware |

---

## Antminer S9 + legacy Braiins OS+

The dedicated `braiins_legacy` backend has been validated on real **Antminer S9** hardware running **Braiins OS+ 22.08.1**.

For a positively identified S9 it provides:

- safe power-target control from **400 W to 1400 W in 1 W steps**,
- independent hardware validation using `/tmp/sysinfo/board_name` and `/etc/bosminer_model.json`,
- atomic updates of the existing `bosminer.toml` `power_target` only,
- a dedicated validated backup plus automatic rollback on write/restart failure,
- BOSMiner service start/stop through SSH for reliable Home Assistant mining control,
- direct BOSer board/chip temperature and fan telemetry when the firmware returns it,
- short **per-field telemetry caching** to absorb transient BOSer omissions without hiding persistent failures.

> **Why a dedicated backend?**  
> The S9 backend deliberately does not rebuild the complete BOSMiner configuration through pyasic. Only the validated power-target field is changed, preventing legacy configuration corruption of the firmware model metadata.

### Legacy Braiins fan telemetry

Legacy BOSer/BOSMiner can intermittently stop returning fan RPM even while mining continues normally. Miner keeps short dropouts stable; if fan telemetry remains missing, use **Restart mining backend** to restart BOSMiner/BOSer and recover telemetry.

## Other miners

Other miners supported by pyasic use the generic compatibility backend. Detection does **not** mean that every firmware-specific write operation has been independently validated by this project.

See **[SUPPORTED_MINERS.md](https://github.com/dhaucke/hass-miner/blob/main/SUPPORTED_MINERS.md)** for the current support levels and hardware notes.

---

## Installation

### HACS

1. Open **HACS**.
2. Open the menu and choose **Custom repositories**.
3. Add `https://github.com/dhaucke/hass-miner` as type **Integration**.
4. Install **Miner** and restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration → Miner**.
6. Enter the miner IP address or hostname and the credentials requested for that device.

[![Open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dhaucke&repository=hass-miner&category=integration)

### Manual installation

Copy `custom_components/miner` to your Home Assistant `custom_components` directory and restart Home Assistant.

---

## Home Assistant entities

Entities are created from detected backend capabilities and reported topology. Miner does not invent hashboards or fans that the miner has never reported.

| Entity / capability | Availability |
| --- | --- |
| **Hashrate / ideal hashrate** | Where reported by the miner |
| **Power consumption / efficiency** | Where supported |
| **Temperature** | Device and per-hashboard where available |
| **Chip temperature** | Where exposed by the backend |
| **Fan RPM** | Where reported by the miner |
| **Power limit** | Supported write-capable backends |
| **Mining switch** | Where supported |
| **Reboot** | Where supported |
| **Restart mining backend** | Backends that expose it |

Not every miner exposes every entity.

## Power-control safety

Power writes are backend-specific. Model-specific backends may enforce a validated range even if generic advanced options are configured.

For the legacy S9, only an existing integer `[autotuning].power_target` is modified. Miner refuses the write when device identity, TOML structure, autotuning state or model metadata do not match the validated S9 path.

---

## Troubleshooting

If a miner is unsupported or an integration problem is reproducible, open a GitHub issue and attach the Home Assistant diagnostics export when useful.

> **Security:** Never post passwords, SSH keys, pool credentials, wallet addresses or other secrets.

## Development

Run the same code checks used by CI:

```bash
python3 -m pip install -r requirements.txt
python3 -m ruff check .
python3 -m pytest -q
```

HACS validation and hassfest run in GitHub Actions.

---

## Credits & license

Miner is released under the [MIT License](https://github.com/dhaucke/hass-miner/blob/main/LICENSE).

This repository is a fork and substantial rework of the original `Schnitzel/hass-miner` project. The original MIT copyright notice is preserved in the project history.

The generic compatibility backend uses [pyasic](https://github.com/UpstreamData/pyasic).
