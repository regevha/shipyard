#!/usr/bin/env python3
"""Check the contract files under contracts/ and the task specs under docs/tasks/.

Implements docs/PLAN.md "Contract file format". Each failure is one line:
    <file>: <JSON pointer or line N>: <message>
Exit 0: no failures. Exit 1: at least one failure. Exit 2: the environment is
wrong (a package or a format checker is missing); nothing is skipped.

Usage: check_contracts.py [--root DIR]
       check_contracts.py --self-test
Needs: python3 -m pip install -r scripts/ci/requirements-contracts.txt
"""
import argparse
import datetime
import math
import re
import socket
import sys
from pathlib import Path
from urllib.parse import quote, unquote

INSTALL_HINT = "python3 -m pip install -r scripts/ci/requirements-contracts.txt"

try:
    import yaml
    from jsonschema import Draft202012Validator
    from openapi_spec_validator import OpenAPIV31SpecValidator
    from jsonschema_path import SchemaPath
    from jsonschema_path.handlers import UrllibHandler
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012
except ImportError as exc:  # exit 2: never skip a check
    print(f"missing package ({exc}); run: {INSTALL_HINT}", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contracts"

BASE = "https://shipyard.invalid/contracts/"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_FILES = ("events.yml", "errors.yml")
API_FILES = (
    "api-pipeline-runner.yml",
    "api-artifact-store.yml",
    "api-release-service.yml",
    "api-dashboard.yml",
)
ALLOWED = frozenset(SCHEMA_FILES + API_FILES)
METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
Q_RE = re.compile(r"^Q-\d{2}$")
Q_HEADING_RE = re.compile(r"^###[ \t]+(Q-\d{2})(?!\d)", re.MULTILINE)
REQUIRED_FORMATS = ("date-time", "uuid", "uri")

# Keys whose value is a mapping of user-chosen names to objects (not keywords).
NAME_MAPS = frozenset({
    "properties", "patternProperties", "$defs", "definitions", "dependentSchemas", "schemas",
    "responses", "parameters", "requestBodies", "headers", "content", "paths", "callbacks",
    "links", "securitySchemes", "pathItems", "webhooks", "encoding", "variables", "mapping",
})
# Keywords whose value is data, not contract structure.
DATA_KEYS = frozenset({"const", "enum", "default", "example"})


def esc(part) -> str:
    return str(part).replace("~", "~0").replace("/", "~1")


def pointer(parts) -> str:
    return "".join("/" + esc(p) for p in parts)


def one_line(msg) -> str:
    text = " ".join(str(msg).split())
    return text if len(text) <= 500 else text[:497] + "..."


def refuse_fetch(uri):
    raise ValueError(f"refusing to fetch {uri} (the checker never uses the network)")


class Report:
    def __init__(self):
        self.lines: list[str] = []

    def fail(self, file: str, where, msg) -> None:
        if not isinstance(where, str):
            where = pointer(where) or "(root)"
        self.lines.append(f"{file}: {where or '(root)'}: {one_line(msg)}")


# --- loading ---------------------------------------------------------------

class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""

    def construct_mapping(self, node, deep=False):
        if isinstance(node, yaml.MappingNode):
            for key_node, _ in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge":
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping", node.start_mark,
                        "YAML merge key '<<' is not allowed; write the keys out", key_node.start_mark)
            self.flatten_mapping(node)
            seen = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=True)
                try:
                    token = (type(key), key)
                    hash(token)
                except TypeError:
                    continue  # the parent raises its own error for unhashable keys
                if token in seen:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping", node.start_mark,
                        f"duplicate mapping key {key!r}", key_node.start_mark)
                seen.add(token)
        return super().construct_mapping(node, deep=deep)


def load_yaml(path: Path):
    """Return (data, None) or (None, (where, message))."""
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, ("(file)", f"not valid UTF-8: {exc}")
    try:
        return yaml.load(text, Loader=UniqueKeyLoader), None  # noqa: S506 (safe subclass)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        line = f"line {mark.line + 1}" if mark else "(file)"
        problem = getattr(exc, "problem", None) or str(exc)
        return None, (line, f"YAML error: {problem}")


