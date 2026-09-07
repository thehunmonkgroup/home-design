"""Authoritative component capabilities shared across authoring, resolution and export."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Mapping
from typing import ClassVar, Literal

from home_design.errors import ResolutionError
from home_design.json_types import JsonObject, JsonPointer
from home_design.schema_diagnostics import SchemaDiagnostics

ReferenceRole = Literal[
    "placement",
    "type",
    "material",
    "containment",
    "ownership",
    "connection",
    "relationship",
    "requirement",
    "reference",
]
HostMode = Literal["wall", "surface", "member", "route", "component"]


@dataclass(frozen=True, slots=True)
class ComponentCapability:
    """Declare one supported family without coupling its geometry to adapters."""

    kind: str
    label: str
    resolver: str
    ifc_class: str
    type_kind: str | None = None
    ifc_type_class: str | None = None
    discipline: str = "envelope"
    host_modes: tuple[HostMode, ...] = ()
    cavity_part: bool = False
    cavity_host: bool = False
    generated_members: bool = False
    scoped_member_host: bool = False
    default_visible: bool = True
    host_targets: tuple[str, ...] = ()

    def to_dict(self) -> JsonObject:
        """Expose compact supported capabilities for extension audits and AI discovery."""
        return {
            "kind": self.kind,
            "label": self.label,
            "resolver": self.resolver,
            "typeKind": self.type_kind,
            "ifcClass": self.ifc_class,
            "ifcTypeClass": self.ifc_type_class,
            "discipline": self.discipline,
            "hostModes": list(self.host_modes),
            "cavityPart": self.cavity_part,
            "cavityHost": self.cavity_host,
            "generatedMembers": self.generated_members,
            "scopedMemberHost": self.scoped_member_host,
            "defaultVisible": self.default_visible,
            "hostTargets": list(self.host_targets),
        }


class ComponentRegistry:
    """Centralize family registration while domain modules implement their geometry."""

    _DECLARATIONS: ClassVar[tuple[ComponentCapability, ...]] = (
        ComponentCapability(
            "wall",
            "Wall",
            "wall",
            "IfcWall",
            "wallType",
            "IfcWallType",
            host_modes=("wall",),
            cavity_host=True,
        ),
        ComponentCapability(
            "slab",
            "Floor or deck slab",
            "slab",
            "IfcSlab",
            "slabType",
            "IfcSlabType",
            host_modes=("surface",),
            cavity_host=True,
        ),
        ComponentCapability(
            "roof",
            "Roof",
            "roof",
            "IfcRoof",
            "roofType",
            "IfcRoofType",
            host_modes=("surface",),
            cavity_host=True,
        ),
        ComponentCapability("opening", "Rough opening", "opening", "IfcOpeningElement"),
        ComponentCapability(
            "penetration",
            "Hole or recess",
            "penetration",
            "IfcOpeningElement",
            host_targets=(
                "wall",
                "slab",
                "roof",
                "footing",
                "member",
                "framing",
                "wallFraming",
                "planarFraming",
                "memberAssembly",
                "curvedMember",
                "hardware",
                "masonryPart",
                "accessory",
                "envelopePart",
                "serviceDevice",
                "serviceRoute",
                "serviceFitting",
                "serviceInsulation",
                "reinforcingBar",
                "reinforcingMesh",
                "panel",
            ),
        ),
        ComponentCapability(
            "door", "Door", "fill", "IfcDoor", "doorType", "IfcDoorType"
        ),
        ComponentCapability(
            "window", "Window", "fill", "IfcWindow", "windowType", "IfcWindowType"
        ),
        ComponentCapability(
            "space",
            "Room or space",
            "space",
            "IfcSpace",
            "spaceType",
            "IfcSpaceType",
            default_visible=False,
        ),
        ComponentCapability(
            "assembly", "Component assembly", "assembly", "IfcElementAssembly"
        ),
        ComponentCapability(
            "member",
            "Structural member",
            "construction",
            "IfcMember",
            "memberType",
            "IfcMemberType",
            "framing",
            ("member",),
            cavity_part=True,
        ),
        ComponentCapability(
            "framing",
            "Repeated framing",
            "construction",
            "IfcElementAssembly",
            "memberType",
            "IfcMemberType",
            "framing",
            cavity_part=True,
            generated_members=True,
        ),
        ComponentCapability(
            "wallFraming",
            "Wall framing",
            "wall-framing",
            "IfcElementAssembly",
            "wallFramingType",
            "IfcElementAssemblyType",
            "framing",
            ("member",),
            cavity_part=True,
            generated_members=True,
            scoped_member_host=True,
            host_targets=("wall",),
        ),
        ComponentCapability(
            "planarFraming",
            "Floor or roof framing",
            "planar-framing",
            "IfcElementAssembly",
            "planarFramingType",
            "IfcElementAssemblyType",
            "framing",
            ("member",),
            cavity_part=True,
            generated_members=True,
            scoped_member_host=True,
            host_targets=("slab", "roof"),
        ),
        ComponentCapability(
            "memberAssembly",
            "Member assembly",
            "member-assembly",
            "IfcElementAssembly",
            discipline="framing",
            host_modes=("member", "component"),
            cavity_part=True,
            generated_members=True,
            scoped_member_host=True,
        ),
        ComponentCapability(
            "curvedMember",
            "Curved structural member",
            "curved",
            "IfcMember",
            "memberType",
            "IfcMemberType",
            "framing",
            ("member", "component"),
            cavity_part=True,
        ),
        ComponentCapability(
            "hardware",
            "Construction connector",
            "hardware",
            "IfcDiscreteAccessory",
            "hardwareType",
            "IfcDiscreteAccessoryType",
            "framing",
            ("component",),
            cavity_part=True,
        ),
        ComponentCapability(
            "masonryPart",
            "Masonry part",
            "masonry",
            "IfcBuildingElementPart",
            "masonryPartType",
            "IfcBuildingElementPartType",
            "framing",
            ("component",),
            cavity_part=True,
        ),
        ComponentCapability(
            "accessory",
            "Fixed accessory",
            "mounted",
            "IfcBuildingElementPart",
            "accessoryType",
            "IfcBuildingElementPartType",
            "accessories",
            ("component",),
            cavity_part=True,
        ),
        ComponentCapability(
            "envelopePart",
            "Envelope detail",
            "mounted",
            "IfcCovering",
            "envelopePartType",
            "IfcCoveringType",
            host_modes=("component",),
            cavity_part=True,
        ),
        ComponentCapability(
            "clearanceZone",
            "Access or clearance space",
            "coordination",
            "IfcVirtualElement",
            host_modes=("component",),
            default_visible=False,
        ),
        ComponentCapability(
            "barrierCheck",
            "Barrier continuity check",
            "coordination",
            "IfcVirtualElement",
            host_modes=("component",),
            default_visible=False,
        ),
        ComponentCapability(
            "serviceDevice",
            "Service device",
            "service",
            "IfcDistributionElement",
            "serviceDeviceType",
            "IfcDistributionElementType",
            "services",
            ("component",),
            cavity_part=True,
        ),
        ComponentCapability(
            "serviceRoute",
            "Pipe, duct or cable run",
            "route",
            "IfcFlowSegment",
            "serviceRouteType",
            "IfcDistributionElementType",
            "services",
            ("route", "component"),
            cavity_part=True,
        ),
        ComponentCapability(
            "serviceFitting",
            "Service fitting",
            "fitting",
            "IfcFlowFitting",
            "serviceFittingType",
            "IfcDistributionElementType",
            "services",
            ("route", "component"),
            cavity_part=True,
        ),
        ComponentCapability(
            "serviceInsulation",
            "Service insulation",
            "insulation",
            "IfcCovering",
            "serviceInsulationType",
            "IfcCoveringType",
            "services",
            ("component",),
            cavity_part=True,
            host_targets=("serviceRoute", "serviceFitting"),
        ),
        ComponentCapability(
            "serviceSystem",
            "Service system",
            "service",
            "IfcDistributionSystem",
            discipline="services",
        ),
        ComponentCapability(
            "serviceCircuit",
            "Service circuit",
            "service",
            "IfcDistributionCircuit",
            discipline="services",
        ),
        ComponentCapability(
            "reinforcingBar",
            "Reinforcing bar",
            "reinforcement",
            "IfcReinforcingBar",
            "reinforcingBarType",
            "IfcReinforcingBarType",
            "framing",
            cavity_part=True,
        ),
        ComponentCapability(
            "reinforcingMesh",
            "Reinforcing mesh",
            "reinforcement",
            "IfcReinforcingMesh",
            "reinforcingMeshType",
            "IfcReinforcingMeshType",
            "framing",
            ("component",),
            cavity_part=True,
        ),
        ComponentCapability(
            "fastenerGroup",
            "Fastener group",
            "hardware",
            "IfcMechanicalFastener",
            "fastenerType",
            "IfcMechanicalFastenerType",
            "framing",
            ("component",),
            cavity_part=True,
        ),
        ComponentCapability(
            "footing",
            "Foundation footing",
            "construction",
            "IfcFooting",
            "footingType",
            "IfcFootingType",
            "framing",
            ("surface",),
            cavity_host=True,
        ),
        ComponentCapability(
            "stair",
            "Stair flight",
            "construction",
            "IfcStairFlight",
            "stairType",
            "IfcStairFlightType",
            "framing",
        ),
        ComponentCapability(
            "railing",
            "Guard or railing",
            "construction",
            "IfcRailing",
            "railingType",
            "IfcRailingType",
        ),
        ComponentCapability(
            "panel",
            "Panel or screen",
            "panel",
            "IfcPlate",
            "panelType",
            "IfcPlateType",
            cavity_part=True,
        ),
        ComponentCapability(
            "terrain",
            "Terrain",
            "construction",
            "IfcGeographicElement",
            discipline="site",
        ),
        ComponentCapability(
            "sweep",
            "Swept construction detail",
            "construction",
            "IfcBuildingElementProxy",
            "sweepType",
            "IfcBuildingElementProxyType",
            cavity_part=True,
        ),
        ComponentCapability(
            "load", "Applied load", "construction", "IfcBuildingElementProxy"
        ),
        ComponentCapability(
            "detail",
            "Fabricated detail",
            "construction",
            "IfcBuildingElementProxy",
            "detailType",
            "IfcBuildingElementProxyType",
        ),
    )
    components: ClassVar[Mapping[str, ComponentCapability]] = MappingProxyType(
        {item.kind: item for item in _DECLARATIONS}
    )

    @classmethod
    def get(cls, kind: str) -> ComponentCapability:
        """Reject unregistered families instead of silently exporting empty placeholders."""
        try:
            return cls.components[kind]
        except KeyError as error:
            raise ResolutionError(
                f"Unsupported component kind: {kind}", code="component.unsupported-kind"
            ) from error

    @classmethod
    def kinds(cls, capability: str) -> frozenset[str]:
        """Select a declared boolean capability without maintaining duplicate kind lists."""
        if capability not in {
            "cavity_part",
            "cavity_host",
            "generated_members",
            "scoped_member_host",
        }:
            raise ValueError(f"Unknown component capability: {capability}")
        return frozenset(
            item.kind for item in cls.components.values() if getattr(item, capability)
        )

    @classmethod
    def hosts(cls, mode: str) -> tuple[str, ...]:
        """Return component families implementing a particular host coordinate frame."""
        return tuple(
            item.kind for item in cls.components.values() if mode in item.host_modes
        )

    @classmethod
    def resolver_kinds(cls, *names: str) -> frozenset[str]:
        """Select domain implementation families from the central dispatch declaration."""
        return frozenset(
            item.kind for item in cls.components.values() if item.resolver in names
        )

    @classmethod
    def type_classes(cls) -> dict[str, str]:
        """Return native default type classes, allowing shared stock types across families."""
        return {
            item.type_kind: item.ifc_type_class
            for item in cls.components.values()
            if item.type_kind is not None and item.ifc_type_class is not None
        }

    @classmethod
    def expected_types(cls, kind: str) -> tuple[str, ...]:
        """Keep invalid-source inspection available while enforcing known type pairings."""
        item = cls.components.get(kind)
        return (
            (item.type_kind,) if item is not None and item.type_kind is not None else ()
        )

    @classmethod
    def audit(cls, schema: JsonObject) -> list[str]:
        """Check schema/registry coverage and shared type declarations in both directions."""
        issues: list[str] = []
        kinds = SchemaDiagnostics(schema)
        for name, declared in (
            ("Element", set(cls.components)),
            ("ComponentType", set(cls.type_classes())),
        ):
            supported = kinds.kinds(JsonPointer.get(schema, f"/$defs/{name}"))
            if missing := supported - declared:
                issues.append(f"Unregistered {name} kinds: {sorted(missing)}")
            if extra := declared - supported:
                issues.append(
                    f"Registered {name} kinds absent from schema: {sorted(extra)}"
                )
        if len(cls.components) != len(cls._DECLARATIONS):
            issues.append("Duplicate component kind declarations")
        types: dict[str, str | None] = {}
        for item in cls._DECLARATIONS:
            if missing_hosts := set(item.host_targets) - cls.components.keys():
                issues.append(
                    f"Unknown host targets for {item.kind}: {sorted(missing_hosts)}"
                )
            if item.type_kind is not None:
                if (
                    item.type_kind in types
                    and types[item.type_kind] != item.ifc_type_class
                ):
                    issues.append(
                        f"Conflicting IFC class for shared type {item.type_kind}"
                    )
                types[item.type_kind] = item.ifc_type_class
                if item.ifc_type_class is None:
                    issues.append(f"Missing IFC type class for {item.kind}")
            if item.scoped_member_host and not item.generated_members:
                issues.append(
                    f"Scoped member host {item.kind} has no generated members"
                )
        return issues

    @staticmethod
    def reference_role(
        owner_registry: str, field: str, target_registry: str
    ) -> ReferenceRole:
        """Classify shared reference fields independently of names and geometry implementations."""
        if owner_registry == "requirements":
            return "requirement"
        if owner_registry == "relationships":
            return "relationship"
        if target_registry == "types":
            return "type"
        if target_registry == "materials":
            return "material"
        if owner_registry == "anchors":
            return "placement"
        if field == "storey":
            return "containment"
        if field in {"occupies", "owner"}:
            return "ownership"
        if field in {"participants", "interface", "members", "system", "schedule"}:
            return "connection"
        if field in {"clearances", "limits", "grade", "target", "coordinationChecks"}:
            return "requirement"
        if field in {
            "base",
            "top",
            "bottom",
            "datum",
            "path",
            "footprint",
            "geometry",
            "geometrySource",
            "axis",
            "follow",
            "location",
            "host",
            "placement",
            "nodes",
            "port",
            "eaveDatum",
        }:
            return "placement"
        return "reference"
