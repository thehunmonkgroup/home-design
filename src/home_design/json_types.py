"""Shared JSON type aliases and pointer utilities."""

from __future__ import annotations

from copy import deepcopy
from typing import TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class JsonPointer:
    """Resolve and mutate RFC 6901-style pointers on JSON objects."""

    @staticmethod
    def tokens(pointer: str) -> list[str]:
        """Decode a JSON pointer.

        :param pointer: Pointer beginning with ``/`` or the empty root pointer.
        :returns: Decoded pointer tokens.
        :raises ValueError: If the pointer syntax is invalid.
        """
        if pointer == "":
            return []
        if not pointer.startswith("/"):
            raise ValueError(f"JSON pointer must start with '/': {pointer}")
        return [
            part.replace("~1", "/").replace("~0", "~")
            for part in pointer[1:].split("/")
        ]

    @classmethod
    def get(cls, document: JsonValue, pointer: str) -> JsonValue:
        """Read a value at a JSON pointer.

        :param document: JSON document to inspect.
        :param pointer: RFC 6901 pointer.
        :returns: Deep copy of the selected value.
        :raises KeyError: If an object member is missing.
        :raises IndexError: If an array index is outside the array.
        :raises TypeError: If traversal encounters a scalar.
        """
        current = document
        for token in cls.tokens(pointer):
            if isinstance(current, dict):
                current = current[token]
            elif isinstance(current, list):
                current = current[cls._array_index(token, len(current))]
            else:
                raise TypeError(f"Cannot traverse scalar at {pointer}")
        return deepcopy(current)

    @classmethod
    def set(cls, document: JsonValue, pointer: str, value: JsonValue) -> None:
        """Replace or add a value at a JSON pointer.

        :param document: JSON document to mutate.
        :param pointer: RFC 6901 pointer.
        :param value: Replacement value.
        :raises ValueError: If the root document is targeted.
        :raises KeyError: If a parent object member is missing.
        :raises IndexError: If an array index is invalid.
        :raises TypeError: If traversal encounters a scalar.
        """
        tokens = cls.tokens(pointer)
        if not tokens:
            raise ValueError("Replacing the root document is not supported")
        parent = cls._resolve_parent(document, tokens[:-1])
        token = tokens[-1]
        if isinstance(parent, dict):
            parent[token] = deepcopy(value)
        elif isinstance(parent, list):
            index = cls._array_index(token, len(parent), append=True)
            if index == len(parent):
                parent.append(deepcopy(value))
            else:
                parent[index] = deepcopy(value)
        else:
            raise TypeError(f"Cannot set a child of a scalar at {pointer}")

    @classmethod
    def remove(cls, document: JsonValue, pointer: str) -> JsonValue:
        """Remove and return a value at a JSON pointer.

        :param document: JSON document to mutate.
        :param pointer: RFC 6901 pointer.
        :returns: Removed value.
        :raises ValueError: If the root document is targeted.
        :raises KeyError: If an object member is missing.
        :raises IndexError: If an array index is invalid.
        :raises TypeError: If traversal encounters a scalar.
        """
        tokens = cls.tokens(pointer)
        if not tokens:
            raise ValueError("Removing the root document is not supported")
        parent = cls._resolve_parent(document, tokens[:-1])
        token = tokens[-1]
        if isinstance(parent, dict):
            return parent.pop(token)
        if isinstance(parent, list):
            return parent.pop(cls._array_index(token, len(parent)))
        raise TypeError(f"Cannot remove a child of a scalar at {pointer}")

    @classmethod
    def _resolve_parent(cls, document: JsonValue, tokens: list[str]) -> JsonValue:
        current = document
        for token in tokens:
            if isinstance(current, dict):
                current = current[token]
            elif isinstance(current, list):
                current = current[cls._array_index(token, len(current))]
            else:
                raise TypeError("Cannot traverse a scalar JSON value")
        return current

    @staticmethod
    def _array_index(token: str, length: int, append: bool = False) -> int:
        """Reject negative and noncanonical array positions before an edit can target another item."""
        if append and token == "-":
            return length
        if (
            not token.isascii()
            or not token.isdecimal()
            or (len(token) > 1 and token.startswith("0"))
        ):
            raise ValueError(f"Invalid JSON Pointer array index {token}")
        index = int(token)
        if index >= length + int(append):
            raise IndexError(
                f"JSON Pointer array index {index} is outside length {length}"
            )
        return index
