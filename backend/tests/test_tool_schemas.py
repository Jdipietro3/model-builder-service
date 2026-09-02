"""Unit tests for app.orchestrator.tools: the pydantic -> LLM-tool-schema
converter (_clean_schema / _inline_refs / _strip_node / _walk_schema).

These tests do not hit the network, the DB, or the LLM — they operate purely
on `model_json_schema()` output.
"""

import json
from typing import Any, Literal

import pytest
from pydantic import Field

from app.orchestrator import tools
from app.orchestrator.tools import (
    _SCHEMA_LIST_KEYS,
    _SCHEMA_MAP_KEYS,
    _SCHEMA_VALUE_KEYS,
    _clean_schema,
    ToolInput,
)

# ---------------------------------------------------------------------------
# Test 1: every registered tool's cleaned schema is well-formed.


def _iter_schema_nodes(node):
    """Yield every schema-node dict in `node`, mirroring the real walker's
    traversal (recurse only through the JSON-Schema keywords, never through
    `properties`' field-name keys) so a field literally named e.g. "title"
    is not mistaken for a schema node.
    """
    if not isinstance(node, dict):
        return
    yield node
    for key in _SCHEMA_VALUE_KEYS:
        if isinstance(node.get(key), dict):
            yield from _iter_schema_nodes(node[key])
    for key in _SCHEMA_LIST_KEYS:
        if isinstance(node.get(key), list):
            for b in node[key]:
                yield from _iter_schema_nodes(b)
    for key in _SCHEMA_MAP_KEYS:
        if isinstance(node.get(key), dict):
            for v in node[key].values():
                yield from _iter_schema_nodes(v)


@pytest.mark.parametrize("name", list(tools._REGISTRY.keys()))
def test_registered_tool_schema_is_clean(name):
    spec = tools._REGISTRY[name]
    schema = _clean_schema(spec.input_model.model_json_schema())

    assert schema["type"] == "object"
    assert "properties" in schema

    for node in _iter_schema_nodes(schema):
        assert "$ref" not in node, f"{name}: leftover $ref in {node}"
        assert "$defs" not in node, f"{name}: leftover $defs in {node}"
        assert "title" not in node, f"{name}: leftover title in {node}"
        assert "default" not in node, f"{name}: leftover default in {node}"


@pytest.mark.parametrize("name", list(tools._REGISTRY.keys()))
def test_registered_tool_wire_formats_round_trip_json(name):
    spec = tools._REGISTRY[name]
    # These are what actually gets sent over the wire — a schema that isn't
    # JSON-serializable (e.g. carrying a stray set or non-str dict key) would
    # break every provider call, so pin the round trip rather than trusting
    # dict-shape alone.
    anthropic = spec.to_anthropic()
    assert json.loads(json.dumps(anthropic)) == anthropic
    openai = spec.to_openai()
    assert json.loads(json.dumps(openai)) == openai
    assert openai["type"] == "function"
    assert openai["function"]["parameters"]["type"] == "object"


# ---------------------------------------------------------------------------
# Test 2: nested models inline correctly.


class _SubModel(ToolInput):
    a: int
    b: str = Field(description="sub field b")


class NestedInput(ToolInput):
    subs: list[_SubModel] = Field(description="list of subs")
    maybe_sub: _SubModel | None = Field(default=None, description="optional sub")
    extra: dict[str, Any] = Field(default_factory=dict, description="free-form dict")
    kind: Literal["a", "b", "c"] = Field(description="enum field")


def test_nested_model_inlines_refs_and_preserves_shape():
    schema = _clean_schema(NestedInput.model_json_schema())

    for node in _iter_schema_nodes(schema):
        assert "$ref" not in node
    assert "$defs" not in schema

    props = schema["properties"]

    # list[SubModel]: items is the inlined SubModel schema, subfields reachable.
    sub_schema = props["subs"]["items"]
    assert sub_schema["type"] == "object"
    assert sub_schema["properties"]["a"]["type"] == "integer"
    assert sub_schema["properties"]["b"]["description"] == "sub field b"
    assert props["subs"]["description"] == "list of subs"

    # Optional[SubModel]: anyOf: [SubModel, null] collapses down to SubModel
    # directly (no anyOf left, description survives).
    maybe = props["maybe_sub"]
    assert "anyOf" not in maybe
    assert maybe["type"] == "object"
    assert maybe["properties"]["a"]["type"] == "integer"
    assert maybe["description"] == "optional sub"

    # dict[str, Any]
    assert props["extra"]["type"] == "object"

    # Literal[...] enum, description survives.
    assert props["kind"]["enum"] == ["a", "b", "c"]
    assert props["kind"]["description"] == "enum field"


# ---------------------------------------------------------------------------
# Test 3: two $refs to the same $defs entry must not alias.


class _SharedSub(ToolInput):
    x: int


class _TwoRefsInput(ToolInput):
    first: _SharedSub
    second: _SharedSub


