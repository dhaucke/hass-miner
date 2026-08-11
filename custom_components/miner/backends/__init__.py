"""Backend implementations for the Miner integration.

Backends isolate Home Assistant entities and coordinators from firmware-specific
APIs.  New firmware support should implement the protocol in ``base.py`` rather
than exposing library-specific objects to the Home Assistant layer.
"""
