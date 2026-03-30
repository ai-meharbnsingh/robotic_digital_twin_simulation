"""
Warehouse Designer v2 — layout generation and conveyor design.

Phase 15: 3D GUI support modules.

Modules:
  layout_generator — auto-edge, zone detection, template scaling, connectivity, metrics
  conveyor_designer — segment generation, divert points, lane wiring, YAML export
"""

from designer.layout_generator import LayoutGenerator
from designer.conveyor_designer import ConveyorDesigner

__all__ = ["LayoutGenerator", "ConveyorDesigner"]
