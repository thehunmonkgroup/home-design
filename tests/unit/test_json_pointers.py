"""JSON Pointer edits reject ambiguous array positions before changing design intent."""

from __future__ import annotations

import pytest

from home_design.json_types import JsonObject, JsonPointer


@pytest.mark.parametrize("token", ["-1", "+1", "01", " 1", "١"])
def test_noncanonical_array_indices_cannot_read_or_change_another_item(
    token: str,
) -> None:
    """Invalid array syntax cannot acquire Python's negative-index or integer parsing semantics."""
    source: JsonObject = {"layers": [{"id": "outer"}, {"id": "inner"}]}
    for operation in (
        lambda: JsonPointer.get(source, f"/layers/{token}"),
        lambda: JsonPointer.set(source, f"/layers/{token}", {}),
        lambda: JsonPointer.remove(source, f"/layers/{token}"),
        lambda: JsonPointer.set(source, f"/layers/{token}/id", "wrong"),
    ):
        with pytest.raises(ValueError):
            operation()
    assert source == {"layers": [{"id": "outer"}, {"id": "inner"}]}


def test_explicit_append_and_object_numeric_names_remain_supported() -> None:
    """Array appending is explicit and dictionary keys do not inherit array restrictions."""
    source: JsonObject = {"layers": [], "metadata": {"-1": "name"}}
    JsonPointer.set(source, "/layers/-", {"id": "first"})
    JsonPointer.set(source, "/layers/1", {"id": "second"})
    assert JsonPointer.get(source, "/layers/1/id") == "second"
    assert JsonPointer.get(source, "/metadata/-1") == "name"
    with pytest.raises(IndexError):
        JsonPointer.set(source, "/layers/3", {})