def test_two_refs_to_same_def_do_not_alias():
    schema = _clean_schema(_TwoRefsInput.model_json_schema())
    first = schema["properties"]["first"]
    second = schema["properties"]["second"]
    assert first == second  # sanity: both inlined the same way

    # Mutate one inlined copy in place; the other must be untouched. If
    # _inline_refs ever stopped deep-copying (e.g. returned the same `resolved`
    # dict object for every $ref to a def), this mutation would leak across.
    first["properties"]["x"]["type"] = "MUTATED"
    assert second["properties"]["x"]["type"] == "integer"


# ---------------------------------------------------------------------------
# Test 4: regression test — fields literally named "title"/"default"/"anyOf".
#
# `properties` is a *map of field name -> schema*, not a schema node itself.
# A walker that recurses into every dict indiscriminately (rather than only
# through the known JSON-Schema keywords: items/anyOf/properties/$defs/...)
# cannot tell "this dict key is a JSON-Schema keyword to act on" apart from
# "this dict key is a user's field name that happens to collide with one".
# Concretely: `schema["properties"]["title"]` is the schema for a field named
# `title` — if a naive stripper treats every `"title"` key it finds as "the
# noise key to delete", it deletes that field's entire schema out of
# `properties`, and a field named `anyOf` gets its schema misread as an
# Optional-collapse candidate. This was a real bug fixed the day this test
# was written; keep this test so nobody "simplifies" _walk_schema back to a
# blind recursive-dict-strip.


class _WeirdNamesInput(ToolInput):
    title: str
    default: int
    anyOf: bool


def test_field_names_colliding_with_schema_keywords_survive():
    schema = _clean_schema(_WeirdNamesInput.model_json_schema())
    props = schema["properties"]

    assert set(props) == {"title", "default", "anyOf"}, (
        "a field named 'title', 'default', or 'anyOf' was dropped from "
        f"properties — got {sorted(props)}"
    )
    assert props["title"]["type"] == "string"
    assert props["default"]["type"] == "integer"
    assert props["anyOf"]["type"] == "boolean"
    assert set(schema["required"]) == {"title", "default", "anyOf"}


def test_field_names_colliding_with_schema_keywords_would_fail_a_naive_stripper():
    """Proves the test above is a real regression test, not one that would
    pass against any implementation. This reimplements the naive "recurse
    into every dict, strip any 'title'/'default' key, collapse any 'anyOf'
    key" walker an earlier version of _clean_schema used, and shows it
    corrupts exactly the field names above. If this test ever fails, the
    fixture above has stopped exercising the failure mode and the guard is
    worthless — fix the fixture rather than deleting this.
    """

    def naive_strip(node):
        if isinstance(node, dict):
            node = {k: naive_strip(v) for k, v in node.items()}
            node.pop("title", None)
            node.pop("default", None)
            if "anyOf" in node:
                branches = [b for b in node["anyOf"] if isinstance(b, dict) and b.get("type") != "null"]
                if len(branches) == 1:
                    node.pop("anyOf")
                    node.update(branches[0])
            return node
        if isinstance(node, list):
            return [naive_strip(v) for v in node]
        return node

    raw = _WeirdNamesInput.model_json_schema()
    naively_cleaned = naive_strip(raw)
    props = naively_cleaned.get("properties", {})
    # The naive walker deletes the "title" and "default" fields outright
    # (their schemas vanish because the walker also strips the *keys*
    # "title"/"default" wherever it finds them, including as properties'
    # field-name keys) and mishandles "anyOf" — demonstrating the failure
    # mode the real _walk_schema (properties-aware) avoids.
    assert set(props) != {"title", "default", "anyOf"}, (
        "expected the naive stripper to corrupt the field set, but it didn't — "
        "this test is no longer a valid regression guard, investigate"
    )


# ---------------------------------------------------------------------------
# Test 5: self-referential model raises ValueError mentioning recursion.


class _SelfRefInput(ToolInput):
    name: str
    child: "_SelfRefInput | None" = None


_SelfRefInput.model_rebuild()


def test_self_referential_model_raises_instead_of_recursing():
    schema = _SelfRefInput.model_json_schema()
    with pytest.raises(ValueError, match="(?i)recursi"):
        _clean_schema(schema)


# ---------------------------------------------------------------------------
# Test 6: a $ref with sibling keys keeps those sibling keys after inlining.


class _SiblingSub(ToolInput):
    y: int


class _RefWithSiblingInput(ToolInput):
    # A *required* nested-model field (not Optional) is emitted by pydantic as
    # {"$ref": "...", "description": "..."} — $ref with a sibling key — rather
    # than wrapped in anyOf.
    required_sub: _SiblingSub = Field(description="sibling description")


def test_ref_with_sibling_keys_keeps_siblings_after_inlining():
    raw = _RefWithSiblingInput.model_json_schema()
    # Confirm the fixture actually exercises a $ref-with-siblings node before
    # cleaning (otherwise this test would pass vacuously).
    raw_node = raw["properties"]["required_sub"]
    assert "$ref" in raw_node and "description" in raw_node

    schema = _clean_schema(raw)
    node = schema["properties"]["required_sub"]
    assert "$ref" not in node
    assert node["description"] == "sibling description"
    assert node["type"] == "object"
    assert node["properties"]["y"]["type"] == "integer"
