# Supported miners

hass-miner separates Home Assistant entities from firmware-specific backends. A miner being detectable through the generic compatibility backend does **not** mean every write operation has been independently verified by this project.

## Support levels

| Level | Meaning |
| --- | --- |
| **Tested** | Maintainer-tested on real hardware, including the documented write paths. |
| **Community tested** | Confirmed by real-device testers with enough information to keep regression coverage. |
| **Compatibility** | Uses the generic pyasic backend. Telemetry and controls depend on pyasic and the miner firmware. |
| **Experimental** | Parsing or protocol support may exist, but hardware behavior is not sufficiently validated for a production claim. |

## Current matrix

| Miner / firmware | Backend | Level | Notes |
| --- | --- | --- | --- |
| Antminer S9 / Braiins OS+ 22.08.1 | `braiins_legacy` | **Tested** | Real-device tested on two S9 units. Dedicated identity checks, safe 400–1400 W power-target writes in 1 W steps, SSH BOSMiner start/stop, board/chip telemetry, fan telemetry when returned by BOSer, rollback protection. |
| Other miners supported by pyasic | `pyasic` | Compatibility | Broad read/control compatibility is retained. Firmware-specific behavior is not automatically considered independently verified. |
| Antminer S19 family | generic / no dedicated backend | Experimental / testers wanted | No maintainer-owned validation hardware. S9-specific write behavior is never applied. |
| Antminer S21 family | generic / no dedicated backend | Experimental / testers wanted | No maintainer-owned validation hardware. S9-specific write behavior is never applied. |

## Legacy Braiins S9 notes

Braiins OS+ 22.08.1 can intermittently omit board or fan fields from BOSer responses. hass-miner caches individual board telemetry fields for a small number of polling cycles so a single incomplete response does not immediately blank Home Assistant entities. Fresh values, including a legitimate `0` hashrate, always win over the cache.

Persistent missing telemetry is eventually exposed as unavailable/unknown instead of being hidden indefinitely. A BOSMiner backend restart can recover firmware-side fan telemetry when BOSer stops returning RPM values.

## Helping with untested hardware

Open an **Unsupported or untested miner** issue and attach the Home Assistant diagnostics export where useful. Do not upload passwords, pool credentials, private keys, wallet addresses or other secrets.

For a new hardware family the preferred path is:

1. collect sanitized diagnostics and read-only API samples,
2. add fixtures and parser tests,
3. implement capability detection,
4. validate read-only behavior,
5. validate write operations on real hardware,
6. only then promote the support level.
