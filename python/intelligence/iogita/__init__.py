"""
io-gita intelligence module.

- ZoneIdentifier: wraps sg_engine Network, extracts features, runs ODE
- ColdStartRecovery: saves/loads state, generates recovery hints
- FleetAtlas: multi-robot fingerprint aggregation, map change detection

Uses sg_engine from system path if available.
Falls back to inline Hopfield network otherwise.
"""

from intelligence.iogita.zone_identifier import ZoneIdentifier
from intelligence.iogita.cold_start import ColdStartRecovery
from intelligence.iogita.fleet_atlas import FleetAtlas

__all__ = ["ZoneIdentifier", "ColdStartRecovery", "FleetAtlas"]
