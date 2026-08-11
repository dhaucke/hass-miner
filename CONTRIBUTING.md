# Contributing

Contributions are welcome for bug fixes, new miner support, documentation and tests.

## Workflow

1. Fork the repository.
2. Create a branch from `main`.
3. Keep changes focused and update documentation when behavior changes.
4. Add or update regression tests for code changes.
5. Run the local checks.
6. Open a pull request against `main`.

## Local checks

```bash
python3 -m pip install -r requirements.txt
python3 -m ruff check .
python3 -m pytest -q
```

GitHub Actions also run HACS validation and Home Assistant hassfest checks.

## Miner support and write operations

New miner families should start read-only. Do not enable firmware-specific configuration writes based only on model-name guesses or generic library detection.

For write support, include enough evidence to validate the target hardware/firmware path and add regression coverage. When maintainers do not have the hardware, sanitized diagnostics and read-only API samples are useful.

Never include real passwords, private keys, pool credentials or wallet addresses in fixtures, logs, issues or pull requests.

## Bug reports

Please include:

- Home Assistant version,
- hass-miner version,
- miner model and firmware,
- steps to reproduce,
- expected and actual behavior,
- relevant Home Assistant logs,
- diagnostics export where useful.

## License

By contributing, you agree that your contributions are licensed under the repository's MIT License.
