# Continuous integration

GitHub Actions is enabled for this fork.

Development changes are expected to pass the repository's code checks plus Home Assistant/HACS validation before the backend rework is promoted from draft status.

The development workflow targets `develop`, `feature/**`, and `fix/**` branches where configured. Pull requests into `develop` or `main` are used as the review gate for the rework.
