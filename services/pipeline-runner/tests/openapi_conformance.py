"""Semantic comparison of a FastAPI OpenAPI document with a Shipyard contract (T022, Q-22).

Canonical file: shared/openapi_conformance.py; each service holds a byte-identical copy at
tests/openapi_conformance.py (scripts/ci/check_shared_copy.py enforces it). Never edit a copy.

Public functions:
  differences(app_spec, contract_path) -> list[str]   one line per difference, [] when they conform
  schema_validator(contract_path, pointer) -> Draft202012Validator
  find_contract(name) -> Path                          contracts/<name> found from this file upwards

Normalisation rules (see docs/tasks/T022.md):
  - every $ref (local and cross-file) is inlined from disk; annotations are ignored;
  - allOf is merged (union of properties and types, union of required);
  - anyOf/oneOf branches are merged (union of properties and types; a property is required only
    when every non-null branch requires it);
  - a missing "type" is inferred from const/enum; a property whose contract schema states no type
    is not type-compared;
  - header parameter names are compared case-insensitively;
  - only JSON media types get their schema compared.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
_APP = Path("<app>")


def find_contract(name: str) -> Path:
    """Return contracts/<name>; the root is the first parent holding contracts/errors.yml."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "contracts" / "errors.yml").is_file():
            return parent / "contracts" / name
    raise FileNotFoundError("no directory above this file holds contracts/errors.yml")


# --- $ref inlining -------------------------------------------------------------------------


class _Docs:
    def __init__(self, app_spec: dict[str, Any] | None = None) -> None:
        self._docs: dict[Path, Any] = {}
        if app_spec is not None:
            self._docs[_APP] = app_spec

    def load(self, path: Path) -> Any:
        if path not in self._docs:
            with path.open(encoding="utf-8") as handle:
                self._docs[path] = yaml.safe_load(handle)
        return self._docs[path]

    def pointer(self, path: Path, fragment: str) -> Any:
        node = self.load(path)
        for raw in fragment.lstrip("/").split("/") if fragment else []:
            part = urllib.parse.unquote(raw).replace("~1", "/").replace("~0", "~")
            node = node[int(part)] if isinstance(node, list) else node[part]
        return node

    def inline(self, node: Any, path: Path, stack: tuple[str, ...] = ()) -> Any:
        if isinstance(node, list):
            return [self.inline(item, path, stack) for item in node]
        if not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        if not isinstance(ref, str):
            return {key: self.inline(value, path, stack) for key, value in node.items()}
        file_part, _, fragment = ref.partition("#")
        target_path = (path.parent / file_part).resolve() if file_part else path
        key = f"{target_path}#{fragment}"
        if key in stack:
            target: Any = {}  # recursive schema: treated as "anything"
        else:
            target = self.inline(self.pointer(target_path, fragment), target_path, (*stack, key))
        siblings = {k: self.inline(v, path, stack) for k, v in node.items() if k != "$ref"}
        return {"allOf": [target, siblings]} if siblings else target


# --- structural shape of a schema ----------------------------------------------------------


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "array" if isinstance(value, list) else "object"


@dataclass
class _Shape:
    types: set[str] = field(default_factory=set)
    required: set[str] = field(default_factory=set)
    props: dict[str, _Shape] = field(default_factory=dict)
    items: _Shape | None = None
    extra: _Shape | None = None

    def is_null_only(self) -> bool:
        return self.types == {"null"} and not self.props and self.items is None


def _merge_opt(a: _Shape | None, b: _Shape | None) -> _Shape | None:
    if a is None or b is None:
        return a or b
    return _merge(a, b)


def _merge(a: _Shape, b: _Shape) -> _Shape:
    props = dict(a.props)
    for name, shape in b.props.items():
        props[name] = _merge(props[name], shape) if name in props else shape
    return _Shape(
        a.types | b.types,
        a.required | b.required,
        props,
        _merge_opt(a.items, b.items),
        _merge_opt(a.extra, b.extra),
    )


def _any_of(branches: list[_Shape]) -> _Shape:
    result = _Shape()
    structural = [b for b in branches if not b.is_null_only()] or branches
    for branch in branches:
        result = _merge(result, branch)
    result.required = set.intersection(*(b.required for b in structural)) if structural else set()
    return result