def json_violations(data) -> list[tuple[str, str]]:
    """Every node must be a JSON type and every key a string."""
    found: list[tuple[str, str]] = []

    def walk(node, parts, stack):
        where = pointer(parts) or "(root)"
        if isinstance(node, bool) or node is None or isinstance(node, (str, int)):
            return
        if isinstance(node, float):
            if not math.isfinite(node):
                found.append((where, "non-finite number is not valid JSON"))
            return
        if isinstance(node, datetime.datetime):
            found.append((where, "unquoted timestamp loads as datetime; quote it"))
            return
        if isinstance(node, datetime.date):
            found.append((where, "unquoted date loads as date; quote it"))
            return
        if isinstance(node, (dict, list)):
            if id(node) in stack:
                found.append((where, "recursive YAML alias is not a JSON tree"))
                return
            stack = stack | {id(node)}
            if isinstance(node, dict):
                for key, value in node.items():
                    if not isinstance(key, str):
                        found.append((pointer(parts + (key,)),
                                      f"mapping key {key!r} is not a string; quote it"))
                    walk(value, parts + (key,), stack)
            else:
                for i, value in enumerate(node):
                    walk(value, parts + (i,), stack)
            return
        found.append((where, f"{type(node).__name__} is not a JSON type"))

    walk(data, (), frozenset())
    return found


# --- structure walking -----------------------------------------------------

def collect_data_refs(node, parts, out):
    """Record every mapping with a $ref key inside a data value (default, const, enum, examples)."""
    if isinstance(node, dict):
        if "$ref" in node:
            out.append(parts)
        for key, value in node.items():
            collect_data_refs(value, parts + (key,), out)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            collect_data_refs(item, parts + (i,), out)


def iter_objects(node, parts=(), data_refs=None):
    """Yield (parts, dict) for every keyword-context object, skipping example and data values.

    If data_refs is a list, the pointers of $ref mappings found inside the skipped data values are appended.
    """
    if isinstance(node, list):
        for i, item in enumerate(node):
            yield from iter_objects(item, parts + (i,), data_refs)
        return
    if not isinstance(node, dict):
        return
    yield parts, node
    for key, value in node.items():
        if not isinstance(key, str):
            continue
        if key in DATA_KEYS:
            if data_refs is not None:
                collect_data_refs(value, parts + (key,), data_refs)
            continue
        if key == "examples":
            if isinstance(value, dict):  # OpenAPI Example Objects; their `value` is example data
                for name, example in value.items():
                    if isinstance(example, dict):
                        rest = {k: v for k, v in example.items() if k != "value"}
                        if data_refs is not None and "value" in example:
                            collect_data_refs(example["value"], parts + (key, name, "value"), data_refs)
                        yield from iter_objects(rest, parts + (key, name), data_refs)
            elif data_refs is not None:
                collect_data_refs(value, parts + (key,), data_refs)
            continue
        if key in NAME_MAPS and isinstance(value, dict):
            for name, child in value.items():
                yield from iter_objects(child, parts + (key, name), data_refs)
        else:
            yield from iter_objects(value, parts + (key,), data_refs)


