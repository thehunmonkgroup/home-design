"""Explicit construction and service participants for physical penetration-interface parts."""

from __future__ import annotations

from dataclasses import replace

from home_design.construction import Authoring
from home_design.errors import ResolutionError
from home_design.mounted_parts import MountedParts
from home_design.resolved import ResolvedElement
from home_design.solids import SolidOperations


class ServiceInterfaces:
    """Validate surviving participants without inferring connection or barrier performance."""

    HOST_KINDS: frozenset[str] = frozenset(
        {
            "wall",
            "slab",
            "roof",
            "footing",
            "member",
            "curvedMember",
            "framing",
            "wallFraming",
            "planarFraming",
            "memberAssembly",
            "panel",
            "masonryPart",
        }
    )
    SERVICE_KINDS: frozenset[str] = frozenset(
        {"serviceDevice", "serviceRoute", "serviceFitting", "serviceInsulation"}
    )

    @classmethod
    def refresh(cls, elements: dict[str, ResolvedElement]) -> None:
        """Retain scoped host identity and reject duplicated stock after cavity composition/cuts."""
        for element in tuple(elements.values()):
            if element.kind != "envelopePart" or "interface" not in element.data:
                continue
            interface = Authoring.object(element.data["interface"])
            host = MountedParts.reference(elements, Authoring.object(interface["host"]))
            if host.kind not in cls.HOST_KINDS or not host.meshes:
                raise ResolutionError(
                    "A service interface requires a surviving construction host"
                )
            services = [
                elements[Authoring.text(Authoring.object(reference)["element"])]
                for reference in Authoring.array(interface["services"])
            ]
            if any(
                service.kind not in cls.SERVICE_KINDS or not service.meshes
                for service in services
            ):
                raise ResolutionError(
                    "A service interface requires surviving physical services"
                )
            for participant in [host, *services]:
                if any(
                    SolidOperations.intersection(mesh, other) is not None
                    for mesh in element.meshes
                    for other in participant.meshes
                ):
                    raise ResolutionError(
                        f"Service interface {element.element_id} overlaps participant "
                        + f"{participant.element_id}; resolve its fabrication, cavity ownership or owned cut"
                    )
            elements[element.element_id] = replace(
                element,
                data={
                    **element.data,
                    "interfaceHostId": host.element_id,
                    "interfaceServiceIds": sorted(
                        service.element_id for service in services
                    ),
                },
            )