def _shape(schema: Any) -> _Shape:
    if not isinstance(schema, dict):
        return _Shape()
    declared = schema.get("type")
    types: set[str] = set()
    if isinstance(declared, str):
        types = {declared}
    elif isinstance(declared, list):
        types = {str(t) for t in declared}
    elif "const" in schema:
        types = {_type_name(schema["const"])}
    elif isinstance(schema.get("enum"), list):
        types = {_type_name(v) for v in schema["enum"]}
    props = schema.get("properties")
    shape = _Shape(
        types,
        {str(r) for r in schema.get("required", []) if isinstance(r, str)},
        {str(k): _shape(v) for k, v in props.items()} if isinstance(props, dict) else {},
        _shape(schema["items"]) if isinstance(schema.get("items"), dict) else None,
        _shape(schema["additionalProperties"])
        if isinstance(schema.get("additionalProperties"), dict)
        else None,
    )
    for branch in schema.get("allOf", []):
        shape = _merge(shape, _shape(branch))
    for key in ("anyOf", "oneOf"):
        if isinstance(schema.get(key), list) and schema[key]:
            shape = _merge(shape, _any_of([_shape(b) for b in schema[key]]))
    return shape


def _flatten(
    shape: _Shape, path: str, required: bool, out: dict[str, tuple[bool, frozenset[str]]]
) -> None:
    out[path] = (required, frozenset(shape.types))
    for name, sub in shape.props.items():
        _flatten(sub, f"{path}.{name}" if path else name, name in shape.required, out)
    if shape.items is not None:
        _flatten(shape.items, f"{path}[]", True, out)
    if shape.extra is not None:
        _flatten(shape.extra, f"{path}.*", True, out)


def _flat(schema: Any) -> dict[str, tuple[bool, frozenset[str]]]:
    out: dict[str, tuple[bool, frozenset[str]]] = {}
    _flatten(_shape(schema), "", True, out)
    return out


def _schema_examples(schema: Any) -> list[Any]:
    if not isinstance(schema, dict):
        return []
    found: list[Any] = list(schema["examples"]) if isinstance(schema.get("examples"), list) else []
    for branch in schema.get("allOf", []):
        found.extend(_schema_examples(branch))
    return found


# --- comparison ----------------------------------------------------------------------------


def _is_json(media_type: str) -> bool:
    base = media_type.split(";")[0].strip().lower()
    return base == "application/json" or base.endswith("+json")


def _fmt(values: Any) -> str:
    return "[" + ", ".join(sorted(str(v) for v in values)) + "]"