def lookup(doc, frag: str):
    """Resolve a JSON pointer; return (found, node)."""
    if frag == "":
        return True, doc
    if not frag.startswith("/"):
        return False, None
    node = doc
    for token in frag[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            return False, None
    return True, node


REF_RE = re.compile(r"(?P<file>[A-Za-z0-9_.-]+)?#(?P<frag>(?:/.*)?)", re.DOTALL)


def split_ref(name: str, ref: str):
    """Return ((target_file, fragment), None) or (None, error message).

    Only '#<pointer>' and '<contract file>#<pointer>' are allowed; absolute URIs and every other form are errors.
    """
    match = REF_RE.fullmatch(ref)
    if not match or (match["file"] or name) not in ALLOWED:
        return None, (f"$ref {ref!r} must be '#<pointer>' or '<contract file>#<pointer>' naming one of the "
                      "six contract files (absolute URIs and anything outside contracts/ are not allowed)")
    return (match["file"] or name, unquote(match["frag"])), None


def media_objects(doc):
    """Yield (parts, media object) for every media type object the format names."""
    def from_content(parts, holder):
        content = holder.get("content") if isinstance(holder, dict) else None
        if isinstance(content, dict):
            for media, obj in content.items():
                if isinstance(obj, dict):
                    yield parts + ("content", media), obj

    paths = doc.get("paths")
    if isinstance(paths, dict):
        for path, item in paths.items():
            if not isinstance(item, dict):
                continue
            for method in METHODS:
                op = item.get(method)
                if not isinstance(op, dict):
                    continue
                base = ("paths", path, method)
                body = op.get("requestBody")
                if isinstance(body, dict) and "$ref" not in body:
                    yield from from_content(base + ("requestBody",), body)
                responses = op.get("responses")
                if isinstance(responses, dict):
                    for status, resp in responses.items():
                        if isinstance(resp, dict) and "$ref" not in resp:
                            yield from from_content(base + ("responses", status), resp)
    comps = doc.get("components")
    if isinstance(comps, dict):
        for section in ("requestBodies", "responses"):
            group = comps.get(section)
            if isinstance(group, dict):
                for name, obj in group.items():
                    if isinstance(obj, dict) and "$ref" not in obj:
                        yield from from_content(("components", section, name), obj)


# --- the checker -----------------------------------------------------------

class Checker:
    def __init__(self, root: Path):
        self.root = root
        self.rep = Report()
        self.docs: dict[str, dict] = {}  # name -> loaded document (files that passed loading)
        self.known_q: set[str] = set()
        self.schema_broken: set[str] = set()  # files that fail check_schema; their examples are not run

    def rel(self, name: str) -> str:
        return f"contracts/{name}"

    def fail(self, name: str, where, msg) -> None:
        self.rep.fail(self.rel(name), where, msg)

    def run(self) -> list[str]:
        self.load_open_questions()
        self.load_contracts()
        for name, doc in self.docs.items():
            self.check_refs(name, doc)
            self.check_x_assumed(name, doc)
            self.check_composition(name, doc)
        for name in SCHEMA_FILES:
            if name in self.docs:
                self.check_schema_file(name, self.docs[name])
        if "errors.yml" in self.docs:
            self.check_errors_file(self.docs["errors.yml"])
        if "events.yml" in self.docs:
            self.check_events_file(self.docs["events.yml"])
        for name in API_FILES:
            if name in self.docs:
                self.check_api_file(name, self.docs[name])
        self.check_examples()
        self.check_task_specs()
        return self.rep.lines

    # -- loading
    def load_open_questions(self):
        path = self.root / "docs" / "OPEN_QUESTIONS.md"
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            self.known_q = set(Q_HEADING_RE.findall(text))

    def load_contracts(self):
        folder = self.root / "contracts"
        if not folder.is_dir():
            return
        for entry in sorted(folder.iterdir()):
            if entry.name not in ALLOWED or not entry.is_file():
                self.fail(entry.name + ("/" if entry.is_dir() else ""), "(file)",
                          "not an allowed contract file (allowed: " + ", ".join(sorted(ALLOWED)) + ")")
                continue
            data, err = load_yaml(entry)
            if err:
                self.fail(entry.name, *err)
                continue
            if not isinstance(data, dict):
                self.fail(entry.name, "(root)", "root must be a mapping")
                continue
            violations = json_violations(data)
            for where, msg in violations:
                self.fail(entry.name, where, msg)
            if not violations:
                self.docs[entry.name] = data

    # -- references, x-assumed, composition (all six files)
    def check_refs(self, name, doc):
        is_schema_file = name in SCHEMA_FILES
        data_refs: list = []
        objects = list(iter_objects(doc, (), data_refs))
        for parts in data_refs:
            self.fail(name, parts + ("$ref",),
                      "a $ref inside a default, const, enum or examples value is not allowed")
        for parts, obj in objects:
            if "$ref" not in obj:
                continue
            ref = obj["$ref"]
            where = parts + ("$ref",)
            if not isinstance(ref, str):
                self.fail(name, where, "$ref must be a string")
                continue
            if is_schema_file and not ref.startswith("#"):
                self.fail(name, where, f"$ref {ref!r} must start with '#' (no cross-file refs here)")
                continue
            self.resolve(name, ref, where)  # reports unresolvable refs

    def resolve(self, name, ref, where):
        """Return (target file, target node) of a $ref; report a failure (when where is set) if it cannot be resolved."""
        target, err = split_ref(name, ref)
        if err:
            if where is not None:
                self.fail(name, where, err)
            return None
        tfile, frag = target
        if tfile not in self.docs:
            if where is not None:
                self.fail(name, where, f"$ref {ref!r}: {tfile} is missing or failed to load")
            return None
        ok, node = lookup(self.docs[tfile], frag)
        if not ok:
            if where is not None:
                self.fail(name, where, f"$ref {ref!r} does not resolve: no {frag or '(root)'} in {tfile}")
            return None
        return tfile, node

    def check_x_assumed(self, name, doc):
        for parts, obj in iter_objects(doc):
            if "x-assumed" not in obj:
                continue
            value = obj["x-assumed"]
            where = parts + ("x-assumed",)
            if (not isinstance(value, list) or not value
                    or not all(isinstance(v, str) and Q_RE.match(v) for v in value)):
                self.fail(name, where, "x-assumed must be a non-empty list of strings like 'Q-07'")
                continue
            for qid in value:
                if qid not in self.known_q:
                    self.fail(name, where, f"x-assumed names {qid}, which has no '### {qid}' "
                                           "heading in docs/OPEN_QUESTIONS.md")

    def check_composition(self, name, doc):
        composers = [(parts, obj) for parts, obj in iter_objects(doc) if isinstance(obj.get("allOf"), list)]
        member_ids = set()  # id() of every dict used as an allOf member (inline or as a $ref target)
        for parts, obj in composers:
            for member in obj["allOf"]:
                if isinstance(member, dict) and isinstance(member.get("$ref"), str):
                    found = self.resolve(name, member["$ref"], None)  # unresolvable refs are reported elsewhere
                    member = found[1] if found else None
                if isinstance(member, dict):
                    member_ids.add(id(member))
        for parts, obj in composers:
            if obj.get("additionalProperties") is False:
                self.fail(name, parts + ("additionalProperties",),
                          "a schema built with allOf must not set additionalProperties: false; "
                          "use unevaluatedProperties: false")
            if id(obj) not in member_ids and obj.get("unevaluatedProperties") is not False:
                self.fail(name, parts, "a schema built with allOf must set unevaluatedProperties: false "
                                       "(only the outermost composer; one that is itself an allOf member stays open)")
            for i, member in enumerate(obj["allOf"]):
                if isinstance(member, dict) and isinstance(member.get("$ref"), str):
                    found = self.resolve(name, member["$ref"], None)
                    member = found[1] if found else None
                if isinstance(member, dict):
                    for key in ("additionalProperties", "unevaluatedProperties"):
                        if member.get(key) is False:
                            self.fail(name, parts + ("allOf", i),
                                      f"an allOf member must stay open: remove {key}: false "
                                      "(the composing schema closes it)")

    # -- events.yml and errors.yml
    def check_schema_file(self, name, doc):
        if doc.get("$schema") != DIALECT:
            self.fail(name, "/$schema", f"must be {DIALECT}")
        if doc.get("$id") != BASE + name:
            self.fail(name, "/$id", f"must be {BASE + name}")
        defs = doc.get("$defs")
        if not isinstance(defs, dict) or not defs:
            self.fail(name, "/$defs", "must be a non-empty mapping")
            defs = {}
        try:
            Draft202012Validator.check_schema(doc)
        except Exception as exc:  # SchemaError and friends
            self.schema_broken.add(name)
            self.fail(name, pointer(getattr(exc, "absolute_path", ())) or "(root)",
                      f"not a valid 2020-12 schema: {getattr(exc, 'message', exc)}")
        for key, entry in defs.items():
            examples = entry.get("examples") if isinstance(entry, dict) else None
            if not isinstance(examples, list) or not examples:
                self.fail(name, ("$defs", key), "must have examples: a non-empty list")

    def check_errors_file(self, doc):
        name = "errors.yml"
        defs = doc.get("$defs") if isinstance(doc.get("$defs"), dict) else {}
        for need in ("ErrorEnvelope", "ErrorCode"):
            if need not in defs:
                self.fail(name, "/$defs", f"must define {need}")
        enum = defs.get("ErrorCode", {}).get("enum") if isinstance(defs.get("ErrorCode"), dict) else None
        if "ErrorCode" in defs and not (isinstance(enum, list) and enum):
            self.fail(name, "/$defs/ErrorCode", "must have enum: a non-empty list of error codes")
            enum = None
        codes = doc.get("x-status-codes")
        if not isinstance(codes, list) or not codes:
            self.fail(name, "/x-status-codes", "must be a non-empty list of {status, code, meaning}")
            return
        seen = set()
        for i, item in enumerate(codes):
            where = ("x-status-codes", i)
            if not isinstance(item, dict):
                self.fail(name, where, "must be a mapping {status, code, meaning}")
                continue
            status, code, meaning = item.get("status"), item.get("code"), item.get("meaning")
            if isinstance(status, bool) or not isinstance(status, int) or not 400 <= status <= 599:
                self.fail(name, where + ("status",), "status must be an integer from 400 to 599")
            if not isinstance(code, str):
                self.fail(name, where + ("code",), "code must be a string")
            elif enum is not None and code not in enum:
                self.fail(name, where + ("code",), f"code {code!r} is not in $defs/ErrorCode/enum")
            if not isinstance(meaning, str):
                self.fail(name, where + ("meaning",), "meaning must be a string")
            if (isinstance(status, int) and not isinstance(status, bool) and isinstance(code, str)):
                if (status, code) in seen:
                    self.fail(name, where, f"duplicate (status, code) pair ({status}, {code})")
                seen.add((status, code))

    def event_types(self, doc):
        """Names of the $defs entries targeted by the root oneOf (list, or None if unusable)."""
        one_of = doc.get("oneOf")
        if not isinstance(one_of, list) or not one_of:
            return None
        names = []
        for item in one_of:
            ref = item.get("$ref") if isinstance(item, dict) else None
            if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
                return None
            names.append(unquote(ref[len("#/$defs/"):]).replace("~1", "/").replace("~0", "~"))
        return names

    def check_events_file(self, doc):
        name = "events.yml"
        names = self.event_types(doc)
        if names is None:
            self.fail(name, "/oneOf", "root must have oneOf: a non-empty list of {$ref: '#/$defs/<Event>'}")
            return
        defs = doc.get("$defs") if isinstance(doc.get("$defs"), dict) else {}
        for i, target in enumerate(names):
            if target not in defs:
                self.fail(name, ("oneOf", i, "$ref"), f"no $defs entry {target!r}")

    # -- api-*.yml
    def check_api_file(self, name, doc):
        service = name[len("api-"):-len(".yml")]
        if doc.get("openapi") != "3.1.0":
            self.fail(name, "/openapi", "must be the string 3.1.0")
        info = doc.get("info") if isinstance(doc.get("info"), dict) else {}
        if info.get("title") != service:
            self.fail(name, "/info/title", f"must be {service!r}")
        if not isinstance(info.get("version"), str):
            self.fail(name, "/info/version", "must be a string (quote it)")
        if "jsonSchemaDialect" in doc:
            self.fail(name, "/jsonSchemaDialect", "not allowed; the OpenAPI 3.1 default dialect applies")
        for parts, obj in iter_objects(doc):
            if "example" in obj:
                self.fail(name, parts + ("example",),
                          "the singular 'example' keyword is not allowed; use 'examples'")
        schemas = doc.get("components", {}).get("schemas") if isinstance(doc.get("components"), dict) else None
        if isinstance(schemas, dict):
            for key, schema in schemas.items():
                examples = schema.get("examples") if isinstance(schema, dict) else None
                if not isinstance(examples, list) or not examples:
                    self.fail(name, ("components", "schemas", key), "must have examples: a non-empty list")
        for parts, media in media_objects(doc):
            if "schema" not in media:
                continue
            examples = media.get("examples")
            if not isinstance(examples, dict) or not examples:
                self.fail(name, parts, "media type with a schema must have examples: a non-empty mapping")
                continue
            for key, ex in examples.items():
                if not isinstance(ex, dict) or "value" not in ex:
                    self.fail(name, parts + ("examples", key), "Example Object must have a value")
                elif "externalValue" in ex:
                    self.fail(name, parts + ("examples", key, "externalValue"), "externalValue is not allowed")
        self.check_responses(name, doc)
        self.check_openapi_validator(name, doc)

    def status_codes(self):
        codes = self.docs.get("errors.yml", {}).get("x-status-codes")
        if not isinstance(codes, list):
            return None
        return {c["status"] for c in codes if isinstance(c, dict)
                and isinstance(c.get("status"), int) and not isinstance(c.get("status"), bool)}

    def check_responses(self, name, doc):
        known = self.status_codes()
        paths = doc.get("paths") if isinstance(doc.get("paths"), dict) else {}
        for path, item in paths.items():
            for method in METHODS:
                op = item.get(method) if isinstance(item, dict) else None
                responses = op.get("responses") if isinstance(op, dict) else None
                if not isinstance(responses, dict):
                    continue
                for status, resp in responses.items():
                    where = ("paths", path, method, "responses", status)
                    if status == "default":
                        self.fail(name, where, "default responses are not allowed; list the statuses")
                        continue
                    numeric = status.isdigit() and len(status) == 3
                    if not (re.fullmatch(r"[45]XX", status) or (numeric and 400 <= int(status) <= 599)):
                        continue
                    seen_refs = set()
                    here = name
                    while isinstance(resp, dict) and isinstance(resp.get("$ref"), str):  # follow chained refs
                        if (here, resp["$ref"]) in seen_refs:
                            self.fail(name, where, f"response $ref loop at {resp['$ref']!r}")
                            resp = None
                            break
                        seen_refs.add((here, resp["$ref"]))
                        found = self.resolve(here, resp["$ref"], None)  # an unresolvable ref is reported once, by check_refs
                        if found is None:
                            resp = None
                            break
                        here, resp = found
                    if resp is None:
                        continue
                    content = resp.get("content") if isinstance(resp, dict) else None
                    media = content.get("application/json") if isinstance(content, dict) else None
                    expect = {"$ref": "errors.yml#/$defs/ErrorEnvelope"}
                    if (not isinstance(content, dict) or list(content) != ["application/json"]
                            or not isinstance(media, dict) or media.get("schema") != expect):
                        self.fail(name, where, "error response content must have exactly one media type, "
                                               "application/json, with schema: "
                                               "{$ref: 'errors.yml#/$defs/ErrorEnvelope'} and nothing else")
                    if numeric and known is not None and int(status) not in known:
                        self.fail(name, where, f"status {status} is not in errors.yml#/x-status-codes")

    def check_openapi_validator(self, name, doc):
        if doc.get("openapi") != "3.1.0":
            return
        file_url = (self.root / "contracts" / name).resolve().as_uri()
        handlers = {"<all_urls>": refuse_fetch, "http": refuse_fetch, "https": refuse_fetch,
                    "file": UrllibHandler("file")}  # only sibling files on disk are ever read
        try:
            schema_path = SchemaPath.from_dict(doc, base_uri=file_url, handlers=handlers)
            OpenAPIV31SpecValidator(schema_path).validate()
        except Exception as exc:
            self.fail(name, "(root)", f"openapi-spec-validator: {type(exc).__name__}: {exc}")

    # -- examples
    def check_examples(self):
        if not self.docs:
            return
        registry = Registry().with_resources(
            (BASE + n, Resource.from_contents(d, default_specification=DRAFT202012))
            for n, d in self.docs.items())
        for name, doc in self.docs.items():
            if name in self.schema_broken:
                continue
            for schema_parts, examples in self.example_pairs(name, doc):
                for ex_parts, value in examples:
                    self.validate_example(registry, name, schema_parts, ex_parts, value)

    def example_pairs(self, name, doc):
        """Yield (schema pointer parts, [(example pointer parts, value)])."""
        def listed(parts, node):
            items = node.get("examples") if isinstance(node, dict) else None
            if isinstance(items, list):
                return [(parts + ("examples", i), v) for i, v in enumerate(items)]
            return []

        if name in SCHEMA_FILES:
            defs = doc.get("$defs") if isinstance(doc.get("$defs"), dict) else {}
            for key, entry in defs.items():
                yield ("$defs", key), listed(("$defs", key), entry)
            if name == "events.yml":
                types = self.event_types(doc)
                collected = []
                for t in types or []:
                    if t in defs:
                        collected += listed(("$defs", t), defs[t])
                if collected:
                    yield (), collected
            return
        comps = doc.get("components") if isinstance(doc.get("components"), dict) else {}
        schemas = comps.get("schemas") if isinstance(comps.get("schemas"), dict) else {}
        for key, schema in schemas.items():
            yield ("components", "schemas", key), listed(("components", "schemas", key), schema)
        for parts, media in media_objects(doc):
            examples = media.get("examples")
            if "schema" in media and isinstance(examples, dict):
                yield parts + ("schema",), [
                    (parts + ("examples", k, "value"), ex["value"])
                    for k, ex in examples.items() if isinstance(ex, dict) and "value" in ex]

    def validate_example(self, registry, name, schema_parts, ex_parts, value):
        uri = BASE + name + "#" + quote(pointer(schema_parts), safe="/~$:@!&'()*+,;=")
        validator = Draft202012Validator({"$ref": uri}, registry=registry,
                                         format_checker=Draft202012Validator.FORMAT_CHECKER)
        try:
            errors = sorted(validator.iter_errors(value), key=lambda e: list(map(str, e.absolute_path)))
        except Exception as exc:  # unresolvable refs, bad schemas
            self.fail(name, ex_parts, f"cannot validate example: {type(exc).__name__}: {exc}")
            return
        for err in errors:
            at = pointer(err.absolute_path)
            self.fail(name, pointer(ex_parts) + at,
                      f"example does not validate against {pointer(schema_parts) or '(root)'}: {err.message}")

    # -- task specs
    def check_task_specs(self):
        folder = self.root / "docs" / "tasks"
        if not folder.is_dir():
            return
        for path in sorted(folder.glob("*.yml")):
            rel = f"docs/tasks/{path.name}"
            data, err = load_yaml(path)
            if err:
                self.rep.fail(rel, *err)
            elif not isinstance(data, dict):
                self.rep.fail(rel, "(root)", "root must be a mapping")
            elif data.get("id") != path.stem:
                self.rep.fail(rel, "/id", f"id {data.get('id')!r} must equal the file name {path.stem!r}")


def check_environment() -> None:
    missing = [f for f in REQUIRED_FORMATS if f not in Draft202012Validator.FORMAT_CHECKER.checkers]
    if missing:
        print(f"format checker(s) missing: {', '.join(missing)}; run: {INSTALL_HINT}", file=sys.stderr)
        sys.exit(2)


def run_checks(root: Path) -> list[str]:
    return Checker(root).run()


# --- self-test -------------------------------------------------------------

# One failing tree per MUST rule; each needs a directory with this name.
REQUIRED_CASES = (
    "int-key", "timestamp", "date", "on-bool", "bad-example", "bad-format", "broken-yaml", "duplicate-key",
    "merge-key", "missing-examples", "bad-cross-file-ref", "ref-outside-contracts", "ref-network",
    "ref-absolute-contract-uri", "ref-in-default-api", "ref-in-default-errors", "events-cross-file-ref",
    "allof-additional-properties", "allof-missing-unevaluated", "allof-member-closed", "allof-nested-closed",
    "unknown-q", "x-assumed-format", "task-id-mismatch", "task-unparseable", "task-duplicate-key",
    "task-root-not-mapping", "extra-file", "wrong-dialect", "wrong-id", "defs-empty", "invalid-schema",
    "missing-oneof", "oneof-missing-def", "missing-error-envelope", "error-code-no-enum",
    "status-codes-missing", "status-codes-item-not-mapping", "status-code-out-of-range",
    "status-code-code-not-string", "status-code-meaning-not-string", "status-code-unknown-code",
    "status-code-duplicate", "status-code-unhashable-status", "status-code-unhashable-code",
    "api-openapi-version", "api-json-schema-dialect", "api-default-response", "api-example-singular",
    "api-error-schema", "api-error-extra-media", "api-error-ref-loop", "api-status-not-in-errors",
    "api-media-without-examples", "api-example-without-value", "api-title-mismatch",
    "api-version-not-string", "api-invalid-openapi", "api-schema-without-examples", "api-external-value",
    "non-finite-number", "binary-value", "recursive-alias", "root-not-mapping", "ref-not-string", "not-utf8", "ref-to-missing-file",
)


class NetworkBlock:
    """Make any socket use fail and record it, so a fetch attempt cannot pass unnoticed."""

    def __init__(self):
        self.attempts: list[str] = []

    def __enter__(self):
        self.saved = (socket.socket, socket.create_connection, socket.getaddrinfo)

        def blocked(*args, **kwargs):
            self.attempts.append("network access attempted")
            raise OSError("network access is blocked by the self-test")

        socket.socket, socket.create_connection, socket.getaddrinfo = blocked, blocked, blocked
        return self

    def __exit__(self, *exc):
        socket.socket, socket.create_connection, socket.getaddrinfo = self.saved


def check_expectations(case: str, expect: str, got: list[str]) -> list[str]:
    """expect.txt lines: a substring that must occur in a failure line; 'once: <text>' needs exactly one line."""
    problems = []
    for want in (line.strip() for line in expect.splitlines() if line.strip()):
        if want.startswith("once:"):
            text = want[len("once:"):].strip()
            hits = sum(text in line for line in got)
            if hits != 1:
                problems.append(f"fixture '{case}': expected exactly one failure line with {text!r}, got {hits}:\n    "
                                + "\n    ".join(got))
        elif not any(want in line for line in got):
            problems.append(f"fixture '{case}' failed for the wrong reason; expected {want!r}, got:\n    "
                            + "\n    ".join(got))
    return problems


def self_test() -> int:
    problems = []
    if not FIXTURES.is_dir():
        print(f"self-test: fixtures folder missing: {FIXTURES}")
        return 1
    line_re = re.compile(r"^[^:\n]+: [^\n]+?: [^\n]+$")
    with NetworkBlock() as net:
        valid = FIXTURES / "valid"
        if not (valid / "contracts").is_dir():
            problems.append("fixture 'valid' is missing")
        else:
            got = run_checks(valid)
            if got:
                problems.append("fixture 'valid' must pass but failed:\n    " + "\n    ".join(got))
        for case in REQUIRED_CASES:
            folder = FIXTURES / case
            expect_file = folder / "expect.txt"
            if not expect_file.is_file():
                problems.append(f"fixture '{case}' is missing (needs a tree and expect.txt)")
                continue
            got = run_checks(folder)
            if not got:
                problems.append(f"fixture '{case}' must fail but passed")
            elif not all(line_re.match(line) for line in got) or any("Traceback" in line for line in got):
                problems.append(f"fixture '{case}': malformed failure line in {got}")
            else:
                problems += check_expectations(case, expect_file.read_text(encoding="utf-8"), got)
    if net.attempts:
        problems.append(f"the checker tried to use the network {len(net.attempts)} time(s)")
    for folder in sorted(p.name for p in FIXTURES.iterdir() if p.is_dir()):
        if folder != "valid" and folder not in REQUIRED_CASES:
            problems.append(f"fixture folder '{folder}' is not listed in REQUIRED_CASES")
    if problems:
        print("self-test FAILED:")
        for p in problems:
            print("  " + p)
        return 1
    print(f"self-test ok: 'valid' passes and {len(REQUIRED_CASES)} failing fixtures fail for the expected reason, "
          "with no network use")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="tree to check (default: this repo)")
    parser.add_argument("--self-test", action="store_true", help="run the checker against its fixtures")
    args = parser.parse_args(argv)
    check_environment()
    if args.self_test:
        return self_test()
    failures = run_checks(args.root.resolve())
    for line in failures:
        print(line)
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("contracts and task specs ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
