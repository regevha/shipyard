"""Checks real HTTP responses against the four contracts in contracts/.

Every `$ref` (local and cross-file) is inlined from disk; keywords next to a `$ref` become an
`allOf`. A response is looked up by service, method, concrete path (matched against the path
templates) and status code; a status the contract does not list for that operation is a failure.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
import yaml
from jsonschema import Draft202012Validator

SERVICE_CONTRACTS = {
    "pipeline-runner": "api-pipeline-runner.yml",
    "artifact-store": "api-artifact-store.yml",
    "release-service": "api-release-service.yml",
    "dashboard": "api-dashboard.yml",
}

# Paths the contracts leave out on purpose: the dashboard's web pages (api-dashboard.yml info).
UNCONTRACTED = {("dashboard", "GET", "/"), ("dashboard", "GET", "/static/app.js")}


def find_contracts_dir(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "contracts" / "errors.yml").is_file():
            return parent / "contracts"
    raise RuntimeError(f"no contracts/errors.yml above {here}")


class ContractError(AssertionError):
    pass


class Contracts:
    def __init__(self, contracts_dir: Path | None = None) -> None:
        self.dir = contracts_dir or find_contracts_dir()
        self._docs: dict[Path, Any] = {}
        self._validators: dict[tuple[str, str, str, str, str], Draft202012Validator] = {}

    # ------------------------------------------------------------------ $ref inlining
    def _doc(self, path: Path) -> Any:
        path = path.resolve()
        if path not in self._docs:
            self._docs[path] = yaml.safe_load(path.read_text())
        return self._docs[path]

    def _pointer(self, path: Path, fragment: str) -> Any:
        node = self._doc(path)
        for raw in [p for p in fragment.lstrip("/").split("/") if p]:
            key = raw.replace("~1", "/").replace("~0", "~")
            node = node[int(key)] if isinstance(node, list) else node[key]
        return node

    def inline(self, node: Any, path: Path, seen: tuple[str, ...] = ()) -> Any:
        if isinstance(node, list):
            return [self.inline(item, path, seen) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            file_part, _, fragment = str(node["$ref"]).partition("#")
            target = (path.parent / file_part).resolve() if file_part else path.resolve()
            key = f"{target}#{fragment}"
            if key in seen:
                raise RuntimeError(f"recursive $ref {key}")
            resolved = self.inline(self._pointer(target, fragment), target, (*seen, key))
            siblings = {k: self.inline(v, path, seen) for k, v in node.items() if k != "$ref"}
            if not siblings:
                return resolved
            all_of = [*siblings.pop("allOf", []), resolved]
            return {**siblings, "allOf": all_of}
        out = {
            k: self.inline(v, path, seen)
            for k, v in node.items()
            if k not in ("$id", "$schema", "$defs")
        }
        return out

    def validator(self, contract: str, pointer: str) -> Draft202012Validator:
        """Validator for a schema, e.g. ("api-pipeline-runner.yml", "/components/schemas/Run")."""
        path = self.dir / contract
        schema = self.inline({"$ref": f"{contract}#{pointer}"}, path)
        return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)

    # ------------------------------------------------------------------ operations
    def _operation(self, service: str, method: str, url_path: str) -> tuple[Path, str, Any]:
        contract = SERVICE_CONTRACTS[service]
        path = self.dir / contract
        paths = self._doc(path)["paths"]
        for template, item in paths.items():
            pattern = "^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(template)) + "$"
            if re.match(pattern, url_path) and method.lower() in item:
                return path, template, item[method.lower()]
        raise ContractError(f"{service}: {method} {url_path} is not in {contract}")

    def operations(self) -> set[tuple[str, str, str]]:
        """Every (service, METHOD, path template) of the four contracts."""
        methods = ("get", "post", "put", "patch", "delete")
        return {
            (service, method.upper(), template)
            for service, contract in SERVICE_CONTRACTS.items()
            for template, item in self._doc(self.dir / contract)["paths"].items()
            for method in item
            if method in methods
        }

    def template(self, service: str, method: str, url_path: str) -> str:
        return self._operation(service, method, url_path)[1]

    def check(self, service: str, response: httpx.Response) -> Any:
        """Validate one response against its operation; return the parsed JSON body (or None)."""
        method = response.request.method
        url_path = response.request.url.path
        if (service, method, url_path) in UNCONTRACTED:
            return None
        path, template, operation = self._operation(service, method, url_path)
        status = str(response.status_code)
        where = f"{service}: {method} {url_path} -> {status}"
        responses = operation.get("responses", {})
        if status not in responses:
            raise ContractError(f"{where}: status not listed in the contract ({sorted(responses)})")
        spec = responses[status]
        spec_path = path
        if "$ref" in spec:
            file_part, _, fragment = spec["$ref"].partition("#")
            spec_path = (path.parent / file_part).resolve() if file_part else path
            spec = self._pointer(spec_path, fragment)
        content = spec.get("content") or {}
        media = response.headers.get("content-type", "").split(";")[0].strip()
        for name, header in (spec.get("headers") or {}).items():
            value = response.headers.get(name)
            if value is None:
                if header.get("required"):
                    raise ContractError(f"{where}: required header {name} missing")
                continue
            schema = self.inline(header.get("schema", {}), spec_path)
            errors = list(Draft202012Validator(schema).iter_errors(value))
            if errors:
                raise ContractError(f"{where}: header {name}={value!r}: {errors[0].message}")
        if not content:
            if response.content:
                raise ContractError(
                    f"{where}: contract has no body, got {response.content[:200]!r}"
                )
            return None
        if media not in content:
            raise ContractError(f"{where}: content-type {media!r} not in {sorted(content)}")
        if media != "application/json":
            return None
        body = response.json()
        schema_node = content[media].get("schema")
        if schema_node is None:
            return body
        key = (service, method, template, status, media)
        if key not in self._validators:
            schema = self.inline(schema_node, spec_path)
            self._validators[key] = Draft202012Validator(
                schema, format_checker=Draft202012Validator.FORMAT_CHECKER
            )
        errors = sorted(self._validators[key].iter_errors(body), key=lambda e: list(e.path))
        if errors:
            first = errors[0]
            raise ContractError(
                f"{where}: body does not match the contract at {list(first.path)}: "
                f"{first.message}\nbody: {body!r}"
            )
        return body
