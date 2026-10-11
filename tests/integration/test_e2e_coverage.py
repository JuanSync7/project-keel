"""
title: Integration — every endpoint an enabled transport serves is named by an e2e scenario or exempt with a reason
kind: tests
layer: n/a
summary: The CONVENTIONS section 17 end-to-end gate. It derives each enabled transport's endpoints from the code, never from a list - the REST app's OpenAPI paths (written by the transport's exporter as a child), each MCP server's tools (asked over its real stdio), each gRPC service's rpcs (read from its .proto files) - and fails when one is neither named by a scenario under config/project.json `e2e.scenario_dir` with `@pytest.mark.<e2e.marker>("<id>")` nor exempt in `e2e.exempt` with a reason. It fails closed: a route the app serves that its OpenAPI document cannot list (an allowlist over a child's walk of the routes the app loads, plus a syntax pass that points at the line), a marker it cannot read or that applies to no test pytest collects, an unknown source kind, a stale marker, a stale, redundant or reasonless exemption, and a deriver that finds nothing are each red. Each fault-injection twin plants one fault and asserts exactly one more finding. The REST half skips, naming the `transport` extra, without FastAPI; the MCP and proto halves still judge.
"""

import ast
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from scripts.child_env import build_child_env
from scripts.pytest_markers import attached_markers, collection_rule
from scripts.pytest_markers import is_marker as _is_marker

import live_server
import optional_deps

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = "config/project.json"

#: The config key that holds the exemptions; test_doc_drift imports its leaf.
EXEMPT_KEY = "e2e.exempt"
#: How a transport's endpoints are derived: the closed vocabulary of
#: config/project.json `e2e.sources` values.
SOURCE_KINDS = ("mcp-stdio", "none", "openapi", "proto")

_TESTS_DIR = "tests"
_HTTP_METHODS = ("delete", "get", "head", "options", "patch", "post", "put", "trace")
# OpenAPI 3 path-item keys that are not operations: allowed and ignored. Any
# other key is a shape this gate does not understand, so it is an error.
_PATH_ITEM_META = ("$ref", "description", "parameters", "servers", "summary")
# Route forms the OpenAPI document cannot show: a websocket, a mounted
# sub-application, a Starlette route, or a route hidden from the schema.
_UNDERIVABLE_CALLS = (
    "add_api_websocket_route",
    "add_route",
    "add_websocket_route",
    "mount",
    "route",
    "websocket",
    "websocket_route",
)
_HIDDEN_KEYWORD = "include_in_schema"
_UNATTACHED = "decorates no test pytest collects"
_ID = re.compile(r"^(\S+) (\S(?:.*\S)?)$")
# The id body each source kind produces; a marker in another shape names nothing
# the gate can derive, so it is an error rather than a silent miss.
_ID_BODY = {
    "mcp-stdio": re.compile(r"^[^/\s]+/[^/\s]+$"),
    "none": re.compile(r"^(?!)"),  # a `none` transport serves no endpoint
    "openapi": re.compile(
        r"^(?:%s) /\S*$" % "|".join(m.upper() for m in _HTTP_METHODS)
    ),
    "proto": re.compile(r"^/(?:[A-Za-z_][\w.]*\.)?[A-Za-z_]\w*/[A-Za-z_]\w*$"),
}
_MCP_INIT_ID, _MCP_LIST_ID = 1, 2


class GateError(Exception):
    """A configuration, derivation or marker the gate cannot judge: red."""


# --------------------------------------------------------------------- config


def load_config(root):
    """(`e2e` block, `transports` block) of config/project.json."""
    try:
        e2e, manifest = live_server.load_e2e_config(str(root))
    except live_server.LiveServerError as exc:
        raise GateError(str(exc)) from None
    transports = manifest.get("transports")
    if not isinstance(transports, dict):
        raise GateError("%s has no `transports` object" % _MANIFEST)
    return e2e, transports


def _expect(value, kind, key):
    if not isinstance(value, kind) or isinstance(value, bool):
        raise GateError(
            "%s: `%s` must be a %s, not %r" % (_MANIFEST, key, kind.__name__, value)
        )
    return value


def source_errors(e2e, transports):
    """Each way `e2e.sources` disagrees with `transports`, by key."""
    errors = []
    sources = e2e.get("sources")
    if not isinstance(sources, dict):
        return ["%s: `e2e.sources` must be an object" % _MANIFEST]
    available = transports.get("available") or {}
    errors.extend(
        "%s: `e2e.sources.%s` is missing: the enabled transport %r has no "
        "declared way to derive its endpoints" % (_MANIFEST, name, name)
        for name in transports.get("enabled") or []
        if name not in sources
    )
    for name in sorted(sources):
        if name not in available:
            errors.append(
                "%s: `e2e.sources.%s` names a transport that is not in "
                "`transports.available`" % (_MANIFEST, name)
            )
        if sources[name] not in SOURCE_KINDS:
            errors.append(
                "%s: `e2e.sources.%s` is %r, not one of %s"
                % (_MANIFEST, name, sources[name], ", ".join(SOURCE_KINDS))
            )
    return errors


# ------------------------------------------------------------------- derivers


def _rel(root, path):
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _py_files(directory):
    return sorted(
        p for p in Path(directory).rglob("*.py") if "__pycache__" not in p.parts
    )


