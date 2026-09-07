"""Individually modeled masonry units, mortar and grout volumes."""

from __future__ import annotations

from home_design.components import ConstructionResolver
from home_design.construction import Authoring
from home_design.fabrication import FabricationGeometry
from home_design.json_types import JsonObject
from home_design.resolved import ResolvedElement
from home_design.solids import SolidOperations


class MasonryParts:
    """Place a typed material solid for explicit masonry composition."""

    @staticmethod
    def resolve(
        construction: ConstructionResolver, element_id: str, source: JsonObject
    ) -> ResolvedElement:
        """Resolve fabricated unit geometry and retain its role and physical quantities."""
        definition = construction.context.types[Authoring.text(source["type"])]
        frame = construction.placement(Authoring.object(source["placement"]))
        mesh = frame.mesh(FabricationGeometry.resolve(definition))
        storey = source.get("storey")
        return ResolvedElement(
            element_id,
            "masonryPart",
            Authoring.text(source["name"]),
            storey if isinstance(storey, str) else None,
            (mesh,),
            {
                "typeId": source["type"],
                "role": definition["role"],
                "materialId": definition["material"],
                "placement": frame.to_dict(),
                "netVolumeMm3": SolidOperations.volume(mesh),
            },
        )
