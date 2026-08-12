# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.0.4] - 2026-08-12

### Changed

- Bump pinned `pyasic` dependency from `0.78.8` to `0.79.0`. Reviewed the upstream diff
  and confirmed the BOSMiner `send_config()` model-corruption issue that
  `braiins_legacy` guards against is still present and unchanged in `0.79.0`, so the
  dedicated S9 backend remains required regardless of this bump. Full test suite and
  `ruff` pass against the new pin.

## [2.0.3] - unreleased prior to changelog

Baseline version prior to this changelog's introduction.
