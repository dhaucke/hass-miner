# Miner and firmware support levels

hass-miner 2.x separates Home Assistant entities from firmware-specific backends. A miner being detectable by the generic compatibility backend does **not** automatically mean every write operation is verified safe.

## Support levels

| Level | Meaning |
| --- | --- |
| Tested | Maintainers have access to the hardware and verify read/write behavior on a real device. |
| Community tested | Real-device behavior has been confirmed by community testers and regression fixtures are kept in the repository. |
| Compatibility | The miner is handled through the generic pyasic backend. Telemetry or controls may depend on pyasic and are not independently verified by hass-miner. |
| Experimental | Protocol support or parsing exists, but write operations have not been sufficiently verified on real hardware. |

## Current matrix

| Miner / firmware | Backend | Level | Notes |
| --- | --- | --- | --- |
| Antminer S9 / legacy Braiins OS+ BOSMiner | `braiins_legacy` | Tested in development | Dedicated identity checks and safe `power_target` write path. Initial target range 400–1000 W, 100 W steps. Real-hardware validation is still required before the 2.0 release. |
| Other miners supported by pyasic | `pyasic` | Compatibility | Existing pyasic support is retained while firmware-specific backends are added progressively. |
| Antminer S19 family | not dedicated yet | Experimental / community wanted | No maintainer-owned test hardware. Do not assume S9 write behavior applies. |
| Antminer S21 family | not dedicated yet | Experimental / community wanted | No maintainer-owned test hardware. Do not assume S9 write behavior applies. |

## Helping with untested hardware

Open an **Unsupported or untested miner** issue and attach the Home Assistant diagnostics export. Do not upload passwords, pool credentials, private keys, wallet addresses, or other secrets.

For new hardware families, the preferred path is:

1. collect sanitized diagnostics and read-only API samples,
2. add recorded fixtures and parser tests,
3. implement capability detection,
4. test read-only behavior,
5. test write operations with explicit real-hardware volunteers,
6. only then promote the support level.

This allows support for expensive hardware without pretending that untested power-control operations are safe.
