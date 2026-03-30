"""io-gita cold start recovery — hierarchical zone ID + dual-scan fingerprinting.

v4 fix: addresses the 11.1% accuracy failure via:
  - Strategy B: Zone-first, node-second (7-12 classes, not 539)
  - Strategy C: Dual-scan fingerprinting (scan-move-scan for corridor disambiguation)
  - Safety rules S1-S7 enforced throughout

ADR-003: io-gita is CORE intelligence, not optional fallback.
ADR-007: Safety scanner independence — io-gita never overrides hardware safety.
ADR-NEW: Hierarchical ID — zone first, node second.
ADR-NEW: Dual-scan — two scans minimum for corridor disambiguation.
ADR-NEW: Honest testing — calibration != evaluation data, always.
"""
from .zone_identifier import (
    ZoneIdentifier,
    HierarchicalZoneIdentifier,
    generate_zone_scan,
    extract_16_features,
    extract_zone_features,
)
from .cold_start import ColdStartStateManager as ColdStartRecovery, RecoveryResult, boot_recovery
from .safety_checker import SafetyChecker, ClearanceResult
from .dual_scan import DualScanFingerprint, combine_scans

__all__ = [
    "ZoneIdentifier",
    "HierarchicalZoneIdentifier",
    "generate_zone_scan",
    "extract_16_features",
    "ColdStartRecovery",
    "RecoveryResult",
    "boot_recovery",
    "SafetyChecker",
    "ClearanceResult",
    "DualScanFingerprint",
    "combine_scans",
]
