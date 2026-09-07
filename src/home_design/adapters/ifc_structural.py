"""Native structural member classifications shared by occurrences and role-specific stock types."""

from __future__ import annotations

from ifcopenshell.entity_instance import entity_instance

from home_design.construction import Authoring
from home_design.json_types import JsonObject


class IfcStructural:
    """Preserve authored structural function independently of straight or curved geometry."""

    @staticmethod
    def assembly_predefined(product: entity_instance, data: JsonObject) -> None:
        """Preserve assembly function on native objects and on their matching role variants."""
        role = Authoring.text(data.get("assemblyType") or "Assembly")
        product.PredefinedType = "TRUSS" if role == "truss" else "USERDEFINED"
        if product.is_a("IfcElementType"):
            product.ElementType = role
        else:
            product.ObjectType = role

    ROLES: dict[str, tuple[str, str]] = {
        "beam": ("IfcBeam", "BEAM"),
        "header": ("IfcBeam", "LINTEL"),
        "joist": ("IfcBeam", "JOIST"),
        "column": ("IfcColumn", "COLUMN"),
        "brace": ("IfcMember", "BRACE"),
        "topChord": ("IfcMember", "CHORD"),
        "bottomChord": ("IfcMember", "CHORD"),
        "topPlate": ("IfcMember", "PLATE"),
        "bottomPlate": ("IfcMember", "PLATE"),
        "plate": ("IfcMember", "PLATE"),
        "post": ("IfcMember", "POST"),
        "purlin": ("IfcMember", "PURLIN"),
        "rafter": ("IfcMember", "RAFTER"),
        "hip": ("IfcMember", "RAFTER"),
        "valley": ("IfcMember", "RAFTER"),
        "stringer": ("IfcMember", "STRINGER"),
        "stud": ("IfcMember", "STUD"),
        "kingStud": ("IfcMember", "STUD"),
        "jackStud": ("IfcMember", "STUD"),
        "crippleStud": ("IfcMember", "STUD"),
    }

    @staticmethod
    def role(data: JsonObject) -> str:
        """Read a generated member's construction role before its generic geometry role."""
        return Authoring.text(data.get("constructionRole", data.get("role", "other")))

    @classmethod
    def classification(cls, data: JsonObject) -> tuple[str, str]:
        """Use an IFC4 role when its meaning matches, retaining unsupported roles explicitly."""
        return cls.ROLES.get(cls.role(data), ("IfcMember", "USERDEFINED"))

    @classmethod
    def predefined(cls, product: entity_instance, data: JsonObject) -> None:
        """Assign matching native classifications and durable authored role labels."""
        product.PredefinedType = cls.classification(data)[1]
        if product.is_a("IfcElementType"):
            product.ElementType = cls.role(data)
        else:
            product.ObjectType = cls.role(data)
