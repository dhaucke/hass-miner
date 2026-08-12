# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
