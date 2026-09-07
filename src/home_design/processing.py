"""Explicit prerequisites for shared construction processing and coordination stages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from home_design.cavities import CavityComposition, CavityRegion
from home_design.circuit_schedules import CircuitSchedules
from home_design.errors import ResolutionError
from home_design.hardware import HardwareComponents
from home_design.json_types import JsonObject
from home_design.member_assemblies import MemberAssemblies
from home_design.mounted_parts import MountedParts, CoordinationVolumes
from home_design.penetrations import Penetrations
from home_design.resolved import ResolvedElement
from home_design.service_coordination import ServiceCoordination
from home_design.service_insulation import ServiceInsulation
from home_design.service_interfaces import ServiceInterfaces
from home_design.service_routes import ServiceRoutes
from home_design.services import ServiceNetworks


@dataclass(slots=True)
class ProcessingContext:
    """Typed shared state produced and consumed by ordered construction stages."""

    elements: dict[str, ResolvedElement]
    relationships: JsonObject
    cavity_regions: dict[tuple[str, int], CavityRegion] | None = None
    networks: ServiceNetworks | None = None
    completed: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProcessingStage:
    """One named operation and the completed evidence it requires before execution."""

    name: str
    requires: frozenset[str]
    apply: Callable[[ProcessingContext], None]


class ConstructionPipeline:
    """Validate stage prerequisites before modifying any resolved construction state."""

    def __init__(self, stages: tuple[ProcessingStage, ...]) -> None:
        """Reject duplicate, missing or out-of-order stage dependencies immediately."""
        self.stages: tuple[ProcessingStage, ...] = stages
        available = {"geometry"}
        for stage in stages:
            if stage.name in available:
                raise ResolutionError(
                    f"Duplicate construction stage: {stage.name}",
                    code="pipeline.duplicate-stage",
                )
            if missing := stage.requires - available:
                details: JsonObject = {
                    "stage": stage.name,
                    "missing": [item for item in sorted(missing)],
                }
                raise ResolutionError(
                    f"Construction stage {stage.name} requires prior stages: {sorted(missing)}",
                    code="pipeline.missing-prerequisite",
                    details=details,
                )
            available.add(stage.name)

    def run(
        self, elements: dict[str, ResolvedElement], relationships: JsonObject
    ) -> ProcessingContext:
        """Process one source snapshot and retain the completed stage evidence."""
        context = ProcessingContext(dict(elements), relationships)
        for stage in self.stages:
            try:
                stage.apply(context)
            except ResolutionError as error:
                error.details.setdefault("stage", stage.name)
                raise
            context.completed.append(stage.name)
        return context

    @classmethod
    def standard(cls) -> ConstructionPipeline:
        """Bind domain implementations to the shared physical-processing contract."""
        return cls(
            (
                ProcessingStage("cavities", frozenset({"geometry"}), cls._cavities),
                ProcessingStage(
                    "cuts",
                    frozenset({"cavities"}),
                    lambda state: Penetrations.apply(state.elements),
                ),
                ProcessingStage("net-cavities", frozenset({"cuts"}), cls._net_cavities),
                ProcessingStage(
                    "routes",
                    frozenset({"net-cavities"}),
                    lambda state: ServiceRoutes.refresh(state.elements),
                ),
                ProcessingStage(
                    "insulation",
                    frozenset({"routes"}),
                    lambda state: ServiceInsulation.refresh(state.elements),
                ),
                ProcessingStage(
                    "members",
                    frozenset({"net-cavities"}),
                    lambda state: MemberAssemblies.refresh(state.elements),
                ),
                ProcessingStage(
                    "hardware",
                    frozenset({"members", "insulation"}),
                    lambda state: HardwareComponents.participants(state.elements),
                ),
                ProcessingStage(
                    "mounted-parts",
                    frozenset({"hardware"}),
                    lambda state: MountedParts.refresh(state.elements),
                ),
                ProcessingStage(
                    "service-interfaces",
                    frozenset({"mounted-parts", "insulation"}),
                    lambda state: ServiceInterfaces.refresh(state.elements),
                ),
                ProcessingStage(
                    "service-clearances",
                    frozenset({"service-interfaces"}),
                    lambda state: ServiceCoordination.refresh(state.elements),
                ),
                ProcessingStage(
                    "access",
                    frozenset({"mounted-parts", "service-clearances"}),
                    lambda state: CoordinationVolumes.access(state.elements),
                ),
                ProcessingStage(
                    "barriers",
                    frozenset({"access", "net-cavities"}),
                    lambda state: CoordinationVolumes.barriers(state.elements),
                ),
                ProcessingStage(
                    "networks", frozenset({"barriers", "routes"}), cls._networks
                ),
                ProcessingStage("circuits", frozenset({"networks"}), cls._circuits),
            )
        )

    @staticmethod
    def _cavities(state: ProcessingContext) -> None:
        """Retain authoritative pre-cut cavity regions for final quantity reconciliation."""
        state.cavity_regions = CavityComposition.apply(state.elements)

    @staticmethod
    def _net_cavities(state: ProcessingContext) -> None:
        """Refresh material ownership against the exact regions produced before cutting."""
        if state.cavity_regions is None:
            raise ResolutionError("Cavity refresh requires captured cavity regions")
        CavityComposition.refresh(state.elements, state.cavity_regions)

    @staticmethod
    def _networks(state: ProcessingContext) -> None:
        """Resolve service connectivity after physical construction interfaces stabilize."""
        state.networks = ServiceNetworks(state.elements, state.relationships)
        state.networks.resolve()

    @staticmethod
    def _circuits(state: ProcessingContext) -> None:
        """Evaluate electrical schedules against the same resolved port graph."""
        if state.networks is None:
            raise ResolutionError("Circuit schedules require resolved service networks")
        CircuitSchedules(state.elements, state.networks.adjacency).resolve()
