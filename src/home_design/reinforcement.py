"""Explicit reinforcing bars, rounded ties and orthogonal reinforcement meshes."""

from __future__ import annotations

from home_design.capabilities import ComponentRegistry

import math

from home_design.components import ConstructionResolver
from home_design.construction import Authoring, ConstructionGeometry
from home_design.errors import ResolutionError
from home_design.geometry import number
from home_design.json_types import JsonObject
from home_design.resolved import ResolvedElement
from home_design.round_paths import RoundPath
from home_design.solids import SolidOperations


class Reinforcement:
    """Resolve authored steel geometry without inferring bar sizes or reinforcement design."""

    KINDS: frozenset[str] = ComponentRegistry.resolver_kinds("reinforcement")

    @classmethod
    def resolve(
        cls, construction: ConstructionResolver, element_id: str, source: JsonObject
    ) -> ResolvedElement:
        """Resolve one typed reinforcement item and retain source steel specifications."""
        definition = construction.context.types[Authoring.text(source["type"])]
        if source["kind"] == "reinforcingBar":
            return cls._bar(construction, element_id, source, definition)
        return cls._mesh(construction, element_id, source, definition)

    @staticmethod
    def _bar(
        construction: ConstructionResolver,
        element_id: str,
        source: JsonObject,
        definition: JsonObject,
    ) -> ResolvedElement:
        """Round an authored centerline and calculate its physical and analytic quantities."""
        diameter = number(definition["nominalDiameter"], "bar diameter")
        radius = number(source["bendRadius"], "bar bend radius")
        if radius < number(
            definition.get("minimumBendRadius", 0), "authored minimum bend radius"
        ):
            raise ResolutionError(
                "Bar bend radius is below its type's authored minimum"
            )
        points = [
            construction.point(value) for value in Authoring.array(source["path"])
        ]
        mesh, data = RoundPath(
            points,
            diameter,
            radius,
            number(source["chordTolerance"], "bar tolerance"),
            source.get("closed") is True,
        ).resolve(Authoring.text(definition["material"]))
        storey = source.get("storey")
        return ResolvedElement(
            element_id,
            "reinforcingBar",
            Authoring.text(source["name"]),
            storey if isinstance(storey, str) else None,
            (mesh,),
            {
                **data,
                "typeId": source["type"],
                "role": definition["role"],
                "materialId": definition["material"],
                "steelGrade": definition.get("steelGrade"),
                "barSurface": definition.get("surface", "plain"),
                "nominalDiameter": diameter,
                "bendRadius": radius,
                "closed": source.get("closed", False),
                "authoredPath": [list(point) for point in points],
                "chordTolerance": source["chordTolerance"],
            },
        )

    @staticmethod
    def _mesh(
        construction: ConstructionResolver,
        element_id: str,
        source: JsonObject,
        definition: JsonObject,
    ) -> ResolvedElement:
        """Generate orthogonal wire sets and count welded intersections only once."""
        length, width = number(source["length"], "mesh length"), number(
            source["width"], "mesh width"
        )
        longitudinal = number(
            definition["longitudinalDiameter"], "longitudinal diameter"
        )
        transverse = number(definition["transverseDiameter"], "transverse diameter")
        long_spacing = number(definition["longitudinalSpacing"], "longitudinal spacing")
        trans_spacing = number(definition["transverseSpacing"], "transverse spacing")
        if long_spacing < longitudinal or trans_spacing < transverse:
            raise ResolutionError(
                "Reinforcement mesh spacing is smaller than its parallel wire diameter"
            )
        long_count, trans_count = (
            math.floor(width / long_spacing) + 1,
            math.floor(length / trans_spacing) + 1,
        )
        if long_count + trans_count > 10000:
            raise ResolutionError("Reinforcement mesh requires more than 10000 wires")
        separation = number(
            source.get("layerSeparation", (longitudinal + transverse) / 2),
            "wire layer separation",
        )
        frame = construction.placement(Authoring.object(source["placement"]))
        material = Authoring.text(definition["material"])
        wires = [
            ConstructionGeometry.member(
                (0, index * long_spacing, 0),
                (length, index * long_spacing, 0),
                {"kind": "circle", "diameter": longitudinal},
                material,
                "body",
            )
            for index in range(long_count)
        ]
        wires.extend(
            ConstructionGeometry.member(
                (index * trans_spacing, 0, separation),
                (index * trans_spacing, width, separation),
                {"kind": "circle", "diameter": transverse},
                material,
                "body",
            )
            for index in range(trans_count)
        )
        mesh = SolidOperations.union(wires, material, "body")
        if mesh is None:
            raise ResolutionError("Reinforcement mesh has no physical wires")
        mesh = frame.mesh(mesh)
        storey = source.get("storey")
        return ResolvedElement(
            element_id,
            "reinforcingMesh",
            Authoring.text(source["name"]),
            storey if isinstance(storey, str) else None,
            (mesh,),
            {
                "typeId": source["type"],
                "role": "mesh",
                "materialId": definition["material"],
                "placement": frame.to_dict(),
                "length": length,
                "width": width,
                "longitudinalDiameter": longitudinal,
                "transverseDiameter": transverse,
                "longitudinalSpacing": long_spacing,
                "transverseSpacing": trans_spacing,
                "longitudinalCount": long_count,
                "transverseCount": trans_count,
                "steelGrade": definition.get("steelGrade"),
                "layerSeparation": separation,
                "totalWireLengthMm": long_count * length + trans_count * width,
                "netVolumeMm3": SolidOperations.volume(mesh),
            },
        )
