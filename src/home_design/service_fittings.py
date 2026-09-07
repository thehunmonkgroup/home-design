"""Placed service fittings with generated ports, physical stock and reusable passage cuts."""

from __future__ import annotations

from home_design.capabilities import ComponentRegistry

from dataclasses import replace

from home_design.components import ConstructionResolver
from home_design.construction import Authoring
from home_design.constants import GEOMETRY_TOLERANCE_MM
from home_design.errors import ResolutionError
from home_design.electrical import ElectricalDevices
from home_design.fitting_geometry import FittingGeometry, FittingShape
from home_design.geometry import number, vector3
from home_design.json_types import JsonObject
from home_design.mechanical import MechanicalDucts
from home_design.resolved import ResolvedElement
from home_design.plumbing import PlumbingRoutes
from home_design.service_ports import ServicePorts
from home_design.service_routes import ServiceRoutes
from home_design.solids import SolidOperations


class ServiceFittings:
    """Place generated fitting geometry without decoupling its ports from its solid interfaces."""

    KINDS: frozenset[str] = ComponentRegistry.resolver_kinds("fitting")

    @staticmethod
    def ports(definition: JsonObject, shape: FittingShape) -> JsonObject:
        """Describe each local mating frame using the reusable stock's medium and technology."""
        forward = definition.get("flow", "bidirectional") == "forward"
        overrides = Authoring.object(definition.get("portOverrides", {}))
        unknown = set(overrides) - set(shape.ports)
        if unknown:
            raise ResolutionError(
                f"Unknown fitting port overrides: {', '.join(sorted(unknown))}"
            )
        return {
            key: {
                "position": list(frame.origin),
                "direction": list(frame.z),
                "up": list(frame.y),
                "section": section,
                "medium": definition["medium"],
                "connectionType": definition["connectionType"],
                **(
                    {"function": definition["function"]}
                    if "function" in definition
                    else {}
                ),
                "flow": (
                    ("sink" if key == "start" else "source")
                    if forward
                    else "bidirectional"
                ),
                **Authoring.object(overrides.get(key, {})),
            }
            for key, (frame, section) in shape.ports.items()
        }

    @classmethod
    def resolve(
        cls, construction: ConstructionResolver, element_id: str, source: JsonObject
    ) -> ResolvedElement:
        """Transform physical material and construction volumes through the same complete placement."""
        definition = construction.component_type(source)
        family = Authoring.text(definition["family"])
        ServiceRoutes.validate_family(definition)
        if "electrical" in definition:
            ElectricalDevices.validate_frequency(
                Authoring.object(definition["electrical"])
            )
        shape = FittingGeometry(
            definition, number(source.get("clearance", 0), "fitting clearance")
        ).resolve()
        material = Authoring.text(definition["material"])
        body = shape.body or SolidOperations.difference(
            shape.volumes["envelope"],
            [shape.volumes["bore"]] if "bore" in shape.volumes else [],
        )
        if body is None:
            raise ResolutionError("Service fitting has no physical material")
        frame = construction.placement(Authoring.object(source["placement"]))
        if Authoring.object(definition["geometry"])["kind"] == "trap":
            path = [
                frame.point(vector3(point, "trap centerline"))
                for point in Authoring.array(shape.data["path"])
            ]
            if (
                min(point[2] for point in path)
                >= min(path[0][2], path[-1][2]) - GEOMETRY_TOLERANCE_MM
            ):
                raise ResolutionError(
                    "A placed trap requires a lowered return below both interfaces"
                )
        body = frame.mesh(body)
        body = replace(body, role="body", material_id=material)
        ports = ServicePorts.resolve(
            cls.ports(definition, shape),
            frame,
            Authoring.object(source.get("portStates", {})),
        )
        return ResolvedElement(
            element_id,
            "serviceFitting",
            Authoring.text(source["name"]),
            Authoring.text(source["storey"]) if "storey" in source else None,
            (body,),
            {
                **shape.data,
                **PlumbingRoutes.resolve(definition, source, []),
                **MechanicalDucts.resolve(definition, source),
                **(
                    {"electrical": definition["electrical"]}
                    if "electrical" in definition
                    else {}
                ),
                "typeId": source["type"],
                "family": family,
                "role": Authoring.object(definition["geometry"])["kind"],
                "materialId": material,
                "placement": frame.to_dict(),
                "ports": ports,
                "portGroups": [list(ports)] if len(ports) > 1 else [],
                "netVolumeMm3": SolidOperations.volume(body),
                "constructionVolumeMm3": {
                    key: SolidOperations.volume(mesh)
                    for key, mesh in shape.volumes.items()
                },
            },
            {key: frame.mesh(mesh) for key, mesh in shape.volumes.items()},
        )