def _operations(paths: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    ops: dict[tuple[str, str], dict[str, Any]] = {}
    for path, item in paths.items():
        shared = item.get("parameters", []) if isinstance(item, dict) else []
        for method in _METHODS:
            op = item.get(method) if isinstance(item, dict) else None
            if isinstance(op, dict):
                merged = dict(op)
                own = {_param_key(p) for p in op.get("parameters", [])}
                merged["parameters"] = [p for p in shared if _param_key(p) not in own] + list(
                    op.get("parameters", [])
                )
                ops[(method.upper(), path)] = merged
    return ops


def _param_key(param: dict[str, Any]) -> tuple[str, str]:
    where = str(param.get("in", ""))
    name = str(param.get("name", ""))
    return (where, name.lower() if where == "header" else name)


def _compare_schema(label: str, contract_schema: Any, app_schema: Any, out: list[str]) -> None:
    contract_flat = _flat(contract_schema)
    app_flat = _flat(app_schema)
    for path in sorted(contract_flat.keys() | app_flat.keys()):
        shown = path or "(whole body)"
        if path not in app_flat:
            out.append(f"{label}: property {shown} is in the contract but not in the app")
        elif path not in contract_flat:
            out.append(f"{label}: property {shown} is in the app but not in the contract")
        else:
            c_req, c_types = contract_flat[path]
            a_req, a_types = app_flat[path]
            if c_req != a_req:
                out.append(
                    f"{label}: property {shown} required differs: contract {c_req}, app {a_req}"
                )
            if c_types and c_types != a_types:
                out.append(
                    f"{label}: property {shown} types differ: contract {_fmt(c_types)}, "
                    f"app {_fmt(a_types)}"
                )


def _compare_examples(label: str, contract_media: Any, app_schema: Any, out: list[str]) -> None:
    examples: list[tuple[str, Any]] = []
    if isinstance(contract_media, dict):
        if "example" in contract_media:
            examples.append(("media-type example", contract_media["example"]))
        named = contract_media.get("examples")
        if isinstance(named, dict):
            for name, ex in named.items():
                if isinstance(ex, dict) and "value" in ex:
                    examples.append((f"media-type example '{name}'", ex["value"]))
        examples.extend(
            (f"schema example #{i}", v)
            for i, v in enumerate(_schema_examples(contract_media.get("schema")))
        )
    if not examples:
        return
    validator = Draft202012Validator(app_schema if app_schema is not None else {})
    for name, value in examples:
        for error in list(validator.iter_errors(value))[:5]:
            where = ".".join(str(p) for p in error.absolute_path) or "(whole body)"
            out.append(
                f"{label}: contract {name} rejected by the app schema at {where}: {error.message}"
            )


def _compare_content(label: str, contract_content: Any, app_content: Any, out: list[str]) -> None:
    c_content = contract_content if isinstance(contract_content, dict) else {}
    a_content = app_content if isinstance(app_content, dict) else {}
    if set(c_content) != set(a_content):
        out.append(
            f"{label}: media types differ: contract {_fmt(c_content)}, app {_fmt(a_content)}"
        )
    for media in sorted(set(c_content) & set(a_content)):
        if not _is_json(media):
            continue
        c_media, a_media = c_content[media] or {}, a_content[media] or {}
        if "schema" not in c_media:
            continue
        sub = f"{label} {media}"
        if "schema" not in a_media:
            out.append(f"{sub}: the app declares no schema")
            continue
        _compare_schema(sub, c_media["schema"], a_media["schema"], out)
        _compare_examples(sub, c_media, a_media["schema"], out)


def differences(app_spec: dict[str, Any], contract_path: str | Path) -> list[str]:
    """Return one readable line per difference between the app's OpenAPI and the contract."""
    path = Path(contract_path).resolve()
    docs = _Docs(app_spec)
    contract_ops = _operations(docs.inline(docs.load(path).get("paths", {}), path))
    app_ops = _operations(docs.inline(app_spec.get("paths", {}), _APP))
    out: list[str] = []
    for method, route in sorted(contract_ops.keys() | app_ops.keys(), key=lambda k: (k[1], k[0])):
        label = f"{method} {route}"
        if (method, route) not in app_ops:
            out.append(f"{label}: in the contract but not in the app")
            continue
        if (method, route) not in contract_ops:
            out.append(f"{label}: in the app but not in the contract")
            continue
        c_op, a_op = contract_ops[(method, route)], app_ops[(method, route)]
        _compare_parameters(label, c_op, a_op, out)
        _compare_content(
            f"{label} request",
            (c_op.get("requestBody") or {}).get("content"),
            (a_op.get("requestBody") or {}).get("content"),
            out,
        )
        c_resp, a_resp = c_op.get("responses") or {}, a_op.get("responses") or {}
        c_codes, a_codes = {str(k) for k in c_resp}, {str(k) for k in a_resp}
        for code in sorted(c_codes - a_codes):
            out.append(f"{label}: status {code} is in the contract but not in the app")
        for code in sorted(a_codes - c_codes):
            out.append(f"{label}: status {code} is in the app but not in the contract")
        by_code_c = {str(k): v for k, v in c_resp.items()}
        by_code_a = {str(k): v for k, v in a_resp.items()}
        for code in sorted(c_codes & a_codes):
            _compare_content(
                f"{label} response {code}",
                (by_code_c[code] or {}).get("content"),
                (by_code_a[code] or {}).get("content"),
                out,
            )
    return out


def _compare_parameters(
    label: str, c_op: dict[str, Any], a_op: dict[str, Any], out: list[str]
) -> None:
    c_params = {_param_key(p): bool(p.get("required", False)) for p in c_op["parameters"]}
    a_params = {_param_key(p): bool(p.get("required", False)) for p in a_op["parameters"]}
    for where, name in sorted(c_params.keys() | a_params.keys()):
        key = (where, name)
        shown = f"{where} parameter {name}"
        if key not in a_params:
            out.append(f"{label}: {shown} is in the contract but not in the app")
        elif key not in c_params:
            out.append(f"{label}: {shown} is in the app but not in the contract")
        elif c_params[key] != a_params[key]:
            out.append(
                f"{label}: {shown} required differs: contract {c_params[key]}, app {a_params[key]}"
            )


def schema_validator(contract_path: str | Path, pointer: str) -> Draft202012Validator:
    """Validator (JSON Schema 2020-12, formats checked) for a contract schema.

    `pointer` is "#/components/schemas/Run" (this file) or "events.yml#/$defs/BuildFinishedData"
    (another file, relative to the contract). Every $ref is inlined from disk; anyOf/oneOf state
    tables are enforced as written.
    """
    path = Path(contract_path).resolve()
    file_part, _, fragment = pointer.partition("#")
    target = (path.parent / file_part).resolve() if file_part else path
    docs = _Docs()
    schema = docs.inline(docs.pointer(target, fragment), target, (f"{target}#{fragment}",))
    if isinstance(schema, dict):
        for key in ("$id", "$schema", "$defs"):
            schema.pop(key, None)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
