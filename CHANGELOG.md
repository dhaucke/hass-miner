# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
