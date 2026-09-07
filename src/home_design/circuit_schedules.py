"""Authored power and communications circuit schedules with scoped rating and supply checks."""

from __future__ import annotations

from dataclasses import replace

from home_design.construction import Authoring
from home_design.electrical import ElectricalDevices
from home_design.errors import ResolutionError
from home_design.geometry import number
from home_design.json_types import JsonObject, JsonValue
from home_design.resolved import ResolvedElement
from home_design.service_ports import ServicePorts


class CircuitSchedules:
    """Check declared circuit data against actual network membership, without electrical sizing."""

    def __init__(
        self,
        elements: dict[str, ResolvedElement],
        adjacency: dict[tuple[str, str], set[tuple[str, str]]],
    ) -> None:
        """Consume the already validated port graph and final physical components."""
        self.elements: dict[str, ResolvedElement] = elements
        self.adjacency: dict[tuple[str, str], set[tuple[str, str]]] = adjacency

    def _terminal(
        self, reference: JsonValue, members: set[tuple[str, str]], function: str
    ) -> tuple[str, str]:
        """Require a scoped interface in this circuit with the intended electrical purpose."""
        key = ServicePorts.reference(reference)
        if key not in members:
            raise ResolutionError(
                f"Circuit schedule interface {key} is outside its circuit"
            )
        port = Authoring.object(
            Authoring.object(self.elements[key[0]].data["ports"])[key[1]]
        )
        if port.get("function") != function:
            raise ResolutionError(
                f"Circuit schedule interface {key} requires {function} function"
            )
        return key

    @staticmethod
    def _check(
        checks: list[JsonValue],
        identity: str,
        field: str,
        actual: JsonValue,
        limit: JsonValue,
        equal: bool = False,
    ) -> None:
        """Retain unknown checks and reject only contradictory authored values."""
        known = actual is not None and limit is not None
        passed = (
            (
                actual == limit
                if equal
                else number(actual, field) <= number(limit, field)
            )
            if known
            else False
        )
        if known and not passed:
            raise ResolutionError(
                f"Circuit rating {field} at {identity}: authored {actual} exceeds or conflicts with {limit}"
            )
        checks.append(
            {
                "elementId": identity,
                "field": field,
                "actual": actual,
                "limit": limit,
                "comparison": "equals" if equal else "atMost",
                "status": "satisfied" if known else "notChecked",
            }
        )

    def _ratings(
        self,
        members: set[tuple[str, str]],
        specification: JsonObject,
        panel: str,
        protection: str | None,
        signal: bool,
    ) -> list[JsonValue]:
        """Compare supply and explicitly authored current/data limits on relevant circuit interfaces."""
        checks: list[JsonValue] = []
        function = "signal" if signal else "power"
        relevant = {
            owner
            for owner, key in members
            if Authoring.object(
                Authoring.object(self.elements[owner].data["ports"])[key]
            ).get("function")
            == function
        }
        protection_rating = (
            Authoring.object(self.elements[protection].data.get("electrical", {})).get(
                "ratedCurrentA"
            )
            if protection
            else None
        )
        for identity in sorted(relevant):
            element = self.elements[identity]
            cable = Authoring.object(element.data.get("cable", {}))
            ratings = (
                cable
                if element.kind == "serviceRoute"
                else Authoring.object(element.data.get("electrical", {}))
            )
            if signal:
                self._check(
                    checks,
                    identity,
                    "dataRateMbps",
                    specification.get("dataRateMbps"),
                    ratings.get("dataRateMbps"),
                )
                continue
            self._check(
                checks,
                identity,
                "voltageV",
                specification["nominalVoltageV"],
                ratings.get("ratedVoltageV"),
            )
            if element.kind in {"serviceDevice", "serviceFitting"}:
                self._check(
                    checks,
                    identity,
                    "supply",
                    specification["supply"],
                    ratings.get("supply"),
                    True,
                )
                self._check(
                    checks,
                    identity,
                    "frequencyHz",
                    specification.get("frequencyHz"),
                    ratings.get("frequencyHz"),
                    True,
                )
            if identity in {panel, protection}:
                self._check(
                    checks,
                    identity,
                    "currentA",
                    specification.get("designCurrentA"),
                    ratings.get("ratedCurrentA"),
                )
                self._check(
                    checks,
                    identity,
                    "poles",
                    specification["poles"],
                    ratings.get("poles"),
                )
            if element.kind == "serviceRoute" and element.data.get("family") == "cable":
                self._check(
                    checks,
                    identity,
                    "currentA",
                    specification.get("designCurrentA"),
                    ratings.get("allowableCurrentA"),
                )
                if "maximumProtectionA" in ratings:
                    self._check(
                        checks,
                        identity,
                        "protectionCurrentA",
                        protection_rating,
                        ratings["maximumProtectionA"],
                    )
        return checks

    def _protection(
        self, specification: JsonObject, members: set[tuple[str, str]]
    ) -> str | None:
        """Reference a breaker/fuse outlet in this circuit without assuming that mounting protects it."""
        if "overcurrentProtection" not in specification:
            return None
        identity, key = self._terminal(
            specification["overcurrentProtection"], members, "power"
        )
        element = self.elements[identity]
        port = Authoring.object(Authoring.object(element.data["ports"])[key])
        if (
            element.kind != "serviceDevice"
            or element.data.get("role") not in {"circuitBreaker", "fuse"}
            or port["flow"] == "sink"
        ):
            raise ResolutionError(
                "Circuit overcurrent protection requires a breaker/fuse output port"
            )
        return identity

    def _loads(
        self,
        specification: JsonObject,
        members: set[tuple[str, str]],
        panel: tuple[str, str],
        protection: str | None,
    ) -> float:
        """Sum declared loads once and reject a declared load's path around its protective device."""
        loads: set[tuple[str, str]] = set()
        total = 0.0
        for value in Authoring.array(specification.get("loads", [])):
            load = Authoring.object(value)
            terminal = self._terminal(load["terminal"], members, "power")
            element = self.elements[terminal[0]]
            if (
                terminal in loads
                or element.kind != "serviceDevice"
                or element.data.get("role")
                in {"distributionPanel", "circuitBreaker", "fuse"}
            ):
                raise ResolutionError(
                    "Circuit loads require distinct device terminals, excluding supply and protection equipment"
                )
            loads.add(terminal)
            total += number(load["apparentPowerVA"], "circuit load")
        if protection and loads:
            pending = [panel]
            visited: set[tuple[str, str]] = set()
            while pending:
                key = pending.pop()
                if key in visited or key[0] == protection:
                    continue
                visited.add(key)
                pending.extend((self.adjacency[key] & members) - visited)
            if visited & loads:
                raise ResolutionError(
                    "A declared circuit load bypasses its overcurrent protection"
                )
        return total

    def resolve(self) -> None:
        """Produce stable schedule rows after ordinary system/circuit connectivity has passed."""
        numbers: set[tuple[str, str]] = set()
        for circuit in tuple(self.elements.values()):
            if circuit.kind != "serviceCircuit" or "schedule" not in circuit.data:
                continue
            schedule = Authoring.object(circuit.data["schedule"])
            signal = "communications" in schedule
            system_type = "communications" if signal else "electrical"
            if circuit.data["systemType"] != system_type:
                raise ResolutionError(
                    "Circuit schedule kind conflicts with its system type"
                )
            members = {
                ServicePorts.reference(value)
                for value in Authoring.array(circuit.data["members"])
            }
            for owner in {key[0] for key in members}:
                component = self.elements[owner]
                if (
                    component.kind == "serviceRoute"
                    and not {
                        (owner, key)
                        for key in Authoring.object(component.data["ports"])
                    }
                    <= members
                ):
                    raise ResolutionError(
                        "A scheduled circuit cannot split a route's endpoint membership"
                    )
            panel = self._terminal(
                schedule["panel"], members, "signal" if signal else "power"
            )
            source = self.elements[panel[0]]
            port = Authoring.object(Authoring.object(source.data["ports"])[panel[1]])
            if (
                source.kind != "serviceDevice"
                or source.data.get("role")
                != ("communicationsPanel" if signal else "distributionPanel")
                or port["flow"] == "sink"
            ):
                raise ResolutionError(
                    "Circuit schedule requires a matching panel output port"
                )
            number_key = panel[0], Authoring.text(schedule["number"])
            if number_key in numbers:
                raise ResolutionError(
                    f"Duplicate circuit number {number_key[1]} on panel {number_key[0]}"
                )
            numbers.add(number_key)
            specification = Authoring.object(schedule[system_type])
            if not signal:
                ElectricalDevices.validate_frequency(specification)
            protection = self._protection(specification, members)
            total = self._loads(specification, members, panel, protection)
            checks = self._ratings(members, specification, panel[0], protection, signal)
            row: JsonObject = {
                "id": circuit.element_id,
                "name": circuit.name,
                "systemId": circuit.data["system"],
                "systemType": system_type,
                **schedule,
                "componentIds": circuit.data["componentIds"],
                "ratingChecks": checks,
                "ratingStatus": (
                    "checked"
                    if all(
                        Authoring.object(check)["status"] == "satisfied"
                        for check in checks
                    )
                    else "partiallyChecked"
                ),
                "routeLengthMm": sum(
                    number(
                        self.elements[owner].data["centerlineLengthMm"], "route length"
                    )
                    for owner in sorted({key[0] for key in members})
                    if self.elements[owner].kind == "serviceRoute"
                ),
            }
            if not signal:
                row["connectedLoadVA"] = total if "loads" in specification else None
                row["loadBasis"] = (
                    "Authored terminal loads only; no demand factors or unlisted loads inferred"
                )
            self.elements[circuit.element_id] = replace(
                circuit, data={**circuit.data, "circuitSchedule": row}
            )