def route_form_errors(root, rest_dir):
    """file:line of every route form the OpenAPI document cannot show."""
    errors = []
    for path in _py_files(rest_dir):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            where = "%s:%d" % (_rel(root, path), node.lineno)
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in _UNDERIVABLE_CALLS:
                errors.append(
                    "%s: route form the gate cannot derive: `.%s(...)` serves "
                    "something the OpenAPI document does not list" % (where, func.attr)
                )
            for kw in node.keywords:
                if kw.arg != _HIDDEN_KEYWORD:
                    continue
                if not (isinstance(kw.value, ast.Constant) and kw.value.value is True):
                    errors.append(
                        "%s: route form the gate cannot derive: `%s=` other than "
                        "the literal True can hide a route from the OpenAPI document"
                        % (where, _HIDDEN_KEYWORD)
                    )
    return errors


def unlisted_route_errors(walk):
    """One error per route the app serves that its OpenAPI document cannot
    list. It is an allowlist over what the server loads (tests/live_server.py
    `rest_routes`), so a route form nobody anticipated is red, not skipped: a
    route passes only as an APIRoute whose effective `include_in_schema` is
    True, or as one of the framework's own documentation routes, which the
    app's settings name."""
    routes = walk.get("routes") if isinstance(walk, dict) else None
    docs = walk.get("docs") if isinstance(walk, dict) else None
    if not isinstance(routes, list) or not isinstance(docs, list):
        return ["the route walk returned no `routes` and `docs` lists: %r" % (walk,)]
    errors = []
    for route in routes:
        if route.get("api") and route.get("in_schema") is True:
            continue
        if not route.get("api") and route.get("path") in docs:
            continue
        why = (
            "it is hidden from the schema (`%s` is not True)" % _HIDDEN_KEYWORD
            if route.get("api")
            else "it is a %s, not an APIRoute" % route.get("type")
        )
        errors.append(
            "%s: route `%s` is served but the OpenAPI document cannot list it: %s"
            % (route.get("where") or "<no source>", route.get("path"), why)
        )
    return errors


