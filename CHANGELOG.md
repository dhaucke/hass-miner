# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.0.9] - 2026-08-12

### Added

- New diagnostic sensor "Connection method" (`backend`) showing which backend
  is currently active for a miner (e.g. "Validated S9 (SSH)" vs "Generic
  (pyasic, network)"). Prompted directly by a live debugging session where a
  miner silently ran on the generic RPC backend for a whole session instead
  of the validated SSH-backed `braiins_legacy` backend, with no way to see
  that from the Home Assistant UI without downloading logs and matching
  traceback file paths. The value was already computed in `coordinator.py`
  (used only for diagnostics downloads); it is now also surfaced through the
  existing `miner_sensors` dict so it picks up a regular sensor entity for
  free, with translated, human-readable state values in `en.json`/`de.json`.

## [2.0.8] - 2026-08-12

### Fixed

- Coordinator now rediscovers the backend after a failed write (switch/number/
  button/service call), not only after repeated telemetry-read failures. Live
  diagnosis on a real S9 showed a miner stuck on the generic `pyasic` backend
  for an entire session -- 114 `async_resume()` calls all going through
  `pyasic_backend.py` (RPC), never through the dedicated SSH-backed
  `braiins_legacy` backend -- because S9 identity validation apparently
  failed once at HA startup, and successful telemetry polling kept resetting
  the existing read-failure counter before it ever reached the 3-strike
  rediscovery threshold. Added `MinerCoordinator.record_command_failure()`,
  called from every entity/service command failure, which forces immediate
  rediscovery unless the backend already validated as `braiins_legacy` (same
  guard `_record_failure` uses, so an already-validated S9's SSH transport is
  never discarded over an unrelated resume/pause hiccup).

## [2.0.7] - 2026-08-12

### Fixed

- Entity/service command handlers (`switch.py`, `number.py`, `button.py`,
  `services.py`) now catch backend failures and re-raise them as
  `homeassistant.exceptions.HomeAssistantError` instead of letting raw
  `RuntimeError`/`BackendError` propagate. Live diagnosis showed that Home
  Assistant's automation `continue_on_error: true` only suppresses
  `HomeAssistantError` subclasses (see `helpers/script.py`
  `_handle_exception`); a raw `RuntimeError` from a failed `async_resume()`
  call (e.g. the S9 not yet acknowledging a command right after a power-limit
  change) still aborted the entire calling automation even with
  `continue_on_error` set on the triggering action. Backend-internal
  exception types in `backends/base.py`/`backends/*.py` are intentionally
  left untouched (plain `Exception`-based) to keep backend unit tests free of
  a Home Assistant runtime dependency; the conversion now happens only at the
  entity/service boundary, which already imports Home Assistant.

## [2.0.6] - 2026-08-12

### Added

- Regression tests for the generic pyasic backend against Antminer S19/S21/S21+
  and Hydro model shapes (`tests/test_pyasic_backend_antminer_models.py`), since
  none of this hardware is owned by the maintainer. Pins down two real pyasic
  facts: stock BMMiner/AntminerModern firmware never sets `supports_autotuning`,
  so factory S19/S21/S21+ units cannot receive power-limit writes through pyasic
  at all (only high/normal/low presets via `supports_power_modes`); and Hydro
  variants report `expected_fans = 0` while board temperatures still populate
  normally. Also documents a known, deliberately *not* fixed gap: pyasic exposes
  presets on VNish/LuxOS through a separate `supports_presets` flag that
  `PyasicBackend` does not read. Investigated fixing it by also checking
  `supports_presets`, but pyasic's `MiningModeConfig` high/normal/low values have
  no `as_vnish()`/`as_luxos()` serializer, so the generic mining-mode write would
  silently no-op instead of failing — enabling it would be unsafe without real
  hardware to validate a proper preset-based implementation. Whatsminer/BTMiner
  already sets `supports_power_modes` directly and is unaffected.

## [2.0.5] - 2026-08-12

### Fixed

- Fix brand images so Home Assistant/HACS actually render the integration icon
  and logo. `icon.png`/`dark_icon.png` were 1536x1024 landscape banners instead
  of the required 1:1 square (256x256, 512x512 for `@2x`), so they were being
  dropped by the brand renderer. Cropped and resized `icon.png`, `dark_icon.png`,
  `logo.png` and `dark_logo.png` to spec, and added the missing hDPI variants
  (`icon@2x.png`, `dark_icon@2x.png`, `logo@2x.png`, `dark_logo@2x.png`).
  Since HA 2026.3.0 these `custom_components/miner/brand/` images are served
  directly, no `home-assistant/brands` submission needed.

## [2.0.4] - 2026-08-12

### Changed

- Bump pinned `pyasic` dependency from `0.78.8` to `0.79.0`. Reviewed the upstream diff
  and confirmed the BOSMiner `send_config()` model-corruption issue that
  `braiins_legacy` guards against is still present and unchanged in `0.79.0`, so the
  dedicated S9 backend remains required regardless of this bump. Full test suite and
  `ruff` pass against the new pin.

## [2.0.3] - unreleased prior to changelog

Baseline version prior to this changelog's introduction.
