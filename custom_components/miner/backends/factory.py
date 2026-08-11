"""Backend selection for the Miner integration."""
from __future__ import annotations

import logging

from .base import MinerBackend
from .base import UnsafeConfigurationError
from .braiins_legacy_state import BraiinsLegacyS9Backend
from .pyasic_backend import PyasicBackend

_LOGGER = logging.getLogger(__name__)


async def async_create_backend(
    miner,
    *,
    minimum_power: int = 15,
    maximum_power: int = 10000,
) -> MinerBackend:
    """Return the safest backend supported for a discovered miner.

    Legacy BOSMiner devices are probed for the two independent S9 identity
    sources. Only a positive match enables the dedicated S9 backend. Any other
    legacy Braiins device remains on the generic compatibility backend instead
    of receiving S9-specific assumptions.
    """
    if type(miner).__name__ == "BOSMiner":
        candidate = BraiinsLegacyS9Backend(miner)
        try:
            await candidate.async_validate_identity()
        except (UnsafeConfigurationError, OSError, RuntimeError) as err:
            _LOGGER.info(
                "Legacy BOSMiner did not pass dedicated S9 validation; "
                "using generic pyasic backend: %s",
                err,
            )
        else:
            return candidate

    return PyasicBackend(
        miner,
        minimum_power=minimum_power,
        maximum_power=maximum_power,
    )