def derive_openapi(root, rest_dir, e2e):
    """`rest <METHOD> <path>` for every operation in the app's OpenAPI document,
    which the transport's own exporter writes as a child process."""
    optional_deps.importorskip("fastapi", extra="transport")
    errors = route_form_errors(root, rest_dir)
    if errors:
        raise GateError("\n".join(errors))
    timeout = _expect_number(e2e.get("list_timeout_s"), "e2e.list_timeout_s")
    try:
        walk = live_server.rest_routes(str(root), str(rest_dir), timeout)
    except live_server.LiveServerError as exc:
        raise GateError(str(exc)) from None
    errors = unlisted_route_errors(walk)
    if errors:
        raise GateError("\n".join(errors))
    exporter = Path(rest_dir) / _expect(
        e2e.get("openapi_exporter"), str, "e2e.openapi_exporter"
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "openapi.json"
        try:
            proc = subprocess.run(
                [sys.executable, str(exporter), "--out", str(out)],
                cwd=str(root),
                env=build_child_env(root=str(root)),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise GateError(
                "%s did not finish within %ss (%s `e2e.list_timeout_s`)"
                % (_rel(root, exporter), timeout, _MANIFEST)
            ) from None
        if proc.returncode != 0:
            raise GateError(
                "%s exited with code %d: %s"
                % (_rel(root, exporter), proc.returncode, proc.stderr.strip())
            )
        if not out.is_file():
            raise GateError(
                "%s exited 0 but wrote no OpenAPI document: %s"
                % (_rel(root, exporter), proc.stderr.strip())
            )
        document = json.loads(out.read_text(encoding="utf-8"))
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise GateError("the OpenAPI document has no `paths` object")
    endpoints = set()
    for path, item in paths.items():
        for key in item:
            if key in _HTTP_METHODS:
                endpoints.add("rest %s %s" % (key.upper(), path))
            elif key not in _PATH_ITEM_META:
                raise GateError(
                    "OpenAPI path %r has key %r, which is neither an HTTP method "
                    "nor a path-item field this gate knows" % (path, key)
                )
    return endpoints


def _expect_number(value, key):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise GateError(
            "%s: `%s` must be a positive number, not %r" % (_MANIFEST, key, value)
        )
    return value


def _mcp_servers(mcp_dir):
    """The __main__-guarded scripts directly in *mcp_dir*: the rule
    test_reference_drift uses to tell a server from a library."""
    from test_reference_drift import _has_main_guard  # lazy: it imports test_doc_drift

    servers = []
    for path in sorted(Path(mcp_dir).glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _has_main_guard(tree):
            servers.append(path)
    return servers


def derive_mcp(root, mcp_dir, e2e):
    """`mcp <serverInfo.name>/<tool>` for every tool each server lists when
    asked over its own stdio."""
    timeout = _expect_number(e2e.get("list_timeout_s"), "e2e.list_timeout_s")
    extra = _expect(e2e.get("mcp_env"), dict, "e2e.mcp_env")
    messages = [
        {
            "jsonrpc": "2.0",
            "id": _MCP_INIT_ID,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
        },
        {"jsonrpc": "2.0", "id": _MCP_LIST_ID, "method": "tools/list"},
    ]
    endpoints = set()
    for path in _mcp_servers(mcp_dir):
        where = _rel(root, path)
        try:
            replies = live_server.mcp_exchange(root, path, messages, timeout, extra)
        except live_server.LiveServerError as exc:
            raise GateError(str(exc)) from None
        by_id = {r.get("id"): r for r in replies if isinstance(r, dict)}
        info = (by_id.get(_MCP_INIT_ID) or {}).get("result", {}).get("serverInfo")
        name = info.get("name") if isinstance(info, dict) else None
        if not isinstance(name, str) or not name:
            raise GateError("%s answered initialize with no serverInfo.name" % where)
        tools = (by_id.get(_MCP_LIST_ID) or {}).get("result", {}).get("tools")
        if not isinstance(tools, list) or not tools:
            raise GateError("%s (%s) listed no tools" % (where, name))
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                raise GateError("%s (%s) listed a tool with no name" % (where, name))
            endpoints.add("mcp %s/%s" % (name, tool["name"]))
    return endpoints


def _strip_proto_comments(text):
    """*text* with `//` and `/* */` comments blanked, newlines and string
    literals kept, so offsets and line numbers still point at the source."""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'":
            end = i + 1
            while end < n and text[end] != ch:
                end += 2 if text[end] == "\\" else 1
            out.append(text[i : end + 1])
            i = end + 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            out.append(" " * (end - i))
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append("".join(c if c == "\n" else " " for c in text[i:end]))
            i = end
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _skip_string(text, i):
    quote, i = text[i], i + 1
    while i < len(text) and text[i] != quote:
        i += 2 if text[i] == "\\" else 1
    return i + 1


def _block_end(text, open_pos):
    """The offset just past the brace matching the one at *open_pos*."""
    depth, i = 0, open_pos
    while i < len(text):
        ch = text[i]
        if ch in "\"'":
            i = _skip_string(text, i)
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise GateError("unbalanced brace at offset %d" % open_pos)


def _statement_end(text, i, stop):
    """The offset just past the `;` that ends the statement at *i*."""
    while i < stop:
        ch = text[i]
        if ch in "\"'":
            i = _skip_string(text, i)
            continue
        if ch == "{":
            i = _block_end(text, i)
            continue
        if ch == ";":
            return i + 1
        i += 1
    return None


_PACKAGE = re.compile(r"\bpackage\s+([A-Za-z_][\w.]*)\s*;")
_SERVICE = re.compile(r"\bservice\s+([A-Za-z_]\w*)\s*\{")
_TYPE = r"\(\s*(?:stream\s+)?\.?[A-Za-z_][\w.]*\s*\)"
_RPC = re.compile(r"rpc\s+([A-Za-z_]\w*)\s*%s\s*returns\s*%s\s*([;{])" % (_TYPE, _TYPE))
_OPTION = re.compile(r"option\b")


def derive_proto(root, proto_dir):
    """`grpc /<package>.<Service>/<Rpc>` for every rpc of every service in the
    .proto files under *proto_dir*."""
    endpoints = set()
    for path in sorted(Path(proto_dir).rglob("*.proto")):
        where = _rel(root, path)
        text = _strip_proto_comments(path.read_text(encoding="utf-8"))
        package = _PACKAGE.search(text)
        prefix = package.group(1) + "." if package else ""
        for service in _SERVICE.finditer(text):
            body_start = service.end()
            body_end = _block_end(text, service.end() - 1) - 1
            i = body_start
            while i < body_end:
                if text[i].isspace() or text[i] == ";":
                    i += 1
                    continue
                rpc = _RPC.match(text, i)
                if rpc:
                    endpoints.add(
                        "grpc /%s%s/%s" % (prefix, service.group(1), rpc.group(1))
                    )
                    i = rpc.end()
                    if rpc.group(2) == "{":
                        i = _block_end(text, i - 1)
                    continue
                if _OPTION.match(text, i):
                    end = _statement_end(text, i, body_end)
                    if end is not None:
                        i = end
                        continue
                raise GateError(
                    "%s:%d: service %s holds a statement that is neither `rpc` nor "
                    "`option`; the gate cannot derive its endpoints"
                    % (where, text.count("\n", 0, i) + 1, service.group(1))
                )
    return endpoints


def derive_endpoints(root, transport):
    """The endpoint ids *transport* serves, by its `e2e.sources` kind. A kind
    other than `none` that finds nothing is an error, not an empty set."""
    root = Path(root)
    e2e, transports = load_config(root)
    errors = source_errors(e2e, transports)
    if errors:
        raise GateError("\n".join(errors))
    if transport not in e2e["sources"]:
        raise GateError("%s: `e2e.sources.%s` is missing" % (_MANIFEST, transport))
    kind = e2e["sources"][transport]
    directory = root / transports["available"][transport]
    if kind == "none":
        return set()
    if kind == "openapi":
        endpoints = derive_openapi(root, directory, e2e)
    elif kind == "mcp-stdio":
        endpoints = derive_mcp(root, directory, e2e)
    else:
        endpoints = derive_proto(root, directory)
    if not endpoints:
        raise GateError(
            "%s: transport %r (`e2e.sources.%s` = %r) derived zero endpoints from "
            "%s; a transport that serves nothing is declared `none`"
            % (_MANIFEST, transport, transport, kind, _rel(root, directory))
        )
    return endpoints


# -------------------------------------------------------------------- markers


def id_errors(endpoint, e2e, transports):
    """Why *endpoint* is not a well-formed id of an available transport."""
    match = _ID.match(endpoint)
    if not match:
        return ["`%s` is not `<transport> <endpoint>`" % endpoint]
    transport, body = match.groups()
    if transport not in (transports.get("available") or {}):
        return [
            "`%s` names transport %r, which is not in `transports.available`"
            % (endpoint, transport)
        ]
    kind = (e2e.get("sources") or {}).get(transport)
    pattern = _ID_BODY.get(kind)
    if pattern is None or not pattern.match(body):
        return [
            "`%s` is not an id the %r source (%s) derives" % (endpoint, transport, kind)
        ]
    return []


def scan_markers(root, rule):
    """(named, errors): every `pytest.mark.<marker>("<id>")` under tests/ that
    applies to a test *rule* collects, as {id: [path:line, ...]}, and every
    marker the gate cannot read or that applies to no collected test."""
    root = Path(root)
    e2e, transports = load_config(root)
    marker = _expect(e2e.get("marker"), str, "e2e.marker")
    scenario_dir = _expect(e2e.get("scenario_dir"), str, "e2e.scenario_dir").rstrip("/")
    named, errors = {}, []
    for path in _py_files(root / _TESTS_DIR):
        rel = _rel(root, path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        called = set()
        attached = attached_markers(tree, marker, rule)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_marker(node.func, marker):
                called.add(id(node.func))
                where = "%s:%d" % (rel, node.lineno)
                if not rel.startswith(scenario_dir + "/"):
                    errors.append(
                        "%s: an `%s` marker outside %s (`e2e.scenario_dir`)"
                        % (where, marker, scenario_dir)
                    )
                    continue
                if id(node) not in attached:
                    errors.append(
                        "%s: an `%s` marker that %s names nothing: put it on a "
                        "test function or class (`python_functions` %s, "
                        "`python_classes` %s) or in a `pytestmark`"
                        % (where, marker, _UNATTACHED, list(rule[0]), list(rule[1]))
                    )
                    continue
                args = node.args
                if (
                    len(args) != 1
                    or node.keywords
                    or not isinstance(args[0], ast.Constant)
                    or not isinstance(args[0].value, str)
                ):
                    errors.append(
                        "%s: `%s` takes exactly one string literal, the endpoint id"
                        % (where, marker)
                    )
                    continue
                problems = id_errors(args[0].value, e2e, transports)
                if problems:
                    errors.extend("%s: %s" % (where, p) for p in problems)
                    continue
                named.setdefault(args[0].value, []).append(where)
        errors.extend(
            "%s:%d: a bare `%s` marker names no endpoint" % (rel, node.lineno, marker)
            for node in ast.walk(tree)
            if _is_marker(node, marker) and id(node) not in called
        )
    return named, sorted(errors)


def named_endpoints(root, rule):
    """{id: [path:line, ...]}; a marker the gate cannot read is an error."""
    named, errors = scan_markers(root, rule)
    if errors:
        raise GateError("\n".join(errors))
    return named


# ------------------------------------------------------------------- findings


def _reason_ok(reason):
    return isinstance(reason, str) and bool(reason.strip())


def unnamed(endpoints, named, exempt):
    """Each endpoint no scenario names and no reasoned exemption covers."""
    return sorted(
        "unnamed endpoint `%s`: no e2e scenario names it and %s `%s` does not "
        "exempt it with a reason" % (e, _MANIFEST, EXEMPT_KEY)
        for e in endpoints
        if e not in named and not (e in exempt and _reason_ok(exempt[e]))
    )


def stale_findings(endpoints, named, exempt, transports, unjudged=()):
    """Markers and exemptions that name nothing served, and exemptions that are
    redundant or carry no reason. Ids of an *unjudged* transport (its deriver
    skipped) are not called stale: the gate does not know what it serves."""

    def judged(endpoint):
        return endpoint.split(" ", 1)[0] not in unjudged

    out = [
        "stale marker `%s` at %s: no enabled transport (%s) serves it"
        % (endpoint, ", ".join(named[endpoint]), ", ".join(transports))
        for endpoint in sorted(named)
        if endpoint not in endpoints and judged(endpoint)
    ]
    for endpoint in sorted(exempt):
        if endpoint not in endpoints and judged(endpoint):
            out.append(
                "stale exemption `%s` in %s `%s`: no enabled transport (%s) serves it"
                % (endpoint, _MANIFEST, EXEMPT_KEY, ", ".join(transports))
            )
        if endpoint in named:
            out.append(
                "redundant exemption `%s` in %s `%s`: a scenario names it at %s"
                % (endpoint, _MANIFEST, EXEMPT_KEY, ", ".join(named[endpoint]))
            )
        if not _reason_ok(exempt[endpoint]):
            out.append(
                "reasonless exemption `%s` in %s `%s`: it exempts nothing until it "
                "says why the endpoint has no scenario"
                % (endpoint, _MANIFEST, EXEMPT_KEY)
            )
    return out


def findings(endpoints, named, exempt, transports, unjudged=()):
    """Every finding, sorted: unnamed endpoints and stale, redundant or
    reasonless markers and exemptions."""
    return sorted(
        unnamed(endpoints, named, exempt)
        + stale_findings(endpoints, named, exempt, transports, unjudged)
    )


def _exempt(e2e):
    return _expect(e2e.get("exempt"), dict, EXEMPT_KEY)


@functools.lru_cache(maxsize=None)
def _derived(root, transport):
    """(endpoints, skip reason or None): derivation is a child process per
    server, so each transport is derived once per session."""
    try:
        return frozenset(derive_endpoints(root, transport)), None
    except pytest.skip.Exception as exc:
        return frozenset(), str(exc)


def _all_derived(root):
    _e2e, transports = load_config(root)
    endpoints, skipped = set(), {}
    for transport in transports.get("enabled") or []:
        found, reason = _derived(str(root), transport)
        if reason is not None:
            skipped[transport] = reason
        endpoints |= found
    return endpoints, skipped, list(transports.get("enabled") or [])


def _enabled():
    try:
        return list(load_config(_ROOT)[1].get("enabled") or [])
    except GateError:
        return ["<config/project.json has no e2e block>"]


# ---------------------------------------------------------------------- gates


@pytest.mark.parametrize("transport", _enabled())
def test_every_endpoint_of_an_enabled_transport_is_named_or_exempt(
    transport, collect_rule
):
    e2e, _transports = load_config(_ROOT)
    found, reason = _derived(str(_ROOT), transport)
    if reason is not None:
        pytest.skip(reason)
    if e2e["sources"][transport] == "none":
        # Declared to serve nothing of its own (an edge proxy): nothing to name.
        assert found == frozenset()
        return
    assert found, "%s derived no endpoints" % transport
    gaps = unnamed(found, named_endpoints(_ROOT, collect_rule), _exempt(e2e))
    assert not gaps, "\n".join(gaps)


def test_no_marker_or_exemption_names_an_endpoint_that_does_not_exist(collect_rule):
    e2e, _transports = load_config(_ROOT)
    endpoints, skipped, enabled = _all_derived(_ROOT)
    problems = stale_findings(
        endpoints,
        named_endpoints(_ROOT, collect_rule),
        _exempt(e2e),
        enabled,
        tuple(skipped),
    )
    assert not problems, "\n".join(problems)
    if skipped:
        pytest.skip(
            "markers and exemptions of %s not judged stale: %s"
            % (", ".join(sorted(skipped)), "; ".join(skipped.values()))
        )


# ------------------------------------------------------ fault-injection twins


@pytest.fixture(scope="module")
def collect_rule(pytestconfig):
    """This session's test-collection rule, which a marker must sit under."""
    return collection_rule(pytestconfig)


def _rest_endpoints():
    found, reason = _derived(str(_ROOT), "rest")
    if reason is not None:
        pytest.skip(reason)
    return set(found)


def _baseline(rule, endpoints=None, named=None, planted=None):
    """The findings over this tree, with *planted* exemptions added on top of
    the ones the project declares: a twin plants one fault, it does not wipe
    the project's own entries."""
    e2e, transports = load_config(_ROOT)
    endpoints = _all_derived(_ROOT)[0] if endpoints is None else endpoints
    named = named_endpoints(_ROOT, rule) if named is None else named
    exempt = dict(_exempt(e2e), **(planted or {}))
    return findings(endpoints, named, exempt, transports["enabled"])


def _a_named_endpoint(endpoints, named):
    """One endpoint this tree serves and a scenario names, chosen from the tree
    rather than typed, so the twins hold in any project."""
    both = sorted(set(endpoints) & set(named))
    assert both, "no endpoint is both served and named -- zero items"
    return both[0]


def _write_config(root, mutate):
    data = json.loads((_ROOT / _MANIFEST).read_text(encoding="utf-8"))
    mutate(data)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / _MANIFEST).write_text(json.dumps(data), encoding="utf-8")
    return root


def _shadow_root(tmp_path, copy):
    """A root that symlinks every top-level entry of the real one except the
    directory *copy* (a relative path), which it copies so a test can plant a
    fault in it without touching the tree."""
    shadow = tmp_path / "root"
    parts = Path(copy).parts
    here, real = shadow, _ROOT
    for depth, part in enumerate(parts):
        here.mkdir(parents=True, exist_ok=True)
        for entry in sorted(real.iterdir()):
            if entry.name in (part, ".git"):
                continue
            (here / entry.name).symlink_to(entry)
        here, real = here / part, real / part
        if depth == len(parts) - 1:
            shutil.copytree(
                str(real), str(here), ignore=shutil.ignore_patterns("__pycache__")
            )
    return shadow


def test_a_planted_route_with_no_scenario_is_exactly_one_more_finding(
    tmp_path, collect_rule
):
    rest = load_config(_ROOT)[1]["available"]["rest"]
    baseline = _baseline(collect_rule)
    shadow = _shadow_root(tmp_path, rest)
    with open(str(shadow / rest / "app.py"), "a", encoding="utf-8") as fh:
        fh.write(
            '\n\n@app.get("/__planted__")\ndef planted() -> dict:\n'
            '    return {"planted": True}\n'
        )
    planted = derive_endpoints(shadow, "rest")
    endpoints = (_all_derived(_ROOT)[0] - _rest_endpoints()) | planted
    after = _baseline(collect_rule, endpoints=endpoints)
    added = sorted(set(after) - set(baseline))
    assert len(after) == len(baseline) + 1, after
    assert len(added) == 1 and "`rest GET /__planted__`" in added[0], added


def test_a_stale_exemption_is_red(collect_rule):
    baseline = _baseline(collect_rule)
    after = _baseline(collect_rule, planted={"rest GET /no-such-route": "r"})
    added = sorted(set(after) - set(baseline))
    assert len(after) == len(baseline) + 1, after
    assert added[0].startswith("stale exemption `rest GET /no-such-route`"), added


def test_a_redundant_or_reasonless_exemption_is_red(collect_rule):
    endpoints = _rest_endpoints() | _all_derived(_ROOT)[0]
    named = named_endpoints(_ROOT, collect_rule)
    baseline = _baseline(collect_rule, endpoints=endpoints, named=named)

    target = _a_named_endpoint(endpoints, named)

    redundant = _baseline(
        collect_rule, endpoints=endpoints, named=named, planted={target: "r"}
    )
    added = sorted(set(redundant) - set(baseline))
    assert len(redundant) == len(baseline) + 1, redundant
    assert added[0].startswith("redundant exemption `%s`" % target), added

    without = {k: v for k, v in named.items() if k != target}
    base_without = _baseline(collect_rule, endpoints=endpoints, named=without)
    reasonless = _baseline(
        collect_rule, endpoints=endpoints, named=without, planted={target: " "}
    )
    added = sorted(set(reasonless) - set(base_without))
    assert len(reasonless) == len(base_without) + 1, reasonless
    assert added[0].startswith("reasonless exemption `%s`" % target), added


def _copy_scenarios(tmp_path):
    """A root with the real config and a copy of the scenario dir only."""
    e2e, _transports = load_config(_ROOT)
    root = _write_config(tmp_path / "root", lambda data: None)
    shutil.copytree(
        str(_ROOT / e2e["scenario_dir"]),
        str(root / e2e["scenario_dir"]),
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return root, root / e2e["scenario_dir"]


def test_a_marker_naming_no_endpoint_is_red(tmp_path, collect_rule):
    root, scenarios = _copy_scenarios(tmp_path)
    (scenarios / "test_gone.py").write_text(
        "import pytest\n\n\n@pytest.mark.endpoint('rest GET /gone')\n"
        "def test_gone():\n    pass\n",
        encoding="utf-8",
    )
    baseline = _baseline(collect_rule)
    after = _baseline(collect_rule, named=named_endpoints(root, collect_rule))
    added = sorted(set(after) - set(baseline))
    assert len(after) == len(baseline) + 1, after
    assert added[0].startswith(
        "stale marker `rest GET /gone` at tests/e2e/test_gone.py:4"
    )


@pytest.mark.parametrize(
    "where, source, expected",
    [
        (
            "tests/e2e/test_x.py",
            "ID = 'rest GET /health'\n@pytest.mark.endpoint(ID)\n",
            "one string literal",
        ),
        (
            "tests/e2e/test_x.py",
            "N = 'health'\n@pytest.mark.endpoint(f'rest GET /{N}')\n",
            "one string literal",
        ),
        (
            "tests/integration/test_x.py",
            "@pytest.mark.endpoint('rest GET /health')\n",
            "outside tests/e2e",
        ),
        (
            "tests/e2e/test_x.py",
            "@pytest.mark.endpoint('soap X')\n",
            "not in `transports.available`",
        ),
        (
            "tests/e2e/test_x.py",
            "@pytest.mark.endpoint('rest get /health')\n",
            "not an id",
        ),
        (
            "tests/e2e/test_x.py",
            "@pytest.mark.endpoint('rest GET /health ')\n",
            "is not `<transport> <endpoint>`",
        ),
        (
            "tests/e2e/test_x.py",
            "pytestmark = pytest.mark.endpoint\n",
            "bare `endpoint`",
        ),
    ],
    ids=[
        "name-arg",
        "f-string",
        "outside-scenario-dir",
        "unknown-transport",
        "lower-case-method",
        "trailing-space",
        "bare-marker",
    ],
)
def test_a_marker_the_gate_cannot_read_is_red(
    tmp_path, where, source, expected, collect_rule
):
    root, _scenarios = _copy_scenarios(tmp_path)
    target = root / where
    target.parent.mkdir(parents=True, exist_ok=True)
    body = "import pytest\n\n" + source + "def test_x():\n    pass\n"
    target.write_text(body, encoding="utf-8")
    line = source.count("\n")  # the marker sits on the source's last line
    _named, errors = scan_markers(root, collect_rule)
    assert len(errors) == 1, errors
    assert errors[0].startswith("%s:%d: " % (where, line + 2)), errors
    assert expected in errors[0], errors
    with pytest.raises(GateError, match=re.escape(where)):
        named_endpoints(root, collect_rule)


@pytest.mark.parametrize(
    "fault",
    [
        "\n@app.websocket('/ws')\nasync def ws(socket):\n    pass\n",
        "\napp.mount('/static', app)\n",
        "\n@app.get('/h', include_in_schema=False)\ndef hidden() -> dict:\n    return {}\n",
        "\nFLAG = True\n@app.get('/h', include_in_schema=FLAG)\ndef hidden() -> dict:\n    return {}\n",
    ],
    ids=["websocket", "mount", "hidden-literal", "hidden-name"],
)
def test_a_route_form_the_gate_cannot_derive_is_red(tmp_path, fault):
    rest = load_config(_ROOT)[1]["available"]["rest"]
    copy = tmp_path / "rest"
    shutil.copytree(
        str(_ROOT / rest), str(copy), ignore=shutil.ignore_patterns("__pycache__")
    )
    assert route_form_errors(tmp_path, copy) == []
    app = copy / "app.py"
    before = app.read_text(encoding="utf-8")
    app.write_text(before + fault, encoding="utf-8")
    errors = route_form_errors(tmp_path, copy)
    assert len(errors) == 1, errors
    assert "route form the gate cannot derive" in errors[0], errors
    match = re.match(r"^rest/app\.py:(\d+): ", errors[0])
    assert match, errors
    planted_line = (
        before.count("\n")
        + next(n for n, text in enumerate(fault.split("\n")) if "app." in text)
        + 1
    )
    assert int(match.group(1)) == planted_line, (errors, planted_line)


@pytest.mark.parametrize(
    "source, line",
    [
        ("_UNUSED = pytest.mark.endpoint('rest GET /health')\n", 3),
        (
            "if False:\n    @pytest.mark.endpoint('rest GET /health')\n"
            "    def test_never():\n        pass\n",
            4,
        ),
        ("@pytest.mark.endpoint('rest GET /health')\ndef helper():\n    pass\n", 3),
        (
            "@pytest.mark.endpoint('rest GET /health')\nclass Helper:\n"
            "    def test_x(self):\n        pass\n",
            3,
        ),
        (
            "def test_outer():\n    @pytest.mark.endpoint('rest GET /health')\n"
            "    def test_inner():\n        pass\n",
            4,
        ),
        (
            "@pytest.mark.parametrize('x', [pytest.param(1, "
            "marks=pytest.mark.endpoint('rest GET /health'))])\n"
            "def test_x(x):\n    pass\n",
            3,
        ),
    ],
    ids=[
        "unused-variable",
        "if-false",
        "helper-function",
        "helper-class",
        "nested-function",
        "param-marks",
    ],
)
def test_a_marker_attached_to_no_collected_test_is_red(
    tmp_path, collect_rule, source, line
):
    root, scenarios = _copy_scenarios(tmp_path)
    (scenarios / "test_x.py").write_text("import pytest\n\n" + source, encoding="utf-8")
    named, errors = scan_markers(root, collect_rule)
    assert len(errors) == 1, errors
    assert errors[0].startswith("tests/e2e/test_x.py:%d: " % line), errors
    assert _UNATTACHED in errors[0], errors
    assert not [w for ws in named.values() for w in ws if "test_x.py" in w], named


def test_a_marker_on_a_collected_test_names_its_endpoint(tmp_path, collect_rule):
    root, scenarios = _copy_scenarios(tmp_path)
    (scenarios / "test_x.py").write_text(
        "import pytest\n\n"
        "pytestmark = [pytest.mark.e2e, pytest.mark.endpoint('rest GET /a')]\n\n\n"
        "@pytest.mark.endpoint('rest GET /b')\n"
        "class TestThings:\n"
        "    pytestmark = pytest.mark.endpoint('rest GET /c')\n\n"
        "    @pytest.mark.endpoint('rest GET /d')\n"
        "    def test_one(self):\n        pass\n\n\n"
        "@pytest.mark.endpoint('rest GET /e')\n"
        "async def test_two():\n    pass\n",
        encoding="utf-8",
    )
    named, errors = scan_markers(root, collect_rule)
    assert errors == [], errors
    mine = {
        e: ws for e, ws in named.items() if any("tests/e2e/test_x.py" in w for w in ws)
    }
    assert sorted(mine) == ["rest GET /%s" % c for c in "abcde"], named


_ELSEWHERE = "elsewhere_routes"


@pytest.mark.parametrize(
    "fault, elsewhere, served",
    [
        (
            "\nfrom starlette.responses import PlainTextResponse\n"
            "from starlette.routing import Route\n"
            "app.router.routes.append(Route('/__raw__', lambda r: "
            "PlainTextResponse('x')))\n",
            None,
            "/__raw__",
        ),
        (
            "\n@app.get('/__hidden__', **{'include_in_schema': False})\n"
            "def hidden() -> dict:\n    return {}\n",
            None,
            "/__hidden__",
        ),
        (
            "\nfrom %s import router as _elsewhere\napp.include_router(_elsewhere)\n"
            % _ELSEWHERE,
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
            "@router.get('/__elsewhere__', include_in_schema=False)\n"
            "def hidden() -> dict:\n    return {}\n",
            "/__elsewhere__",
        ),
        (
            "\nfrom %s import install\ninstall(app)\n" % _ELSEWHERE,
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
            "@router.get('/__hidden_router__')\n"
            "def shown() -> dict:\n    return {}\n"
            "def install(app):\n"
            "    app.include_router(router, include_in_schema=False)\n",
            "/__hidden_router__",
        ),
    ],
    ids=["starlette-route", "kwargs-hidden", "imported-hidden", "router-hidden"],
)
def test_a_served_route_the_openapi_document_does_not_list_is_red(
    tmp_path, fault, elsewhere, served
):
    # Each fault is invisible to the syntax pass over the REST directory: the
    # route form is not a call it knows, or it lives in a module outside the
    # directory. The walk over the app the server loads still sees it.
    optional_deps.importorskip("fastapi", extra="transport")
    rest = load_config(_ROOT)[1]["available"]["rest"]
    shadow = _shadow_root(tmp_path, rest)
    if elsewhere is not None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / ("%s.py" % _ELSEWHERE)).write_text(elsewhere, encoding="utf-8")
        fault = "\nimport sys\nsys.path.insert(0, %r)\n%s" % (str(outside), fault)
    with open(str(shadow / rest / "app.py"), "a", encoding="utf-8") as fh:
        fh.write(fault)
    assert route_form_errors(shadow, shadow / rest) == []
    with pytest.raises(GateError) as caught:
        derive_endpoints(shadow, "rest")
    message = str(caught.value)
    assert "`%s`" % served in message, message
    assert message.count("\n") == 0, message  # exactly one finding


def test_an_unknown_source_or_undeclared_transport_is_red(tmp_path):
    def sources(mutate):
        def apply(data):
            mutate(data["e2e"]["sources"])

        return apply

    root = _write_config(tmp_path / "a", sources(lambda s: s.update(rest="graphql")))
    with pytest.raises(GateError, match=re.escape("`e2e.sources.rest` is 'graphql'")):
        derive_endpoints(root, "rest")

    root = _write_config(tmp_path / "b", sources(lambda s: s.pop("mcp")))
    with pytest.raises(GateError, match=re.escape("`e2e.sources.mcp` is missing")):
        derive_endpoints(root, "rest")

    root = _write_config(tmp_path / "c", sources(lambda s: s.update(soap="none")))
    with pytest.raises(
        GateError, match=re.escape("`e2e.sources.soap` names a transport")
    ):
        derive_endpoints(root, "mcp")

    def empty_grpc(data):
        # Declared here, so the twin holds in a project that did not choose grpc.
        data["transports"]["available"]["grpc"] = "empty_grpc"
        data["e2e"]["sources"]["grpc"] = "proto"

    root = _write_config(tmp_path / "d", empty_grpc)
    (root / "empty_grpc").mkdir()
    with pytest.raises(GateError, match="derived zero endpoints"):
        derive_endpoints(root, "grpc")

    def empty_mcp(data):
        data["transports"]["available"]["mcp"] = "empty_mcp"

    root = _write_config(tmp_path / "e", empty_mcp)
    (root / "empty_mcp").mkdir()
    (root / "empty_mcp" / "library.py").write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(GateError, match="derived zero endpoints"):
        derive_endpoints(root, "mcp")


def _rpc_names(proto_dir):
    """Every `rpc <Name>` token in the .proto files under *proto_dir*, read
    with a plain pattern independent of the parser (comments not stripped, so
    it may only over-count)."""
    names = set()
    for path in sorted(Path(proto_dir).rglob("*.proto")):
        names.update(re.findall(r"\brpc\s+(\w+)", path.read_text(encoding="utf-8")))
    return names


def test_proto_derivation_reads_the_shipped_service_and_rejects_unknown_statements(
    tmp_path,
):
    # Each shipped proto transport (none in a project that did not choose one):
    # every rpc it declares is derived, as a well-formed id. The synthetic
    # files below pin the parser itself.
    e2e, transports = load_config(_ROOT)
    for transport, kind in sorted(e2e["sources"].items()):
        if kind != "proto" or transport not in transports["available"]:
            continue
        proto_dir = _ROOT / transports["available"][transport]
        derived = derive_proto(_ROOT, proto_dir)
        assert derived, "%s derived no rpc" % transport
        assert not [e for d in derived for e in id_errors(d, e2e, transports)]
        assert {d.rsplit("/", 1)[1] for d in derived} <= _rpc_names(proto_dir)

    (tmp_path / "ok.proto").write_text(
        'syntax = "proto3";\n'
        "/* package not.this; */\n"
        "service A {\n"
        "  option deprecated = true;  // service B { rpc Ghost(X) returns (Y); }\n"
        "  rpc One(stream .x.Req) returns (stream Res) {\n"
        '    option (google.api.http) = { get: "/v1/{name}" };\n'
        "  }\n"
        "  ;\n"
        "  rpc Two(Req) returns (Res);\n"
        "}\n"
        "service B { rpc Three(Req) returns (Res); }\n",
        encoding="utf-8",
    )
    assert derive_proto(tmp_path, tmp_path) == {
        "grpc /A/One",
        "grpc /A/Two",
        "grpc /B/Three",
    }

    (tmp_path / "bad.proto").write_text(
        "package p;\nservice S {\n  rpc Ok(A) returns (B);\n  stream Foo;\n}\n",
        encoding="utf-8",
    )
    with pytest.raises(GateError, match=re.escape("bad.proto:4: service S")):
        derive_proto(tmp_path, tmp_path)


def test_mcp_derivation_asks_each_server_over_stdio_and_times_out_closed(tmp_path):
    e2e, transports = load_config(_ROOT)
    mcp_dir = _ROOT / transports["available"]["mcp"]
    derived = derive_mcp(_ROOT, mcp_dir, e2e)
    assert not [e for d in derived for e in id_errors(d, e2e, transports)]
    # Each server is asked: one serverInfo name per __main__-guarded script.
    servers = {d.split(" ", 1)[1].split("/", 1)[0] for d in derived}
    assert len(servers) == len(_mcp_servers(mcp_dir)) > 0, (servers, derived)

    root = _write_config(tmp_path / "root", lambda data: None)
    servers = tmp_path / "servers"
    servers.mkdir()
    (servers / "hang.py").write_text(
        "import os, sys, time\n"
        "if __name__ == '__main__':\n"
        "    open(sys.argv[0] + '.pid', 'w').write(str(os.getpid()))\n"
        "    time.sleep(120)\n",
        encoding="utf-8",
    )
    with pytest.raises(GateError, match=re.escape("e2e.list_timeout_s")):
        derive_mcp(root, servers, dict(e2e, list_timeout_s=1))
    pid = int((servers / "hang.py.pid").read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)  # killed with its group, and reaped

    (servers / "hang.py").unlink()
    (servers / "noisy.py").write_text(
        "if __name__ == '__main__':\n    print('starting up')\n", encoding="utf-8"
    )
    with pytest.raises(GateError, match="not JSON-RPC"):
        derive_mcp(root, servers, e2e)
