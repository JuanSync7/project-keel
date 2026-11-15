"""
title: Integration — shipped documents say nothing true of one host or one moment
kind: tests
layer: n/a
summary: The shipped-doc drift gate. A shipped document is any Markdown file (or its `.md.jinja` twin) outside config/project.json `doc_drift.history_paths`; in its prose it names no concrete campaign or slice id (the `work_naming` mention grammar, any prefix), matches no `doc_drift.forbidden_phrases` pattern, names no loopback port that no non-Markdown file declares, cites only check letters in check_structure.CHECKS or check names a Python module stem or definition supplies. Python twins retain definitions after Jinja tags are removed with line numbers preserved, and unparseable source raises with its path. Check citations read inline code names and letters inside code spans and exempt fences within the shared scanner's container limits; a twin definition whose name a Jinja tag touches is not read; the check-name sentence in doc_drift.check_name_guide is held to each mark's side, effect and spacing. Code spans and fences are illustrations and are exempt from the prose rules, as check_Z treats them. The excluded-path rule instead reads every shipped text source, with no history, table or fence waiver, using Copier's own matcher for unconditional exclusions under docs/ only; other exclusions (Copier defaults, generated views and template-only tools) and conditional exclusions are outside its class. It exempts a whole test module only when its module-level pytest.mark.skipif uses the copier-absent guard and the _TEMPLATE_ONLY reason. NUL-containing files are counted as binary and skipped. The non-Markdown port scan decodes UTF-8 strictly and reports an invalid file with its byte offset, even when no port is requested or all requested ports were found. A history file's `.md.jinja` twin renders as the generated project's own history, so it carries no `- ` entry line of the untwinned file, and finding no such pair fails. Jinja sources are read without rendering answers. Every expected set is derived from the thing it describes, never typed here; a missing or malformed `doc_drift` or `work_naming` block fails, a scan over zero documents fails, and only the copier.yml-derived test skips, with a stated reason, in a generated project. Each rule has a fault-injection twin that plants one item and asserts exactly one finding. Not a writer: it reads the tree and writes only under pytest's tmp_path. A change opener is advisory in review_docs, and a test here proves present claims fail no gate scan.
"""

import ast
import bisect
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import pytest

import isolation_guard
import optional_deps
from bounded_cache import bounded

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
import exit_code_table  # noqa: E402
import review_docs  # noqa: E402
import traceability  # noqa: E402
from child_env import build_child_env  # noqa: E402
from scripts.bounded_match import match_spans  # noqa: E402
from test_e2e_coverage import EXEMPT_KEY  # noqa: E402

pytestmark = pytest.mark.integration

_BLOCK = "doc_drift"
_TEMPLATE_ONLY = "not a copier template — this is a generated project"
_TWIN_SUFFIX = ".jinja"
_DOC_SUFFIXES = (".md", ".md" + _TWIN_SUFFIX)
# A loopback URL's port. Raw text is scanned, fences and code spans included:
# a port a reader is told to open is a claim wherever it is written.
_LOOPBACK_PORT = re.compile(r"\b(?:localhost|127\.0\.0\.1):([0-9]{2,5})\b")
# A single capital names CHECKS; every longer identifier names Python code.
# Qualified attributes and keyword arguments belong to the library being used.
# The name after the prefix is read by _word, Python's identifier grammar, and
# _continues_name reads the character before it by the same grammar.
_CHECK_START = re.compile(r"check_")
_KEYWORD_ARGUMENT = re.compile(r"\s*=(?!=)")
_LETTER = r"[A-Z](?![\w'])"
_CHECK_PROSE = re.compile(
    r"\b[Cc]hecks?\s+(%s(?:(?:\s*[–-]\s*|\s+to\s+)%s)?"
    r"(?:(?:,\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+)%s"
    r"(?:(?:\s*[–-]\s*|\s+to\s+)%s)?)*)" % ((_LETTER,) * 4)
)
_CHECK_NAME_GUIDE = ("doc_drift", "check_name_guide")
# copier.yml's `_exclude` entries carry jinja conditionals; an entry with one
# is answer-driven, an entry without one never ships.
_JINJA_TAG = re.compile(r"\{%.*?%\}")
_DEF_GAP = re.compile(r"(?:[ \t\f]|\\\r?\n)+")
_PYTHON_JINJA_TAG = re.compile(r"\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\}", re.DOTALL)
# A definition's keyword and name token, matched from the node's column.
# The condition of one such entry's `{% if <condition> %}` tag.
_JINJA_IF = re.compile(r"\{%-?\s*if\s+(.*?)\s*-?%\}")
# One entry of the README's layout tree: a box-drawing branch, then a name
# with a trailing slash (a directory; files carry none).
_TREE_DIR = re.compile(r"^[├└]── (\S+)/")
# A waiver pragma as a checker's own module-level `re.compile` spells it in
# source: `#\s*<word>-ok`. Read over source text, so the `\s*` is literal.
_PRAGMA = re.compile(r"#\\s\*([a-z]+(?:-[a-z]+)*-ok)")
# The checkers whose module-level regexes may declare a pragma.
_CHECKER_GLOB = "scripts/check_*.py"
# check_practices.py runs a practice whose status starts with this; any other
# status is a way to switch one off, so it is a waiver.
_ACTIVE_STATUS = "on"
# The tables the two guides are read through, found by their columns so a
# heading can be reworded without blinding the gate.
_EXIT_TABLE = ("Script", "Exit")
_CHECKLIST_TABLE = ("Step", "Exit", "Recovery")
_EXCLUSION_TABLE = ("Path", "Arrives")
_PASSES_THROUGH = "passes through"
# The key whose prefixes exempt a document from this gate: a waiver too.
_HISTORY_KEY = "history_paths"
_HISTORY_PATH = (_BLOCK, _HISTORY_KEY)
_PHRASES_PATH = (_BLOCK, "forbidden_phrases")
# The child-process allowlist module and the names of its config block and of
# the tuple of keys it reads; every key there widens or narrows what a child
# inherits, so each is a lever the limits guide names.
_CHILD_ENV = "scripts/child_env.py"
_CHILD_ENV_NAMES = ("_BLOCK", "_BLOCK_KEYS")
# A checklist Step cell opening with this is a `_tasks` entry; any other row is
# a `_migrations` entry.
_TASK_MARK = "task:"


class DocDriftConfigError(AssertionError):
    """The gate cannot judge: the manifest or a block it reads is missing or
    malformed. Raised, never skipped."""


# --- config ---------------------------------------------------------------


def load_manifest(root):
    try:
        manifest = config_loader.read(str(root))
    except config_loader.ConfigError as exc:
        raise DocDriftConfigError(str(exc)) from None
    return manifest


def drift_policy(manifest: dict[str, Any]) -> dict[str, Any]:
    """The `doc_drift` keys this file reads, validated. The loader judges the
    block against its `KEYS` rows; a refusal, or a reason that is not a
    non-empty string, raises DocDriftConfigError naming the key, so a typo
    cannot fall back to nothing."""
    try:
        values = config_loader.resolve(
            manifest,
            config_loader.rows(_HISTORY_PATH, _PHRASES_PATH),
            config_loader.CONFIG_FILE,
            environ={},
            stream=io.StringIO(),
        )
    except config_loader.ConfigError as exc:
        raise DocDriftConfigError(str(exc)) from None
    compiled = []
    for pattern, reason in sorted(values[_PHRASES_PATH].items()):
        if not isinstance(reason, str) or not reason.strip():
            raise DocDriftConfigError(
                "config/project.json: `%s.forbidden_phrases` has an entry without "
                "a reason; correct each reason to a non-empty string" % _BLOCK
            )
        try:
            regex = config_loader.compile_pattern(
                pattern, "%s.forbidden_phrases" % _BLOCK, "config/project.json"
            )
        except config_loader.ConfigError as exc:
            raise DocDriftConfigError(str(exc)) from None
        compiled.append((regex, reason))
    return {_HISTORY_KEY: tuple(values[_HISTORY_PATH]), "forbidden_phrases": compiled}


def work_mention(manifest):
    """The `work_naming` mention regex: finds any campaign or slice id in prose,
    with or without a `<project>:` prefix."""
    policy, errs = cs.work_naming_policy(manifest)
    if policy is None:
        raise DocDriftConfigError("config/project.json: " + "; ".join(errs))
    return cs.id_grammar(policy)["mention"]


def _nonempty_str(block, key):
    value = block.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DocDriftConfigError(
            "config/project.json: `%s.%s` must be a non-empty string" % (_BLOCK, key)
        )
    return value


def entry_policy(manifest):
    """The `doc_drift` keys the entry-document, guide-audience, limits-guide
    and upgrade-guide rules read, validated the way `drift_policy` validates
    its own: a missing or mistyped key raises naming it."""
    block = manifest.get(_BLOCK)
    if not isinstance(block, dict):
        raise DocDriftConfigError(
            "config/project.json: `%s` is missing or not an object" % _BLOCK
        )
    one_hop = block.get("one_hop")
    if (
        not isinstance(one_hop, dict)
        or not one_hop
        or not all(
            isinstance(doc, str)
            and doc.strip()
            and isinstance(targets, list)
            and targets
            and all(isinstance(t, str) and t.strip() for t in targets)
            for doc, targets in one_hop.items()
        )
    ):
        raise DocDriftConfigError(
            "config/project.json: `%s.one_hop` must map each entry document to a "
            "non-empty list of the documents it links to" % _BLOCK
        )
    audiences = block.get("audiences")
    if (
        not isinstance(audiences, list)
        or not audiences
        or not all(isinstance(a, str) and a.strip() for a in audiences)
        or len(set(audiences)) != len(audiences)
    ):
        raise DocDriftConfigError(
            "config/project.json: `%s.audiences` must be a non-empty list of "
            "distinct names, in the order a cell lists them" % _BLOCK
        )
    policy = {"one_hop": {d: tuple(t) for d, t in sorted(one_hop.items())}}
    policy["audiences"] = tuple(audiences)
    for key in ("layout_heading", "roster", "limits_guide", "upgrade_guide"):
        policy[key] = _nonempty_str(block, key)
    policy["gate_target"] = _nonempty_str(block, "gate_target")
    policy["settings_reference"] = _nonempty_str(block, "settings_reference")
    policy["features_reference"] = _nonempty_str(block, "features_reference")
    return policy


# --- the documents --------------------------------------------------------


def _untwinned(relpath):
    return relpath.removesuffix(_TWIN_SUFFIX)


def leaked_history_findings(root, history_paths):
    """(findings, pairs judged) for every `.md.jinja` twin under a history
    prefix whose untwinned file exists: each `- ` entry line of the twin that
    is also a line of the untwinned file is a finding, because the twin
    renders as the generated project's own history and keel's entries are not
    that history."""
    findings, pairs = [], 0
    for dirpath, _dirs, files in cs.walk(str(root)):
        for name in files:
            if not name.endswith(".md" + _TWIN_SUFFIX):
                continue
            twin = os.path.join(dirpath, name)
            relpath = os.path.relpath(twin, str(root)).replace(os.sep, "/")
            source = os.path.join(str(root), _untwinned(relpath))
            if not _untwinned(relpath).startswith(history_paths):
                continue
            if not os.path.isfile(source):
                continue
            pairs += 1
            with open(source, encoding="utf-8") as fh:
                own = set(fh.read().splitlines())
            with open(twin, encoding="utf-8") as fh:
                for i, line in enumerate(fh.read().splitlines(), 1):
                    if line.startswith("- ") and line in own:
                        findings.append(
                            "%s:%d: carries the template's own history entry %r; "
                            "the generated project starts its history empty"
                            % (relpath, i, line)
                        )
    return findings, pairs


def shipped_docs(root, history_paths):
    """[(relpath, text)] for every shipped Markdown document under *root* and
    every `.md.jinja` twin, sorted. A path (twin suffix stripped) under a
    history prefix is history and is left out; a symlink is read under its
    target's name, as `cs._markdown_texts` does."""
    out = []
    for dirpath, _dirs, files in cs.walk(str(root)):
        for name in files:
            full = os.path.join(dirpath, name)
            if not name.endswith(_DOC_SUFFIXES) or os.path.islink(full):
                continue
            relpath = os.path.relpath(full, str(root)).replace(os.sep, "/")
            if _untwinned(relpath).startswith(history_paths):
                continue
            with open(full, encoding="utf-8") as fh:
                out.append((relpath, fh.read()))
    return sorted(out)


def _git_listed(root, *, untracked=True):
    """Files git would hand a commit: tracked plus, with *untracked*,
    untracked-and-unignored. None when *root* is not a git work tree. Ignored
    files are generated views (wiki/corpus.json, llms-full.txt) that copy
    Markdown text verbatim, so reading them would let a doc declare its own
    port."""
    if shutil.which("git") is None:
        return None
    env = build_child_env()
    probe = subprocess.run(
        review_docs.git_argv(str(root), "rev-parse", "--is-inside-work-tree"),
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=env,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return None
    which = (
        ["--cached", "--others", "--exclude-standard"] if untracked else ["--cached"]
    )
    listed = subprocess.run(
        review_docs.git_argv(str(root), "ls-files", "-z", *which),
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=True,
    )
    return sorted(p for p in listed.stdout.decode("utf-8").split("\0") if p)


def _non_markdown_files(root):
    listed = _git_listed(root)
    if listed is None:
        listed = []
        for dirpath, _dirs, files in cs.walk(str(root)):
            for name in files:
                full = os.path.join(dirpath, name)
                listed.append(os.path.relpath(full, str(root)).replace(os.sep, "/"))
    return [p for p in listed if not p.endswith(_DOC_SUFFIXES)]


def declared_ports(root, wanted):
    """Declared port strings and named UTF-8 findings in non-Markdown files.

    NUL-containing binaries follow shipped_sources' binary rule. Every text
    file is decoded strictly, even after all ports have been found, because
    discarding bytes can manufacture a declaration that the source never held.
    """
    found = set()
    findings = []
    pattern = (
        re.compile(
            r"(?<![0-9])(%s)(?![0-9])" % "|".join(sorted(map(re.escape, wanted)))
        )
        if wanted
        else None
    )
    for relpath in _non_markdown_files(root):
        full = Path(root) / relpath
        if full.is_symlink() or not full.is_file():
            continue
        try:
            data = full.read_bytes()
        except OSError:  # noqa: DROP001 -- an unreadable file holds no pattern to find
            continue
        if b"\0" in data:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            findings.append(
                "%s: byte offset %d: not UTF-8 (%s)" % (relpath, exc.start, exc.reason)
            )
            continue
        if pattern is not None:
            found.update(pattern.findall(text))
    return found, findings


# --- the rules ------------------------------------------------------------


@bounded(str(_ROOT))
def python_names(root):
    """Python module stems and function/class definitions, including twins.

    Jinja tags are removed from twins, preserving newlines so syntax errors
    name their source line. A definition whose name token has an expression
    or statement tag at its edge or inside it is not returned, since its
    rendered name is unknown; a comment tag renders to nothing, so removing
    it is the rendering. A name is returned as Python binds it (NFKC).
    Unparseable Python, twin or plain, is never skipped.
    """
    names = set()
    for dirpath, _dirs, files in cs.walk(str(root)):
        for name in files:
            stem = name.removesuffix(_TWIN_SUFFIX)
            full = Path(dirpath) / name
            if not stem.endswith(".py") or full.is_symlink():
                continue
            names.add(stem[:-3])
            source, cuts = full.read_text(encoding="utf-8"), set()
            if name.endswith(_TWIN_SUFFIX):
                source, cuts = _strip_jinja(source)
            tree = ast.parse(source, filename=str(full))
            starts = [0] + [n + 1 for n, c in enumerate(source) if c == "\n"]
            for node in ast.walk(tree):
                if not isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    continue
                token = _definition_token(source, starts, node)
                if token is None:
                    raise AssertionError(
                        "%s:%d: no definition token for %r"
                        % (full, node.lineno, node.name)
                    )
                if not any(token[0] <= cut <= token[1] for cut in cuts):
                    names.add(node.name)
    return names


def _definition_token(source, starts, node):
    """(start, end) of *node*'s name token in *source*, whose line *n* starts
    at offset ``starts[n - 1]``, or None when the text at its column is no
    definition naming it."""
    line_start = starts[node.lineno - 1]
    line_end = source.find("\n", line_start)
    line = source[line_start : None if line_end < 0 else line_end]
    # ast columns count UTF-8 bytes; the slices below count characters.
    column = len(line.encode("utf-8")[: node.col_offset].decode("utf-8"))
    start, end = _word(source, line_start + column)
    if source[start:end] == "async":
        start, end = _word(source, _past_gap(source, end))
    if source[start:end] not in ("def", "class"):
        return None
    start, end = _word(source, _past_gap(source, end))
    if unicodedata.normalize("NFKC", source[start:end]) != node.name:
        return None
    return start, end


def _past_gap(source, at):
    """The offset past the blanks and backslash continuations at *at*."""
    gap = _DEF_GAP.match(source, at)
    return gap.end() if gap else at


def _word(source, at):
    """(at, end) of the longest identifier in *source* that starts at *at*."""
    end = at
    # str.isidentifier is Python's own XID grammar, which a regex \w is not.
    while end < len(source) and source[at : end + 1].isidentifier():
        end += 1
    return at, end


def _continues_name(source, at):
    """Whether the character before *at* continues an identifier or is an
    attribute's dot, so a name starting at *at* is part of a longer one."""
    # A regex \w misses a combining mark and a middle dot, which Python's
    # XID_Continue grammar counts.
    return at > 0 and (source[at - 1] == "." or ("_" + source[at - 1]).isidentifier())


def _strip_jinja(source):
    """Source with Jinja tags removed, newlines kept, and the offsets in the
    result where an expression or statement tag was removed."""
    out, cuts, last = [], set(), 0
    for match in _PYTHON_JINJA_TAG.finditer(source):
        out += [source[last : match.start()], "\n" * match[0].count("\n")]
        if not match[0].startswith("{#"):
            cuts.add(sum(map(len, out)))
        last = match.end()
    return "".join(out) + source[last:], cuts


def _prose_letters(citation):
    letters = []
    for part in re.split(r",|\band\b|\bor\b", citation):
        ends = re.findall(r"[A-Z]", part)
        if len(ends) == 2:
            low, high = ends
            if low > high:
                letters.append(low + "–" + high)
            else:
                letters.extend(chr(c) for c in range(ord(low), ord(high) + 1))
        else:
            letters.extend(ends)
    return letters


def check_citation_findings(docs, letters, names):
    """Unknown check names with their document and line; fences are examples.

    Inline code cites checks as prose does: names, letters, lists and ranges
    are read inside code spans too. CHECKS decides whether a letter runs, even
    if a retired function remains defined in Python.
    """
    findings = []
    for relpath, text in docs:
        unfenced = "\n".join(cs._unfenced_lines(text))
        for match in _CHECK_START.finditer(unfenced):
            if _continues_name(unfenced, match.start()):
                continue
            start, end = _word(unfenced, match.start())
            if end == match.end() or _KEYWORD_ARGUMENT.match(unfenced, end):
                continue
            name = unicodedata.normalize("NFKC", unfenced[start:end])
            suffix = name[len("check_") :]
            is_letter = re.fullmatch(r"[A-Z]", suffix) is not None
            if is_letter and suffix not in letters:
                reason = "check_structure.CHECKS has no check " + suffix
            elif not is_letter and name not in names:
                reason = "no Python file is or defines " + name
            else:
                continue
            line_number = unfenced.count("\n", 0, match.start()) + 1
            findings.append(
                "%s:%d: cites %s, but %s -- name a check that exists"
                % (relpath, line_number, name, reason)
            )
        # Only the span delimiters are blanked, to spaces of the same width, so
        # `check Q` is read like prose and line numbers are kept.
        prose = cs._INLINE_CODE.sub(
            lambda m: " " * len(m[1]) + m[2] + " " * len(m[1]), unfenced
        )
        for match in _CHECK_PROSE.finditer(prose):
            unknown = [c for c in _prose_letters(match[1]) if c not in letters]
            if unknown:
                line_number = prose.count("\n", 0, match.start()) + 1
                findings.append(
                    "%s:%d: cites %s, but check_structure.CHECKS lacks %s -- "
                    "name a check that runs"
                    % (relpath, line_number, match[0], ", ".join(unknown))
                )
    return sorted(findings)


_paragraphs = cs.markdown_paragraphs
_blank_code_spans = cs.blank_code_spans
_WHITESPACE_RUN = re.compile(r"\s+")


def _scan_text(text: str) -> tuple[str, list[int]]:
    """A paragraph as the phrase scan reads it: code spans blanked, then every
    whitespace run one space, so a hard wrap or a doubled space cannot split a
    literal-space phrase; with, for each character of that text, its offset in
    *text*, so a finding still names the line the match is on."""
    blanked = _blank_code_spans(text)
    pieces: list[str] = []
    origin: list[int] = []
    last = 0
    for run in _WHITESPACE_RUN.finditer(blanked):
        pieces.append(blanked[last : run.start()] + " ")
        origin.extend(range(last, run.start()))
        origin.append(run.start())
        last = run.end()
    pieces.append(blanked[last:])
    origin.extend(range(last, len(blanked)))
    return "".join(pieces), origin


def _line_of(
    scanned: str, origin: list[int], span: tuple[int, int], starts: list[int]
) -> int:
    """The 0-based line, within its paragraph, of the first non-space
    character of the match at *span* in the scanned text. A pattern may open on
    the whitespace before its word, and in a joined paragraph that whitespace
    can be the previous line's break."""
    matched = scanned[span[0] : span[1]]
    first = span[0] + len(matched) - len(matched.lstrip())
    if not origin:
        return 0
    offset = origin[min(first, len(origin) - 1)]
    return bisect.bisect_right(starts, offset) - 1


def moment_and_host_findings(
    docs: list[tuple[str, str]],
    policy: dict[str, Any],
    mention: re.Pattern[str],
    port_root: Path,
    *,
    timeout: float | None = None,
) -> list[str]:
    """Findings for rule (a) over *docs*: a concrete work id or a forbidden
    phrase in prose, or a loopback port in raw text that no non-Markdown file
    under *port_root* declares. Each finding is `relpath:line: message`."""
    findings: list[str] = []
    ports: dict[str, list[tuple[str, int, str]]] = {}
    prose = []
    for relpath, text in docs:
        for i, line in enumerate(cs._unfenced_lines(text), 1):
            # A code span may wrap onto the next line, so the paragraph keeps
            # its code and blanks it joined, for the work id and the phrases.
            prose.append((relpath, i, line))
        for i, line in enumerate(text.split("\n"), 1):
            for m in _LOOPBACK_PORT.finditer(line):
                ports.setdefault(m.group(1), []).append((relpath, i, m.group(0)))
    paragraphs = [
        (relpath, first, starts, *_scan_text(text))
        for relpath, first, text, starts in _paragraphs(prose)
    ]
    for relpath, first, starts, scanned, origin in paragraphs:
        # The same blanked text as the phrase scan, so one definition of a code
        # span exempts both and a match is reported on the line it starts on.
        findings.extend(
            "%s:%d: names the work id %r in prose -- a slice id is history; "
            "say what is true now, or move the text under doc_drift."
            "history_paths"
            % (
                relpath,
                first + _line_of(scanned, origin, m.span(), starts),
                m.group(0),
            )
            for m in mention.finditer(scanned)
        )
    for regex, reason in policy["forbidden_phrases"]:
        # The bounded child enumerates every match, so no configured pattern
        # runs here. A paragraph holds many lines, so every match is a finding:
        # stopping at the first would hide a second report beside it.
        spans = match_spans(
            regex.pattern,
            "doc_drift.forbidden_phrases",
            [scanned for _path, _number, _starts, scanned, _origin in paragraphs],
            timeout=timeout,
        )
        for (relpath, first, starts, scanned, origin), hits in zip(
            paragraphs, spans, strict=True
        ):
            findings.extend(
                "%s:%d: %r -- %s"
                % (
                    relpath,
                    first + _line_of(scanned, origin, hit, starts),
                    " ".join(scanned[hit[0] : hit[1]].split()),
                    reason,
                )
                for hit in hits
            )
    declared, decode_findings = declared_ports(port_root, set(ports))
    findings.extend(decode_findings)
    for port in sorted(set(ports) - declared):
        for relpath, i, url in ports[port]:
            findings.append(
                "%s:%d: names %s, but no non-Markdown file declares port %s -- "
                "a port from one machine" % (relpath, i, url, port)
            )
    return sorted(findings)


def _unconditional_exclusions(root):
    """Read unconditional Copier patterns, or None outside the template."""
    copier_yml = Path(root) / "copier.yml"
    if not copier_yml.is_file():
        return None
    yaml = optional_deps.importorskip("yaml", extra="template")
    cfg = yaml.safe_load(copier_yml.read_text(encoding="utf-8"))
    entries = cfg.get("_exclude") if isinstance(cfg, dict) else None
    if not isinstance(entries, list) or not all(
        isinstance(e, str) and e.strip() for e in entries
    ):
        raise DocDriftConfigError("copier.yml: `_exclude` must list nonblank strings")
    return sorted(e for e in entries if "{%" not in e)


def never_shipped_docs(root):
    """Unconditional exclusions under docs/ only; None outside the template.

    Copier defaults, generated views, template-only tools and conditional
    exclusions are outside the citation gate; unreadable docs/ globs fail.
    """
    entries = _unconditional_exclusions(root)
    if entries is None:
        return None
    excluded = [e for e in entries if e.strip().lstrip("/").startswith("docs/")]
    if not excluded:
        raise DocDriftConfigError("copier.yml: zero unconditional docs/ exclusions")
    for entry in excluded:
        path = entry.strip().strip("/")
        if any(c in path for c in "*?[]\\") or ".." in Path(path).parts:
            raise DocDriftConfigError(
                "copier.yml: docs/ exclusion is not a readable path: %r" % entry
            )
    if not any((Path(root) / e.strip().strip("/")).is_dir() for e in excluded):
        raise DocDriftConfigError("copier.yml: zero directory exclusions under docs/")
    return excluded


def shipped_sources(
    root: Path, files: list[str] | None = None
) -> tuple[list[tuple[str, str]], int]:
    """Return shipped source texts and the number of NUL-containing binaries.

    Plain sources replaced by template twins do not ship; twins are read raw.
    """
    from test_copier_shipping import _matcher

    files = _git_listed(root) if files is None else files
    if files is None:
        raise DocDriftConfigError("cannot list shipped sources with git")
    excluded = _unconditional_exclusions(root)
    if excluded is None:
        raise DocDriftConfigError("copier.yml: cannot derive shipped sources")
    match = _matcher(excluded)
    sources = []
    binary_count = 0
    shipped_count = 0
    for path in files:
        destination = _untwinned(path)
        if match(destination) or (
            not path.endswith(_TWIN_SUFFIX) and path + _TWIN_SUFFIX in files
        ):
            continue
        data = (Path(root) / path).read_bytes()
        shipped_count += 1
        if b"\0" in data:
            binary_count += 1
            continue
        sources.append((path, data.decode("utf-8")))
    if not shipped_count:
        raise DocDriftConfigError("zero shipped files")
    return sources, binary_count


def _template_only_module(relpath, text):
    """Whether a test module has the copier-absent module skip marker."""
    if (
        not relpath.startswith("tests/")
        or not Path(relpath).name.startswith("test_")
        or not relpath.endswith(".py")
    ):
        return False
    tree = ast.parse(text, filename=relpath)
    bindings = {
        node.targets[0].id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }
    marker = bindings.get("pytestmark")
    markers = marker.elts if isinstance(marker, (ast.List, ast.Tuple)) else [marker]
    for mark in markers:
        if not isinstance(mark, ast.Call) or not mark.args:
            continue
        if ast.unparse(mark.func) != "pytest.mark.skipif":
            continue
        if ast.unparse(mark.args[0]) != "not (_ROOT / 'copier.yml').is_file()":
            continue
        reason = next((k.value for k in mark.keywords if k.arg == "reason"), None)
        if isinstance(reason, ast.Name) and reason.id == "_TEMPLATE_ONLY":
            reason = bindings.get(reason.id)
        if isinstance(reason, ast.Constant) and reason.value == _TEMPLATE_ONLY:
            return True
    return False


# Paths are read in raw source, including comments, tables and fences.
_SOURCE_PATH = re.compile(
    r"(?<![\w./-])(?:\.{1,2}/|/)?[\w.~*?\[\]+-]+"
    r"(?:/[\w.~*?\[\]+-]+)*/?"
)


def excluded_citation_findings(docs, excluded):
    """Find excluded paths at component boundaries in shipped source text."""
    from test_copier_shipping import _matcher

    match = _matcher(excluded)
    findings = []
    for relpath, text in docs:
        if _template_only_module(relpath, text):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            targets = set()
            for token in _SOURCE_PATH.finditer(line):
                path = token.group().rstrip(".")
                candidates = (
                    path.lstrip("/"),
                    posixpath.normpath(
                        posixpath.join(posixpath.dirname(relpath), path)
                    ),
                )
                for target in candidates:
                    if match(target) or match(target.rstrip("/") + "/"):
                        targets.add(target)
                        break
            findings.extend(
                "%s:%s: names %s, which copier excludes" % (relpath, number, target)
                for target in sorted(targets)
            )
    return findings


# --- rule (b): a newcomer reaches every guide, and the tree is true --------


def one_hop_findings(one_hop, texts, known):
    """*one_hop*: {entry doc: [targets]}; *texts*: {relpath: text} for every
    Markdown file; *known*: every Markdown path. An entry doc that is absent,
    a target that does not exist, or a target the doc does not name by link or
    path, is one finding each."""
    findings = []
    for doc, targets in sorted(one_hop.items()):
        if doc not in texts:
            findings.append("%s: the entry document does not exist" % doc)
            continue
        if not targets:
            findings.append("%s: names no one-hop target -- zero items" % doc)
        reached = cs._document_references(doc, texts[doc], known)
        for target in targets:
            if target not in known:
                findings.append("%s: one-hop target %s does not exist" % (doc, target))
            elif target not in reached:
                findings.append(
                    "%s: does not link to %s, so a newcomer cannot reach it in one "
                    "hop" % (doc, target)
                )
    return findings


def roster_reach_findings(roster, texts, known):
    """Every Markdown document beside *roster* (its directory's members) must be
    named from it, so the README's hop to the roster reaches each guide."""
    if roster not in texts:
        return ["%s: the roster does not exist" % roster]
    base = posixpath.dirname(roster)
    members = sorted(p for p in known if posixpath.dirname(p) == base and p != roster)
    if not members:
        return ["%s: its directory holds no other document -- zero items" % roster]
    reached = cs._document_references(roster, texts[roster], known)
    return [
        "%s: does not name %s, so no entry document reaches it" % (roster, m)
        for m in members
        if m not in reached
    ]


def layout_tree(text, heading):
    """The directory names in the first fenced block under `## <heading>`, or
    None when there is no such heading or no fence under it."""
    lines = text.split("\n")
    target = "## " + heading
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == target)
    except StopIteration:  # noqa: DROP001 -- None when the heading is absent, as documented
        return None
    names, fenced = [], False
    for line in lines[start + 1 :]:
        if line.startswith("```"):
            if fenced:
                return names
            fenced = True
            continue
        if not fenced and line.startswith("## "):
            return None
        if fenced:
            m = _TREE_DIR.match(line)
            if m:
                names.append(m.group(1))
    return names if fenced else None


def shipping_toplevel_dirs(root, manifest):
    """The top-level directories a reader of this tree meets: every taxonomy
    directory present, every `structure.extra_toplevel` name, and every
    top-level dot-directory git tracks (without a git work tree: every one
    present outside IGNORE_DIRS). An untracked dot-directory, such as an
    editor's settings, is local state and ships nowhere."""
    root = Path(root)
    extra = (manifest.get("structure") or {}).get("extra_toplevel")
    if not isinstance(extra, list):
        raise DocDriftConfigError(
            "config/project.json: `structure.extra_toplevel` is missing or not a list"
        )
    expected = {d for d in cs.TAXONOMY if (root / d).is_dir()} | set(extra)
    listed = _git_listed(root, untracked=False)
    if listed is None:
        dots = {
            p.name
            for p in root.iterdir()
            if p.name.startswith(".") and p.is_dir() and p.name not in cs.IGNORE_DIRS
        }
    else:
        dots = {p.split("/", 1)[0] for p in listed if p.startswith(".") and "/" in p}
    return expected | dots


def layout_findings(doc, text, heading, expected, root):
    """The layout tree under `## <heading>` in *doc* lists every *expected*
    directory, and every directory it lists exists under *root*."""
    listed = layout_tree(text, heading)
    if listed is None:
        return ["%s: no fenced tree under `## %s`" % (doc, heading)]
    if not listed:
        return ["%s: the tree under `## %s` lists no directory" % (doc, heading)]
    if not expected:
        return ["no shipping top-level directory derived -- zero items"]
    findings = [
        "%s: the layout tree omits %s/, which ships at the top level" % (doc, d)
        for d in sorted(set(expected) - set(listed))
    ]
    findings.extend(
        "%s: the layout tree lists %s/, which does not exist" % (doc, d)
        for d in listed
        if not (Path(root) / d).is_dir()
    )
    return findings


def audience_findings(roster, text, audiences):
    """The roster's `## What ships here` table carries an Audience column, and
    each row's cell is a non-empty comma-joined subset of *audiences*, in
    their order."""
    table = cs._roster_table(text)
    if not table or not table[0]:
        return ["%s: no `## What ships here` table" % roster]
    header, rows = table
    if "audience" not in header:
        return ["%s: the roster has no Audience column" % roster]
    col = header.index("audience")
    if not rows:
        return ["%s: the roster has no rows -- zero items" % roster]
    findings = []
    for row in rows:
        member = row[0] if row else "?"
        cell = row[col] if col < len(row) else ""
        names = [a.strip() for a in cell.split(",")] if cell.strip() else []
        order = [audiences.index(a) for a in names if a in audiences]
        if not names:
            findings.append("%s: %s names no audience" % (roster, member))
        elif len(order) != len(names) or order != sorted(set(order)):
            findings.append(
                "%s: %s names %r -- each audience must be one of %s, listed once "
                "and in that order" % (roster, member, cell, ", ".join(audiences))
            )
    return findings


# --- rule (c): the limits guide names every waiver and every exit code ------


def derived_waivers(root):
    """Every way this tree lets a project switch a rule off, read from the
    code and registry that grant it: a pragma a checker compiles at module
    level, a gate-runner policy key, the mypy kill switch, a dict-valued
    ruleset key in config/practices.json, a practice status that is not the
    active one, every key of the child-process allowlist's block, the
    history prefixes this gate exempts, the end-to-end gate's endpoint
    exemptions (tests/integration/test_e2e_coverage.py `EXEMPT_KEY`, by leaf),
    the two keys that excuse a requirement or a whole project from
    requirement traceability (scripts/traceability.py `GAPS_KEY` and
    `EMPTY_KEY`, by leaf), and the keys that let a test reach past the
    strictest isolation rule (tests/isolation_guard.py `WAIVERS`, whole: the
    leaf `exempt` is the end-to-end gate's too)."""
    root = Path(root)
    found = set()
    checkers = sorted(root.glob(_CHECKER_GLOB))
    if not checkers:
        raise DocDriftConfigError("no %s found -- zero items" % _CHECKER_GLOB)
    for path in checkers:
        source = path.read_text(encoding="utf-8")
        for node in ast.parse(source).body:
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "compile"
            ):
                found.update(
                    _PRAGMA.findall(ast.get_source_segment(source, node) or "")
                )
    found.update(cs._POLICY_KEYS)
    found.add(cs._OVERRIDE_KILL_SWITCH)
    found.update(child_env_keys(root))
    found.add("%s.%s" % (_BLOCK, _HISTORY_KEY))
    found.add(EXEMPT_KEY.rsplit(".", 1)[-1])
    for key in (traceability.GAPS_KEY, traceability.EMPTY_KEY):
        found.add(key.rsplit(".", 1)[-1])
    found.update(isolation_guard.WAIVERS)
    registry_path = root / "config" / "practices.json"
    if not registry_path.is_file():
        raise DocDriftConfigError("config/practices.json is missing")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    rulesets = registry.get("rulesets")
    practices = registry.get("practices")
    if not isinstance(rulesets, dict) or not isinstance(practices, list):
        raise DocDriftConfigError(
            "config/practices.json: `rulesets` or `practices` is missing or mistyped"
        )
    for tool, rules in sorted(rulesets.items()):
        if not isinstance(rules, dict):
            continue  # `_comment`: a string, not a tool
        found.update(
            "rulesets.%s.%s" % (tool, key)
            for key, value in rules.items()
            if isinstance(value, dict)
        )
    found.update(
        p["status"]
        for p in practices
        if isinstance(p, dict)
        and isinstance(p.get("status"), str)
        and not p["status"].startswith(_ACTIVE_STATUS)
    )
    return sorted(found)


def child_env_keys(root):
    """`<block>.<key>` for every key the child-process allowlist reads, from
    the module's own `_BLOCK` and `_BLOCK_KEYS` literals. A module without
    them is a finding, never an empty set."""
    path = Path(root) / _CHILD_ENV
    if not path.is_file():
        raise DocDriftConfigError("%s is missing" % _CHILD_ENV)
    values = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in _CHILD_ENV_NAMES:
                values[target.id] = ast.literal_eval(node.value)
    block, keys = (values.get(n) for n in _CHILD_ENV_NAMES)
    if not isinstance(block, str) or not isinstance(keys, tuple) or not keys:
        raise DocDriftConfigError(
            "%s: no %s literal -- zero items"
            % (_CHILD_ENV, " or ".join(_CHILD_ENV_NAMES))
        )
    return sorted("%s.%s" % (block, k) for k in keys if not k.startswith("_"))


def _backticked(text):
    """Every inline-code span outside fenced code, whole and split on
    whitespace, so `rm -rf src/frontend` names `src/frontend`."""
    spans = set()
    for line in cs._unfenced_lines(text):
        for span in cs._BACKTICKED.findall(line):
            spans.add(span.strip())
            spans.update(span.split())
    return spans


# The header of the limits guide's waiver table, whose first cell names a waiver.
_WAIVER_HEADER = "| Waiver |"


def waiver_rows(text):
    """The code spans of the first cell of each row of the waiver table: a
    waiver named only in prose elsewhere in the guide has no row."""
    named = set()
    in_table = False
    for line in cs._unfenced_lines(text):
        if line.startswith(_WAIVER_HEADER):
            in_table = True
            continue
        if in_table and not line.startswith("|"):
            in_table = False
        if in_table:
            named.update(_backticked(line.split("|")[1]))
    return named


def waiver_findings(guide, text, waivers):
    if not waivers:
        return ["no waiver derived -- zero items"]
    named = waiver_rows(text)
    if not named:
        return ["%s: holds no `%s` table" % (guide, _WAIVER_HEADER)]
    return [
        "%s: the waiver table has no row for `%s`" % (guide, w)
        for w in waivers
        if w not in named
    ]


def exit_codes(path, root=_ROOT):
    """(codes, passes_through) for the script at *path*, by the ExitCode enum
    of *root*. scripts/exit_code_table.py is the one reader of what a script
    can exit with; this gate and the generated table share it."""
    return exit_code_table.exit_codes(path, root)


def gate_scripts(root, target):
    """Every `*.py` a recipe reachable from make *target* runs. A makefile
    the reader cannot read fully is a finding, never a smaller set."""
    try:
        return exit_code_table.gate_scripts(root, target)
    except exit_code_table.TableError as exc:
        raise DocDriftConfigError(str(exc)) from exc


def _code_cell_findings(guide, cell, script, codes, passes):
    missing = [
        str(c) for c in sorted(codes) if not re.search(r"(?<!\d)%d(?!\d)" % c, cell)
    ]
    findings = []
    if missing:
        findings.append(
            "%s: the row for `%s` omits exit code(s) %s"
            % (guide, script, ", ".join(missing))
        )
    if passes and _PASSES_THROUGH not in cell.lower():
        findings.append(
            "%s: the row for `%s` does not say it %s a child's code"
            % (guide, script, _PASSES_THROUGH)
        )
    return findings


def _rows_naming(table, column, item):
    header, rows = table
    col = header.index(column.lower())
    return [
        row
        for row in rows
        if col < len(row)
        and item in {s.strip() for s in cs._BACKTICKED.findall(row[col])}
    ]


def exit_code_findings(guide, text, root, scripts):
    """Each gate script has a row in the guide's Script/Exit table whose Exit
    cell names every code the script can exit with."""
    if not scripts:
        return ["no gate script derived -- zero items"]
    table = cs._pipe_table(text, _EXIT_TABLE)
    if table is None:
        return ["%s: no table with the columns %s" % (guide, ", ".join(_EXIT_TABLE))]
    exit_col = table[0].index("exit")
    findings = []
    for script in scripts:
        path = Path(root) / script
        if not path.is_file():
            findings.append(
                "%s: the gate runs %s, which does not exist" % (guide, script)
            )
            continue
        codes, passes = exit_codes(path, root)
        if not codes and not passes:
            findings.append("%s: no exit code derived -- zero items" % script)
            continue
        rows = _rows_naming(table, "Script", script)
        if not rows:
            findings.append("%s: no exit-code row names `%s`" % (guide, script))
        for row in rows:
            cell = row[exit_col] if exit_col < len(row) else ""
            findings.extend(_code_cell_findings(guide, cell, script, codes, passes))
    return findings


# --- rule (d): the upgrade guide names what copier does to a project --------


def _command_items(command):
    """(scripts, removed paths) one `_tasks`/`_migrations` command names: a
    list command runs its `.py`; a string command is `rm` over the paths after
    its flags (yaml folds a multi-line string, so whitespace splits it)."""
    if isinstance(command, dict):
        command = command.get("command")
    if isinstance(command, list):
        scripts = [c for c in command if isinstance(c, str) and c.endswith(".py")]
        if scripts:
            return scripts, []
    if isinstance(command, str):
        words = command.split()
        if words and words[0] == "rm":
            return [], [w for w in words[1:] if not w.startswith("-")]
    raise DocDriftConfigError(
        "copier.yml: a task or migration this gate cannot read: %r" % (command,)
    )


def _exclude_condition(entry):
    """The jinja condition an `_exclude` entry ships under: "" for an entry
    with no tag, the `if` conditions joined by ` and ` otherwise. An entry
    carrying a tag that is not an `if`/`endif` cannot be read, so it raises."""
    tags = _JINJA_TAG.findall(entry)
    conditions = [m.group(1) for m in map(_JINJA_IF.match, tags) if m]
    other = [t for t in tags if not _JINJA_IF.match(t) and "endif" not in t]
    if other or (tags and not conditions):
        raise DocDriftConfigError(
            "copier.yml: an `_exclude` entry this gate cannot read: %r" % (entry,)
        )
    return " and ".join(conditions)


def copier_inventory(root):
    """{"scripts", "checklist", "steps", "exclusions", "exclude_conditions",
    "migration_conditions", "min_copier_version"} read from copier.yml, or
    None when *root* is not the template: the scripts the tasks and
    migrations run, those plus every path a migration removes, every task
    then every migration as (kind, items) in the order copier runs them,
    every `_exclude` entry with its jinja stripped, that entry mapped to its
    raw jinja condition ("" when it never ships), every path a migration
    removes mapped to its raw `when` text, and the copier version floor."""
    copier_yml = Path(root) / "copier.yml"
    if not copier_yml.is_file():
        return None
    yaml = optional_deps.importorskip("yaml", extra="template")
    cfg = yaml.safe_load(copier_yml.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise DocDriftConfigError("copier.yml: top level is not a mapping")
    scripts, removed, steps, migration_conditions = [], [], [], {}
    # Every migration here is an `after` one, and copier runs `_tasks` while
    # it renders, before them: so tasks first, then migrations in file order.
    for key, kind in (("_tasks", "task"), ("_migrations", "migration")):
        entries = cfg.get(key)
        if not isinstance(entries, list) or not entries:
            raise DocDriftConfigError("copier.yml: `%s` is missing or empty" % key)
        for entry in entries:
            ran, gone = _command_items(entry)
            scripts.extend(ran)
            removed.extend(gone)
            steps.append((kind, tuple(ran + gone)))
            when = entry.get("when", "") if isinstance(entry, dict) else ""
            for path in gone:
                migration_conditions[path] = str(when)
    excludes = cfg.get("_exclude")
    if not isinstance(excludes, list) or not excludes:
        raise DocDriftConfigError("copier.yml: `_exclude` is missing or empty")
    exclusions = [_JINJA_TAG.sub("", e).strip() for e in excludes if isinstance(e, str)]
    exclude_conditions = {
        _JINJA_TAG.sub("", e).strip(): _exclude_condition(e)
        for e in excludes
        if isinstance(e, str) and _JINJA_TAG.sub("", e).strip()
    }
    floor = cfg.get("_min_copier_version")
    if not isinstance(floor, str) or not floor.strip():
        raise DocDriftConfigError("copier.yml: `_min_copier_version` is missing")
    return {
        "scripts": scripts,
        "checklist": scripts + removed,
        "steps": steps,
        "exclusions": [e for e in exclusions if e],
        "exclude_conditions": exclude_conditions,
        "migration_conditions": migration_conditions,
        "min_copier_version": floor.strip(),
    }


def _span_names(cell):
    """Every inline-code span in *cell*, whole and split on whitespace."""
    named = set()
    for span in cs._BACKTICKED.findall(cell):
        named.add(span.strip())
        named.update(span.split())
    return named


def checklist_findings(guide, table, root, inventory):
    """Each task and each migration has a row of its own kind (a task row's
    Step cell opens with `task:`) whose Step cell names every item it runs or
    removes, the rows follow copier's order, and a script's row carries its
    exit codes. A row stands for one entry only, so a script that is both a
    task and a migration needs two rows."""
    header, rows = table
    step_col = header.index(_CHECKLIST_TABLE[0].lower())
    exit_col = header.index("exit")
    parsed = [
        (
            _TASK_MARK if row[step_col].lower().startswith(_TASK_MARK) else "",
            _span_names(row[step_col]),
            row,
        )
        for row in rows
        if step_col < len(row)
    ]
    findings, used, previous = [], set(), -1
    for kind, items in inventory["steps"]:
        mark = _TASK_MARK if kind == "task" else ""
        match = next(
            (
                i
                for i, (m, named, _row) in enumerate(parsed)
                if i not in used and m == mark and set(items) <= named
            ),
            None,
        )
        label = " ".join("`%s`" % i for i in items)
        if match is None:
            findings.append("%s: no %s row names %s" % (guide, kind, label))
            continue
        used.add(match)
        # Against the step copier runs just before, not every earlier one, so
        # one misplaced row is one finding.
        if match < previous:
            findings.append(
                "%s: the %s row for %s is out of copier's order -- it sits above "
                "the row of the step copier runs just before it" % (guide, kind, label)
            )
        previous = match
        row = parsed[match][2]
        cell = row[exit_col] if exit_col < len(row) else ""
        for item in items:
            if item not in inventory["scripts"]:
                continue
            codes, passes = exit_codes(Path(root) / item, root)
            if not codes and not passes:
                findings.append("%s: no exit code derived -- zero items" % item)
            findings.extend(_code_cell_findings(guide, cell, item, codes, passes))
    return findings


def upgrade_findings(guide, text, root, inventory):
    """Every task and migration has its own row, in copier's order, in the
    guide's checklist table (see checklist_findings); every `_exclude` entry
    has a row in its exclusion table; the guide states the copier version
    floor."""
    findings = []
    floor = inventory["min_copier_version"]
    if not re.search(r"(?<![\d.])%s(?![\d.])" % re.escape(floor), text):
        findings.append(
            "%s: does not state the copier version floor %s that copier.yml "
            "`_min_copier_version` sets" % (guide, floor)
        )
    for columns, items, kind in (
        (_CHECKLIST_TABLE, inventory["checklist"], "task or migration"),
        (_EXCLUSION_TABLE, inventory["exclusions"], "exclusion"),
    ):
        if not items:
            findings.append("copier.yml: no %s derived -- zero items" % kind)
            continue
        table = cs._pipe_table(text, columns)
        if table is None:
            findings.append(
                "%s: no table with the columns %s" % (guide, ", ".join(columns))
            )
            continue
        if columns is _CHECKLIST_TABLE:
            findings.extend(checklist_findings(guide, table, root, inventory))
            continue
        named = set()
        for row in table[1]:
            for cell in row:
                named |= _span_names(cell)
        findings.extend(
            "%s: no %s row names `%s`" % (guide, kind, item)
            for item in sorted(set(items))
            if item not in named
        )
    return findings


# --- fixtures -------------------------------------------------------------


@pytest.fixture(scope="module")
def manifest():
    return load_manifest(_ROOT)


@pytest.fixture(scope="module")
def policy(manifest):
    return drift_policy(manifest)


@pytest.fixture(scope="module")
def entry(manifest):
    return entry_policy(manifest)


@pytest.fixture(scope="module")
def markdown():
    """{relpath: text} for every Markdown file, history included: an entry
    document may link into docs/adr/."""
    found = dict(cs._markdown_texts(str(_ROOT)))
    assert found, "no Markdown file found -- a scan over zero docs"
    return found


@pytest.fixture(scope="module")
def docs(policy):
    found = shipped_docs(_ROOT, policy["history_paths"])
    assert found, "no shipped Markdown document found -- a scan over zero docs"
    return found


# --- rule (a): no moment, no host ------------------------------------------


def test_no_shipped_doc_cites_a_work_id_or_a_host_specific_string(
    manifest, policy, docs
):
    findings = moment_and_host_findings(docs, policy, work_mention(manifest), _ROOT)
    names = python_names(_ROOT)
    assert "check_structure" in names, "no Python check module found"
    letters = {letter for letter, _fn in cs.CHECKS}
    assert letters, "check_structure.CHECKS is empty"
    findings.extend(check_citation_findings(docs, letters, names))
    assert not findings, "\n".join(findings)


@pytest.mark.parametrize(
    "citation, cited",
    [
        ("`check_Q`", "check_Q"),
        ("check Q", "Q"),
        ("checks A, F and Q", "Q"),
        ("checks P–U", "Q"),
        ("checks P-U", "Q"),
        ("checks P to U", "Q"),
        ("checks A,\nF and Q", "Q"),
        ("checks P\nto U", "Q"),
        ("`check_nonesuch`", "check_nonesuch"),
        ("`check_AB`", "check_AB"),
        ("`check_A1`", "check_A1"),
        ("`check_A_helper`", "check_A_helper"),
        ("`check_Hx`", "check_Hx"),
        ("`check_VERSION`", "check_VERSION"),
    ],
)
def test_a_document_citing_a_check_that_does_not_exist_fails(
    tmp_path, manifest, policy, monkeypatch, citation, cited
):
    # A retired check may still have a definition; CHECKS decides whether it runs.
    monkeypatch.setattr(cs, "CHECKS", [(k, f) for k, f in cs.CHECKS if k != "Q"])
    for filename in ("guide.md", "guide.md.jinja"):
        doc = tmp_path / filename
        doc.write_text("The gate uses %s.\n" % citation, encoding="utf-8")
        with pytest.raises(AssertionError) as failure:
            test_no_shipped_doc_cites_a_work_id_or_a_host_specific_string(
                manifest, policy, shipped_docs(tmp_path, policy["history_paths"])
            )
        assert filename in str(failure.value) and cited in str(failure.value)
        doc.unlink()


@pytest.mark.parametrize(
    "text, citations",
    [
        (
            "``` check_missing ```\nUses check_other.",
            [(1, "check_missing"), (2, "check_other")],
        ),
        ("```markdown\n```python\ncheck_missing\n```", []),
        (
            "~~~~text\n~~~\n~~~~ trailing\ncheck_missing\n~~~~\ncheck_other",
            [(6, "check_other")],
        ),
        ("- item\n\n  ```\n  check_missing\n  ```\ncheck_other", [(6, "check_other")]),
        ("> ```\n> check_missing\n> ```", []),
        ("- item\n\n    ```\n    check_missing\n    ```", []),
        (
            "- item\n2. ```\n   check_missing\n   ```\ncheck_other",
            [(5, "check_other")],
        ),
        (
            "> quote\n-\n  <?x\n  check_missing\ncheck_other",
            [(5, "check_other")],
        ),
        (
            "Prose <!-- hidden\ncheck_missing\n--> more\ncheck_other",
            [(4, "check_other")],
        ),
    ],
)
def test_check_citations_follow_shared_fence_boundaries(text, citations):
    findings = check_citation_findings([("guide.md", text)], set(), set())
    assert len(findings) == len(citations), findings
    for finding, (line, name) in zip(findings, citations, strict=True):
        assert finding.startswith("guide.md:%d: cites %s," % (line, name)), finding


@pytest.mark.parametrize("start", ["<details>", "<x-panel>"])
def test_check_citations_follow_blank_line_html_boundaries(start):
    documents = [("guide.md", start + "\ncheck_missing\n```\n\ncheck_other")]
    assert len(documents) == 1
    findings = check_citation_findings(documents, set(), set())
    assert len(findings) == 1, findings
    assert findings[0].startswith("guide.md:5: cites check_other,"), findings


def _assert_check_name_sentence(text):
    sentences = re.findall(r"^For check-name citations, (.+)$", text, re.MULTILINE)
    assert len(sentences) == 1, "the guide must state one check-name sentence"
    claims = re.findall(
        r"`([^`]+)` (before|after) a name (is read|is not read) "
        r"(with or without spaces|only without spaces)",
        sentences[0],
    )
    assert len(claims) == 3 and {c[0] for c in claims} == {".", "=", "=="}
    names = python_names(_ROOT)
    assert "check_structure" in names, "no Python check module found"
    letters = {letter for letter, _fn in cs.CHECKS}
    assert letters, "check_structure.CHECKS is empty"
    for mark, side, effect, spaces in claims:
        for gap in ("", " "):
            token = (
                "module%s%s%scheck_missing_probe" % (gap, mark, gap)
                if side == "before"
                else "check_missing_probe%s%s%s1" % (gap, mark, gap)
            )
            expected = effect == "is read"
            if gap and spaces == "only without spaces":
                expected = not expected
            actual = bool(
                check_citation_findings([("probe.md", token)], letters, names)
            )
            assert actual == expected, "guide mark %r disagrees on %r" % (mark, token)


def test_python_check_names_and_citation_exemptions(tmp_path):
    (tmp_path / "check_module.py").write_text(
        "def check_A1(): pass\n"
        "async def check_Hx(): pass\n"
        "class check_VERSION:\n"
        "    def check_A_helper(self): pass\n",
        encoding="utf-8",
    )
    (tmp_path / "check_twin.py.jinja").write_text(
        "{% if\n enabled %}def check_unrendered(): pass{% endif %}\n"
        "{# a\n comment #}\n"
        "{{ preamble }}def check_twin_expression(): pass\n"
        "class check_twin_class:\n"
        "    async def check_twin_async(self): return '{{ value }}'\n"
        "def check_fused{{ suffix }}(): pass\n"
        "def {{ prefix }}check_prefixed(): pass\n"
        "def check_{{ middle }}ghost(): pass\n"
        "def f{{ suffix }}(): pass\n"
        "def check_kept{# a note #}(): pass\n",
        encoding="utf-8",
    )
    # Python binds the NFKC form: U+212A KELVIN SIGN spells check_Kelvin.
    (tmp_path / "check_kelvin.py").write_text(
        "def check_\u212aelvin(): pass\n", encoding="utf-8"
    )
    # A combining mark and a middle dot continue an identifier, and a
    # backslash continues the line, as Python's own grammar has it.
    (tmp_path / "check_grammar.py").write_text(
        "def check_e\u0301(): pass\n"
        "def check_l\u00b7l(): pass\n"
        "def \\\n check_cont(): pass\n"
        "async \\\n  def \\\n    check_async_cont(): pass\n",
        encoding="utf-8",
    )
    names = python_names(tmp_path)
    # An expression or statement tag at the edge of or inside a name leaves
    # that name unknown, never a guess; a comment renders to nothing.
    assert not names & {"check_fused", "check_prefixed", "check_ghost", "f"}
    assert {"check_kept", "check_Kelvin"} <= names
    assert {
        unicodedata.normalize("NFKC", "check_e\u0301"),
        "check_l\u00b7l",
        "check_cont",
        "check_async_cont",
    } <= names
    # A citation is read by the same grammar, and compared as Python binds it.
    assert not check_citation_findings(
        [("guide.md", "`check_e\u0301` and `check_l\u00b7l`")], set(), names
    )
    # A name that only ends in check_ is not a citation of one, however its
    # earlier part is spelt: a combining mark and a middle dot continue it.
    assert not check_citation_findings(
        [("guide.md", "`e\u0301check_missing` and `l\u00b7check_missing`")],
        set(),
        names,
    )
    assert {
        "check_module",
        "check_twin",
        "check_A1",
        "check_Hx",
        "check_VERSION",
        "check_A_helper",
        "check_unrendered",
        "check_twin_class",
        "check_twin_async",
        "check_twin_expression",
    } <= names
    assert not check_citation_findings(
        [("guide.md", "`%s`" % "`, `".join(sorted(names)))], set(), names
    )
    examples = (
        "module.check_missing; module.check_Q; check_missing=False; "
        "f(check_missing = 1); check_Q=1; a check WARN\n"
        "```python\ncheck_missing\ncheck Q\n```\n"
        "~~~text\ncheck_missing\n~~~\n"
    )
    assert check_citation_findings([("guide.md", examples)], set(), names) == []
    findings = check_citation_findings(
        [("guide.md", "check_missing == 1\nchecks U–P")], set(), names
    )
    assert len(findings) == 2 and all("guide.md:" in f for f in findings)
    spans = check_citation_findings(
        [("guide.md", "`check Q`\n`checks P-U`")], set(), names
    )
    assert [f.split(":")[:2] for f in spans] == [["guide.md", "1"], ["guide.md", "2"]]
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "check_broken.py").write_text("def (", encoding="utf-8")
    with pytest.raises(SyntaxError):
        python_names(broken)


def test_an_unparseable_python_twin_fails_closed_with_path_and_line(tmp_path):
    twin = tmp_path / "check_broken.py.jinja"
    twin.write_text(
        "{% if enabled %}\n{# note #}\ndef (\n{% endif %}\n", encoding="utf-8"
    )
    with pytest.raises(SyntaxError) as failure:
        python_names(tmp_path)
    assert failure.value.filename == str(twin)
    assert failure.value.lineno == 3


@pytest.mark.parametrize("mark", [".", "=", "=="])
def test_the_check_name_sentence_fails_when_a_mark_effect_is_inverted(manifest, mark):
    values = config_loader.resolve(
        manifest, config_loader.rows(_CHECK_NAME_GUIDE), config_loader.CONFIG_FILE
    )
    text = (_ROOT / values[_CHECK_NAME_GUIDE]).read_text(encoding="utf-8")
    _assert_check_name_sentence(text)
    pattern = r"(`%s` (?:before|after) a name )(is not read|is read)" % re.escape(mark)
    inverted, count = re.subn(
        pattern,
        lambda m: m[1] + ("is read" if m[2] == "is not read" else "is not read"),
        text,
    )
    assert count == 1
    with pytest.raises(AssertionError, match="guide mark"):
        _assert_check_name_sentence(inverted)


@pytest.mark.parametrize("mark", [".", "=", "=="])
def test_the_check_name_sentence_fails_when_spacing_is_inverted(manifest, mark):
    values = config_loader.resolve(
        manifest, config_loader.rows(_CHECK_NAME_GUIDE), config_loader.CONFIG_FILE
    )
    text = (_ROOT / values[_CHECK_NAME_GUIDE]).read_text(encoding="utf-8")
    _assert_check_name_sentence(text)
    pattern = (
        r"(`%s` (?:before|after) a name (?:is not read|is read) )"
        r"(with or without spaces|only without spaces)"
    ) % re.escape(mark)
    inverted, count = re.subn(
        pattern,
        lambda m: (
            m[1]
            + (
                "only without spaces"
                if m[2] == "with or without spaces"
                else "with or without spaces"
            )
        ),
        text,
    )
    assert count == 1
    with pytest.raises(AssertionError, match="guide mark"):
        _assert_check_name_sentence(inverted)


@pytest.mark.parametrize(
    "planted, exempt",
    [
        ("Delivered by CMP-1.S1 last week.", "Delivered by `CMP-1.S1` last week."),
        ("This works on this host only.", "```\nThis works on this host only.\n```"),
        # A port is read in raw text, so a fence does not exempt it; a
        # non-Markdown file that declares it does.
        ("Open http://127.0.0.1:59999 to see it.", None),
    ],
    ids=["work-id", "host-phrase", "undeclared-port"],
)
def test_a_planted_work_id_host_phrase_or_undeclared_port_reds_the_scan(
    tmp_path, manifest, policy, docs, planted, exempt
):
    mention = work_mention(manifest)
    source = dict(docs)["CONTRIBUTING.md"]
    doc = tmp_path / "CONTRIBUTING.md"

    def scan(text):
        # The copy is judged on its own tree: tmp_path holds no git work tree
        # and no non-Markdown file, so the port lookup walks it and finds none.
        doc.write_text(text, encoding="utf-8")
        found = shipped_docs(tmp_path, policy["history_paths"])
        return moment_and_host_findings(found, policy, mention, tmp_path)

    assert scan(source) == [], "the unplanted copy must be clean"
    findings = scan(source + "\n" + planted + "\n")
    assert len(findings) == 1, findings
    assert findings[0].startswith("CONTRIBUTING.md:"), findings
    if exempt is not None:
        assert scan(source + "\n" + exempt + "\n") == []
    else:
        port = _LOOPBACK_PORT.search(planted).group(1)
        (tmp_path / "serve.py").write_text("PORT = %s\n" % port, encoding="utf-8")
        assert scan(source + "\n" + planted + "\n") == []


def _planted_slice_id(manifest):
    """A concrete slice id built from the `work_naming` slice_id template."""
    return manifest["work_naming"]["slice_id"].replace("<n>", "1").replace("<m>", "1")


@pytest.mark.parametrize(
    "lines, expected",
    [
        # The span wraps across two lines: the id is code on both, no finding.
        (["Delivered as `see", "{id} here` today."], []),
        # Prose between two wrapped spans: the backticks on the middle line are
        # not a span, so the id is prose and is found on the middle line.
        (["Text `a", "b` then {id} then `c", "d` end."], [2]),
        # The id on the line after a wrapped span closes: the offset map must
        # name that line, not the line the span opened on.
        (["Text `a", "b` closes.", "Then {id} follows."], [3]),
        # An id fully on one line, outside any span, is found as before.
        (["Plain {id} prose."], [1]),
    ],
    ids=["id-in-wrapped-span", "id-between-spans", "id-after-span", "id-one-line"],
)
def test_the_work_id_scan_reads_code_spans_on_the_joined_paragraph(
    tmp_path, manifest, policy, lines, expected
):
    mention = work_mention(manifest)
    ident = _planted_slice_id(manifest)
    # A lead paragraph moves each case off line 1: a finding numbered from its
    # paragraph rather than its file then names the wrong line and fails.
    lead = ["Lead paragraph.", ""]
    text = "\n".join(line.replace("{id}", ident) for line in lead + lines) + "\n"
    findings = moment_and_host_findings([("GUIDE.md", text)], policy, mention, tmp_path)
    reds = [f for f in findings if "work id" in f]
    assert [int(f.split(":")[1]) for f in reds] == [n + len(lead) for n in expected], (
        findings
    )


_BLOCK_CASES = [
    # A stray backtick ends the block's own line and another follows the id on
    # the next line: joined, the pair would blank the id and the phrase.
    (["# T`", "Body {id}` here."], [2]),
    (["Title`", "=====", "Body {id}` here."], [3]),
    (["Title`", "-----", "Body {id}` here."], [3]),
    (["| a | b` |", "Body {id}` here."], [2]),
    # A thematic break ends the paragraph above it, so an opener there does
    # not pair with a backtick below it.
    (["Text `a", "***", "Body {id}` here."], [3]),
    (["Text `a", "___", "Body {id}` here."], [3]),
    (["- item `a", "---", "Body {id}` here."], [3]),
    # A quote opens a paragraph after a plain one; an unquoted line after a
    # quote is a lazy continuation, so a span wraps across the two.
    (["Text `a", "> Body {id}` here."], [2]),
    (["> Quote `a", "lazy {id}` b"], []),
    # A list item keeps its continuation lines, so a span may wrap inside it.
    (["- item `a", "  {id}` b"], []),
    (["- item `a", "  b` then {id}"], [2]),
    # A block opens 0 to 3 columns past the content column of the item it sits
    # in, so at the third level a break, an item or a heading at 4 spaces ends
    # the paragraph above it.
    (["- o", "  - i `a", "    ***", "    Body {id}` here."], [4]),
    (["- o", "  - i `a", "    - Body {id}` here."], [3]),
    (["- o", "  - i `a", "    # Body {id}` here."], [3]),
    # A deeper quote under a quote opens a paragraph of its own.
    (["> Quote `a", "> > Body {id}` here."], [2]),
    # Four columns past the content column of a top-level item is a
    # continuation line; so is a tab, which counts as four columns.
    (["- item `a", "    {id}` b"], []),
    (["Text `a", "\t***", "Body {id}` here."], []),
    # After a blank line, a column-0 paragraph closes the nested items above
    # it, so a 4-space `- x` in it is a continuation line, not an item.
    (["- o", "  - i", "    - j", "", "Top `a", "    - x` {id} `y"], [6]),
    # An item's content column follows its marker's width and gap: five or
    # more spaces after `10.` count as one, so its column is 4; after `-` it
    # is 2; and a tab after the marker runs to the next multiple of 4 columns
    # of the line.
    (["10.      o `a", "      - Body {id}` here."], [2]),
    (["-     o `a", "      - x` {id} `y"], [2]),
    (["-\to `a", "        - x` {id} `y"], [2]),
    # A quote's content may sit up to 3 spaces past its mark, so `>  >` is a
    # deeper quote; a list inside a quote keeps its columns line to line.
    (["> Quote `a", ">  > Body {id}` here."], [2]),
    (["> - o", ">   - i `a", ">     - Body {id}` here."], [3]),
    # An unquoted line under a quote sits outside the quote's items, so a
    # 4-space `- x` there is a lazy continuation, not a nested item.
    (["> - o `a", "    - x` {id} `y"], [2]),
    (["> - o", ">   - i `a", "    - x` {id} `y"], [3]),
    # A tab after a quote mark counts to the next multiple of 4 columns of the
    # line, and the mark takes one of them as its optional space.
    (["> t `a", ">\t  > x` {id} `y"], [2]),
    (["> Quote `a", "> \t> Body {id}` here."], [2]),
    (["> t", ">\t- Body `b", ">       - {id}` x"], [3]),
    # An unquoted line that is no lazy continuation closes the quote and its
    # items, so a 5-space `- x` under the paragraph after it continues it.
    (["> - o", "  # H", "  text `b", "     - x` {id} `y"], [4]),
    # A quote inside a list item keeps the item's column: the break at that
    # column ends the quote (a break is never lazy) and opens inside the item.
    (["10. o", "    > q `a", "    ***", "    Body {id}` here."], [4]),
    (["10. o", "    > - q `a", "    ***", "    Body {id}` here."], [4]),
    (["10. o", "    > q `a", "    > r {id}` b"], []),
    # A line 4 or more columns past its container's column, after a blank
    # line, is indented code: a block of its own that the first line under 4
    # columns past the container closes, so its backtick pairs with nothing.
    (["p", "", "    code `a", "Body {id}` here."], [4]),
    (["- o", "", "      code `a", "  Body {id}` here."], [4]),
    # A blank line keeps the items open, so the paragraph after it sits in
    # its item; a lazy line keeps the open items, so a sub-item after it opens
    # inside them.
    (["- o", "", "    p `a", "  {id}` b"], []),
    (["- o", "  - i `a", "lazy", "    - x {id}` y"], [4]),
    # Under a paragraph that holds text the same line is a continuation, in an
    # item as at the top level.
    (["Text `a", "    {id}` b"], []),
    (["- o `a", "      {id}` b"], []),
    # A blank quoted line ends the quoted paragraph, so the unquoted line
    # after it is no lazy continuation and its items are closed.
    (["> q", ">", "text `a", "> more {id}` b"], [4]),
    (["> - o", ">", "  text", "> p `a", ">     - x {id}` y"], []),
    # A setext underline needs a paragraph line with text above it: after a
    # blank line `===` is text, so the 4-space line after it continues it and
    # its backtick pairs with the one before the id.
    (["Lead.", "", "===", "    a `b", "c` {id} `d"], [5]),
    # A line that opens two containers (`- - o`, `1. - o`, `> - - o`) leaves
    # the innermost item's content column in force: the 6-space line after the
    # blank is a paragraph of the inner item, not indented code of the outer.
    (["- - o", "", "      a `", "    c` {id} `"], [4]),
    (["1. - o", "", "       a `", "     c` {id} `"], [4]),
    (["> - - o", ">", ">       a `", ">     c` {id} `"], [4]),
    # An item that holds a heading or a break is closed after it: the line
    # after it is no lazy continuation, so the 4-space line is plain text
    # under a paragraph, not an item.
    (["- # H", "x `", "    - y` {id} `"], [3]),
    (["- ***", "x `", "    - y` {id} `"], [3]),
    # Only an ordered item numbered 1 and holding text may interrupt a
    # paragraph; `10.` and an empty `*` are text of it.
    (["x `", "10. y` {id} `"], [2]),
    (["x `", "* ", "y` {id} `"], [3]),
    (["x `", "1. y` {id} `"], []),
    # A blank line keeps indented code open, so a span wraps across it.
    (["p", "", "    code `a", "", "    more` {id} `y"], [5]),
    # An unquoted line does not continue a quote's indented code: it is a
    # block of its own, so the backtick before it pairs with nothing after.
    (["> p", ">", ">     code `a", "      x` {id} `y"], []),
    # A quote mark 4 or more columns in is text, not a quote: it is indented
    # code, so the line under it is a paragraph of its own.
    (["> a", ">", "    > b `", "c` {id} `"], []),
    # A marker after a quote mark opens an item in that quote, which a
    # paragraph above does not limit: `10.` here is an item, and its nested
    # item and its quote close the paragraphs they follow.
    (["x", "> 10. y `", ">     - z` {id} `"], []),
    (["> x `", "10. y` {id} `"], []),
    (["- > q `", "  > r` {id} `"], [2]),
    # A marker takes the columns up to its content column and the rest of the
    # line keeps its own: five or more spaces after it leave indented code, so
    # its backtick pairs with nothing and the id in it is read; one to four
    # spaces leave item text, so the span wraps onto the next line. A tab
    # counts to the next multiple of 4 columns of the line.
    (["-      `{id}", "  2. `"], [1]),
    (["-     `{id}", "  2. `"], [1]),
    (["-    `{id}", "     2. `"], []),
    (["- `{id}", "  2. `"], []),
    (["-\t\t`{id}", "  2. `"], [1]),
    (["-\t`{id}", "    2. `"], []),
    # An empty item holds no text, so a line indented under it is no
    # continuation: at 4 columns past the item it is indented code.
    (["-  ", "      `{id}", "z `"], [2]),
    # A setext underline closes the paragraph it sits under inside an item,
    # but a line outside the paragraph's containers is lazy text: it never
    # underlines, so the span wraps across it.
    (["- y `a", "  ===", "  b {id}` c"], [3]),
    (["- y `a", "  ---", "  b {id}` c"], [3]),
    (["> y `a", "===", "b {id}` c"], []),
    (["- y `a", "      ===", "  b {id}` c"], []),
]
_BLOCK_IDS = [
    "atx-heading",
    "setext-equals",
    "setext-dashes",
    "table-row",
    "thematic-break-stars",
    "thematic-break-underscores",
    "thematic-break-after-item",
    "quote-after-text",
    "quote-lazy-continuation",
    "list-item-wrapped-span",
    "list-item-id-after-span",
    "third-level-thematic-break",
    "third-level-list-item",
    "third-level-heading",
    "quote-under-quote",
    "item-four-space-continuation",
    "tab-before-break-continues",
    "blank-closes-nested-items",
    "wide-ordered-marker",
    "wide-gap-counts-one",
    "tab-after-marker",
    "spaced-quote-under-quote",
    "list-inside-quote",
    "lazy-line-under-quoted-item",
    "lazy-line-under-nested-quoted-item",
    "tab-after-quote-mark",
    "tab-between-quote-marks",
    "tab-before-quoted-item",
    "unquoted-block-closes-quote",
    "quote-in-item-then-break",
    "list-in-quote-in-item-then-break",
    "quote-in-item-continues",
    "indented-code-after-blank",
    "indented-code-in-item",
    "blank-keeps-item-open",
    "lazy-line-keeps-items",
    "four-spaces-after-text-continues",
    "six-spaces-in-item-continues",
    "blank-quoted-line-ends-lazy",
    "blank-quoted-line-closes-items",
    "underline-after-blank-is-text",
    "two-markers-one-line",
    "ordered-then-bullet-one-line",
    "two-markers-in-quote",
    "item-heading-closes-item",
    "item-break-closes-item",
    "numbered-ten-continues-paragraph",
    "empty-item-continues-paragraph",
    "numbered-one-interrupts",
    "blank-keeps-indented-code-open",
    "unquoted-line-ends-quoted-code",
    "quote-mark-four-columns-in-is-code",
    "item-in-fresh-quote-may-be-ten",
    "unmatched-quote-leaves-ten-an-item",
    "quote-inside-item",
    "six-spaces-after-marker-is-code",
    "five-spaces-after-marker-is-code",
    "four-spaces-after-marker-is-text",
    "one-space-after-marker-is-text",
    "two-tabs-after-marker-is-code",
    "one-tab-after-marker-is-text",
    "empty-item-holds-no-text",
    "underline-closes-item-paragraph",
    "dashes-underline-closes-item-paragraph",
    "lazy-equals-is-not-an-underline",
    "four-columns-in-equals-is-not-an-underline",
]


@pytest.mark.parametrize("lines, expected", _BLOCK_CASES, ids=_BLOCK_IDS)
def test_a_heading_setext_title_or_table_row_ends_its_paragraph_for_the_work_id_scan(
    tmp_path, manifest, policy, lines, expected
):
    mention = work_mention(manifest)
    ident = _planted_slice_id(manifest)
    lead = ["Lead paragraph.", ""]
    text = "\n".join(line.replace("{id}", ident) for line in lead + lines) + "\n"
    findings = moment_and_host_findings([("GUIDE.md", text)], policy, mention, tmp_path)
    reds = [f for f in findings if "work id" in f]
    assert [int(f.split(":")[1]) for f in reds] == [n + len(lead) for n in expected], (
        findings
    )


@pytest.mark.parametrize(
    "lines, expected",
    [
        (["# T`", "Works on this host` only."], [2]),
        (["Title`", "=====", "Works on this host` only."], [3]),
        (["| a | b` |", "Works on this host` only."], [2]),
        (["- item `a", "  on this host` b"], []),
        (["Text `a", "***", "Works on this host` only."], [3]),
        (["Text `a", "> Works on this host` only."], [2]),
        (["- o", "  - i `a", "    ***", "    Works on this host` only."], [4]),
        (["p", "", "    code `a", "Works on this host` only."], [4]),
    ],
    ids=[
        "atx-heading",
        "setext",
        "table-row",
        "list-item-wrapped-span",
        "thematic-break",
        "quote-after-text",
        "third-level-thematic-break",
        "indented-code",
    ],
)
def test_a_block_line_does_not_pair_its_backtick_with_the_next_line_for_the_phrase_scan(
    tmp_path, manifest, policy, lines, expected
):
    mention = work_mention(manifest)
    lead = ["Lead paragraph.", ""]
    text = "\n".join(lead + lines) + "\n"
    findings = moment_and_host_findings([("GUIDE.md", text)], policy, mention, tmp_path)
    reds = [f for f in findings if "on this host" in f]
    assert [int(f.split(":")[1]) for f in reds] == [n + len(lead) for n in expected], (
        findings
    )


def test_a_quote_mark_is_dropped_only_from_the_start_of_a_line():
    # A `>` later in a line is text: dropping it would change the prose the
    # scans and the corpus read.
    assert [p[2] for p in _paragraphs([("G.md", 3, "a -> b <x> c")])] == [
        "a -> b <x> c"
    ]
    assert [p[2] for p in _paragraphs([("G.md", 3, "> > a -> b")])] == ["a -> b"]


# A report of a change names the moment it describes, so it is history. Each
# planted form pairs with a fragment of the manifest reason that refuses it.
# test_copier_generation.py plants this same list in a generated project, so a
# form added here is one its own gate must refuse too.
REPORT_FORMS = [
    ("The loader now uses a stricter reader.", "temporal implementation claim"),
    ("Now reads the manifest first.", "temporal implementation claim"),
    ("Since the rewrite the gate no longer accepts blank paths.", "temporal negative"),
    ("No longer rejects a blank path.", "temporal negative"),
    ("The key was renamed to timeout.", "passive modification report"),
    ("Was moved from the old file.", "passive modification report"),
    ("The flag has been renamed to timeout.", "passive modification report"),
    ("Has been moved from the old file.", "passive modification report"),
    ("The flag is no longer used.", "temporal negative"),
    ("IS NO LONGER USED by the gate.", "temporal negative"),
    ("The job now runs the gate first.", "temporal implementation claim"),
    ("NOW RUNS the gate first.", "temporal implementation claim"),
]


@pytest.mark.parametrize(
    "planted, reason",
    REPORT_FORMS,
    ids=[
        "now-lower",
        "now-upper",
        "no-longer-mid",
        "no-longer-upper",
        "renamed",
        "moved",
        "has-been-renamed",
        "has-been-moved-upper",
        "no-longer-used",
        "no-longer-used-upper",
        "now-runs",
        "now-runs-upper",
    ],
)
def test_a_planted_report_of_a_change_reds_the_scan_with_path_line_and_reason(
    tmp_path, manifest, policy, docs, planted, reason
):
    assert policy["forbidden_phrases"], "a scan with no phrase judges nothing"
    mention = work_mention(manifest)
    source = dict(docs)["CONTRIBUTING.md"]
    assert source.strip(), "the planted guide must be non-empty"
    doc = tmp_path / "CONTRIBUTING.md"

    def scan(text):
        doc.write_text(text, encoding="utf-8")
        found = shipped_docs(tmp_path, policy["history_paths"])
        assert found, "a pass over zero documents is a failure"
        return moment_and_host_findings(found, policy, mention, tmp_path)

    assert scan(source) == [], "the unplanted copy must be clean"
    text = source + "\n" + planted
    line = len(text.split("\n"))
    findings = scan(text + "\n")
    assert len(findings) == 1, findings
    assert findings[0].startswith("CONTRIBUTING.md:%d:" % line), findings
    assert reason in findings[0], findings
    for exempt in (
        "`%s`" % planted,
        "```\n%s\n```" % planted,
        "~~~\n%s\n~~~" % planted,
    ):
        assert scan(source + "\n" + exempt + "\n") == [], exempt
    history = tmp_path / "docs" / "design"
    history.mkdir(parents=True)
    (history / "plan.md").write_text(planted + "\n", encoding="utf-8")
    assert scan(source) == [], "a history document may report a change"


@pytest.mark.parametrize(
    "planted, reason",
    [
        ("The loader now\nuses a stricter reader.", "temporal implementation"),
        ("The loader NOW\n  USES a stricter reader.", "temporal implementation"),
        ("The gate no\nlonger accepts blanks.", "temporal negative"),
        ("The flag is no longer\nused.", "temporal negative"),
        ("The key has been\nrenamed to timeout.", "passive modification"),
        ("The job now\nruns the gate.", "temporal implementation"),
        ("- The job now\n  runs the gate.", "temporal implementation"),
        ("> The job now\n> runs the gate.", "temporal implementation"),
    ],
    ids=[
        "now-uses",
        "now-uses-upper-indented",
        "no-longer-accepts",
        "no-longer-used",
        "has-been-renamed",
        "now-runs",
        "list-item",
        "quote",
    ],
)
def test_a_report_hard_wrapped_across_two_lines_reds_at_its_first_line(
    tmp_path, manifest, policy, docs, planted, reason
):
    """The scan reads each paragraph with its line breaks joined, so where a
    hard wrap falls cannot hide a report; the finding names the line the
    match starts on."""
    source = dict(docs)["CONTRIBUTING.md"]
    first = len(source.split("\n")) + 1
    doc = tmp_path / "CONTRIBUTING.md"

    def scan(text):
        doc.write_text(text, encoding="utf-8")
        found = shipped_docs(tmp_path, policy["history_paths"])
        assert found, "a pass over zero documents is a failure"
        return moment_and_host_findings(found, policy, work_mention(manifest), tmp_path)

    assert scan(source) == [], "the unplanted copy must be clean"
    findings = scan(source + "\n" + planted + "\n")
    assert len(findings) == 1, findings
    assert findings[0].startswith("CONTRIBUTING.md:%d:" % first), findings
    assert reason in findings[0], findings
    assert "\n" not in findings[0], "a finding is one line"
    fenced = scan(source + "\n```\n" + planted + "\n```\n")
    assert fenced == [], "a fence is an illustration"


def _scan_planted(tmp_path, manifest, policy, docs, planted):
    """Findings for the shipped CONTRIBUTING.md with *planted* appended, after
    proving the unplanted copy is clean; also the line the plant starts on."""
    source = dict(docs)["CONTRIBUTING.md"]
    doc = tmp_path / "CONTRIBUTING.md"

    def scan(text):
        doc.write_text(text, encoding="utf-8")
        found = shipped_docs(tmp_path, policy["history_paths"])
        assert found, "a pass over zero documents is a failure"
        return moment_and_host_findings(found, policy, work_mention(manifest), tmp_path)

    assert scan(source) == [], "the unplanted copy must be clean"
    return scan(source + "\n" + planted + "\n"), len(source.split("\n")) + 1


@pytest.mark.parametrize(
    "planted, first_line_offset",
    [
        ("The agent runs on this\nhost only.", 0),
        ("The agent runs on\n  this   host only.", 0),
        ("The agent runs\non\nthis\nhost only.", 1),
        ("Look at this\nhost's disk.", 0),
    ],
    ids=["one-wrap", "indent-and-doubled-space", "wrap-every-word", "apostrophe"],
)
def test_a_literal_space_phrase_split_by_a_hard_wrap_reds_at_its_first_word(
    tmp_path, manifest, policy, docs, planted, first_line_offset
):
    """A configured phrase with a literal space is matched over the paragraph
    with each whitespace run read as one space, and the finding names the line
    the phrase starts on, not the line it ends on."""
    findings, first = _scan_planted(tmp_path, manifest, policy, docs, planted)
    assert len(findings) == 1, findings
    assert findings[0].startswith("CONTRIBUTING.md:%d:" % (first + first_line_offset))
    assert "a claim about one machine" in findings[0], findings
    assert "\n" not in findings[0], "a finding is one line"


@pytest.mark.parametrize(
    "planted",
    [
        "Quote `the loader now\nuses a reader` here.",
        "Quote `the loader now\n  uses a reader` and `a\nsecond` span.",
        "Quote ``the loader ` now\nuses a reader`` here.",
        "Quote `on this\nhost` here.",
        "`the loader now\nuses a reader`",
    ],
    ids=["one-span", "two-spans", "double-backtick", "phrase-in-span", "whole-line"],
)
def test_a_report_quoted_in_a_code_span_wrapped_across_lines_is_exempt(
    tmp_path, manifest, policy, docs, planted
):
    """Code spans are illustrations, as the line scan treated them, even where
    the span wraps."""
    findings, _first = _scan_planted(tmp_path, manifest, policy, docs, planted)
    assert findings == [], findings


@pytest.mark.parametrize(
    "planted, count",
    [
        ("A `span` is fine; the loader now\nuses a reader.", 1),
        ("A `a\nb` span, then the loader now\nuses a reader.", 1),
        ("A stray ` then the loader now\nuses it.", 1),
        ("A `` pair `\nthe loader now\nuses it.", 1),
        ("An escaped \\`tick the loader now\nuses it\\`.", 1),
        ("`x` the loader now\nuses `y` and the gate no\nlonger accepts z.", 2),
        ("Use `C:\\` then the loader now\nuses a reader, see `z`.", 1),
        ("A trailing `\\` is fine.\nThe loader now uses a reader, see `z`.", 1),
    ],
    ids=[
        "span-before",
        "wrapped-span-before",
        "unmatched-opener",
        "unequal-runs",
        "escaped-ticks",
        "two-reports-around-spans",
        "backslash-ends-span",
        "lone-backslash-span",
    ],
)
def test_a_real_wrapped_report_beside_code_spans_still_reds(
    tmp_path, manifest, policy, docs, planted, count
):
    findings, _first = _scan_planted(tmp_path, manifest, policy, docs, planted)
    assert len(findings) == count, findings


@pytest.mark.parametrize(
    "text, blanked",
    [
        ("a `b` c", "a     c"),
        ("a `b\nc` d", "a   \n   d"),
        ("a ``b ` c`` d", "a" + " " * 11 + "d"),
        ("a `b`` c", "a `b`` c"),
        ("a \\`b` c", "a \\`b` c"),
        ("a \\``b`` c", "a \\``b`` c"),
        ("a `C:\\` b `y`", "a " + " " * 5 + " b " + " " * 3),
    ],
    ids=[
        "one",
        "wrapped",
        "longer-run-inside",
        "unequal",
        "escaped",
        "half-escaped",
        "backslash-inside-span",
    ],
)
def test_blank_code_spans_follows_the_commonmark_run_rule(text, blanked):
    assert _blank_code_spans(text) == blanked
    assert len(_blank_code_spans(text)) == len(text), "offsets must not move"


@pytest.mark.parametrize(
    "text",
    [
        "A widget that is now\n\nUses are listed below.",
        "The step now\n## Uses of the gate",
        "The step now\n- uses nothing here",
        "A cell reads now\n| uses | x |",
    ],
    ids=["blank-line", "heading", "list-item", "table-row"],
)
def test_a_paragraph_break_between_two_words_is_not_a_hard_wrap(
    tmp_path, manifest, policy, docs, text
):
    """Joining stops at a blank line, heading, list item, table row or fence."""
    doc = tmp_path / "CONTRIBUTING.md"
    doc.write_text(dict(docs)["CONTRIBUTING.md"] + "\n" + text + "\n", encoding="utf-8")
    found = shipped_docs(tmp_path, policy["history_paths"])
    assert (
        moment_and_host_findings(found, policy, work_mention(manifest), tmp_path) == []
    )


def test_every_report_in_one_paragraph_is_a_finding_at_its_own_line(
    tmp_path, manifest, policy, docs
):
    """One paragraph may hold several reports that one expression refuses, so
    each match is a finding, not only the paragraph's first."""
    source = dict(docs)["CONTRIBUTING.md"]
    first = len(source.split("\n")) + 1
    doc = tmp_path / "CONTRIBUTING.md"
    doc.write_text(
        source + "\n" + "\n".join(form for form, _ in REPORT_FORMS) + "\n",
        encoding="utf-8",
    )
    found = shipped_docs(tmp_path, policy["history_paths"])
    assert found, "a pass over zero documents is a failure"
    findings = moment_and_host_findings(found, policy, work_mention(manifest), tmp_path)
    assert len(findings) == len(REPORT_FORMS), findings
    for offset, (form, reason) in enumerate(REPORT_FORMS):
        where = "CONTRIBUTING.md:%d:" % (first + offset)
        hit = [f for f in findings if f.startswith(where)]
        assert len(hit) == 1 and reason in hit[0], (form, findings)


def test_a_match_opening_on_a_line_break_is_reported_at_its_word(
    tmp_path, manifest, policy, docs
):
    """A home-directory pattern opens on the whitespace before the path; when a
    wrap puts the path at a line start, the finding names the path's line, not
    the line the break ends."""
    source = dict(docs)["CONTRIBUTING.md"]
    path_line = len(source.split("\n")) + 2
    doc = tmp_path / "CONTRIBUTING.md"
    doc.write_text(source + "\nSee\n/home/someone/notes for it.\n", encoding="utf-8")
    found = shipped_docs(tmp_path, policy["history_paths"])
    assert found, "a pass over zero documents is a failure"
    findings = moment_and_host_findings(found, policy, work_mention(manifest), tmp_path)
    assert len(findings) == 1, findings
    assert findings[0].startswith("CONTRIBUTING.md:%d:" % path_line), findings
    assert "home-directory" in findings[0], findings


def test_the_patterns_are_data_two_synthetic_policies_give_two_verdicts(tmp_path):
    def policy_for(pattern):
        return drift_policy(
            {
                "doc_drift": {
                    "history_paths": ["history/"],
                    "forbidden_phrases": {pattern: "a synthetic reason"},
                }
            }
        )

    found = [("guide.md", "A widget sits beside a gadget.\n")]
    never = re.compile("never")
    widget = moment_and_host_findings(found, policy_for(r"\bwidget\b"), never, tmp_path)
    gadget = moment_and_host_findings(found, policy_for(r"\bgadget\b"), never, tmp_path)
    assert [f.split(" -- ")[0] for f in widget] == ["guide.md:1: 'widget'"], widget
    assert [f.split(" -- ")[0] for f in gadget] == ["guide.md:1: 'gadget'"], gadget


@pytest.mark.parametrize(
    "path, phrase",
    [
        ("docs/reference/settings.md", "no longer reads"),
        ("docs/guides/limits-and-troubleshooting.md", "nothing was changed"),
    ],
    ids=["settings", "limits"],
)
def test_a_real_present_claim_in_the_corpus_stays_accepted(
    manifest, policy, path, phrase
):
    text = (_ROOT / path).read_text(encoding="utf-8")
    prose = "\n".join(cs._prose_lines(text))
    assert phrase in prose, "the present claim must sit in prose, not a span"
    found = [(path, text)]
    assert moment_and_host_findings(found, policy, work_mention(manifest), _ROOT) == []


@bounded(str(_ROOT))
def _answer_sets(root: str) -> list[dict[str, Any]]:
    """Every answer set copier.yml's validators allow, from the list
    `test_reference_drift` judges the twin under (imported at call time: that
    module imports this one). Many sets, so they are derived once."""
    import test_reference_drift as reference

    return reference.answer_sets(reference.copier_questions(Path(root)))


def _twin_phrases(template: Any, answers: dict[str, Any]) -> dict[str, str]:
    """The `doc_drift.forbidden_phrases` map of the manifest twin *template*
    (compiled once: compiling dominates a render) as copier renders it under
    *answers*, parsed.

    A substring search of the source would credit an entry kept only in a
    `{# #}` comment or an `{% if %}` block, which the render lacks; the
    render is what a generated project reads. Raises on a name the answers
    leave undefined (StrictUndefined) and on a render that is not JSON."""
    rendered = json.loads(template.render(**answers))
    return dict(rendered[_BLOCK]["forbidden_phrases"])


def _twin_phrase_findings(source: str, entries: list[tuple[Any, str]]) -> list[str]:
    """Differences between keel's `forbidden_phrases` and the twin's render
    under every answer set, both directions: an entry the render lacks or
    words differently, and an entry the render holds that keel does not. A
    finding says in how many answer sets it holds, because an entry kept in an
    answer-dependent block is missing from only some."""
    ours = {regex.pattern: reason for regex, reason in entries}
    import test_reference_drift as reference

    sets = _answer_sets(str(_ROOT))
    assert sets, "a parity check over zero answer sets proves nothing"
    template = reference._jinja().from_string(source)
    counts: dict[str, int] = {}
    for answers in sets:
        theirs = _twin_phrases(template, answers)
        found = [
            "twin lacks or rewords %r" % p
            for p in sorted(ours)
            if theirs.get(p) != ours[p]
        ]
        found += ["twin adds %r" % p for p in sorted(set(theirs) - set(ours))]
        for finding in found:
            counts[finding] = counts.get(finding, 0) + 1
    return [
        "%s under %d of %d answer sets" % (finding, count, len(sets))
        for finding, count in sorted(counts.items())
    ]


def _default_only_test() -> str:
    """A Jinja test, on a scalar question, that holds under the question
    defaults and fails under some other answer set."""
    import test_reference_drift as reference

    questions = reference.copier_questions(_ROOT)
    defaults = reference.complete_answers(questions, {})
    sets = _answer_sets(str(_ROOT))
    for name, value in defaults.items():
        if isinstance(value, (bool, str)) and any(a[name] != value for a in sets):
            return "%s == %s" % (name, json.dumps(value))
    raise AssertionError("no scalar question has an answer other than its default")


def test_every_forbidden_phrase_ships_in_both_manifest_twins(policy):
    """A generated project refuses what keel refuses: the parsed render of the
    `.jinja` twin, under every answer set, holds exactly the
    `forbidden_phrases` keel reads, pattern and reason, in both directions.
    The expected set is the policy itself."""
    twin = _ROOT / "config" / "project.json.jinja"
    if not twin.is_file():
        pytest.skip(_TEMPLATE_ONLY)
    entries = policy["forbidden_phrases"]
    assert entries, "a parity check over zero phrases proves nothing"
    found = _twin_phrase_findings(twin.read_text(encoding="utf-8"), entries)
    assert found == [], "config/project.json.jinja renders %s" % found


def _manifest_paths(ours: Any, theirs: Any, path: str = "") -> set[str]:
    """Return differing JSON Pointer paths; maps recurse and lists stay whole."""
    if isinstance(ours, dict) and isinstance(theirs, dict):
        found = set()
        for key in sorted(ours.keys() | theirs.keys()):
            child = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key not in ours or key not in theirs:
                found.add(child)
            else:
                found.update(_manifest_paths(ours[key], theirs[key], child))
        return found
    return {path} if type(ours) is not type(theirs) or ours != theirs else set()


def _manifest_twin_findings(source: str, manifest: dict[str, Any]) -> list[str]:
    """Compare every rendered manifest, with exact, non-stale path exemptions."""
    import test_reference_drift as reference

    key = ("template", "manifest_differences")
    allowed = config_loader.resolve(
        manifest, config_loader.rows(key), config_loader.CONFIG_FILE
    )[key]
    for path, reason in allowed.items():
        assert path.startswith("/") and isinstance(reason, str) and reason.strip(), (
            "template.manifest_differences: %r needs a JSON Pointer and reason" % path
        )
    sets = _answer_sets(str(_ROOT))
    assert sets, "a parity check over zero answer sets proves nothing"
    template = reference._jinja().from_string(source)
    counts: dict[str, int] = {}
    for answers in sets:
        rendered = json.loads(template.render(**answers))
        if rendered.get("name") == answers["project_slug"]:
            rendered["name"] = manifest["name"]
        for path in _manifest_paths(manifest, rendered):
            counts[path] = counts.get(path, 0) + 1
    return [
        "%s differs under %d of %d answer sets" % (path, count, len(sets))
        for path, count in sorted(counts.items())
        if path not in allowed
    ] + [
        "%s is a stale exemption: differs under 0 of %d answer sets" % (path, len(sets))
        for path in sorted(set(allowed) - counts.keys())
    ]


def test_every_manifest_leaf_ships_in_both_manifest_twins(manifest):
    """Every generated manifest matches keel except at reasoned template paths."""
    twin = _ROOT / "config" / "project.json.jinja"
    if not twin.is_file():
        pytest.skip(_TEMPLATE_ONLY)
    found = _manifest_twin_findings(twin.read_text(encoding="utf-8"), manifest)
    assert found == [], "config/project.json.jinja renders %s" % found


@pytest.mark.parametrize(
    "plant",
    [
        "comment",
        "if-false",
        "extra-entry",
        "reworded",
        "answer-dependent-if",
    ],
)
def test_a_twin_entry_outside_the_render_reds_the_parity_check(policy, plant):
    """Each fault is invisible to a substring search of the source and red to
    the render: an entry kept only in a Jinja comment or a false block, an
    entry only the twin holds, an entry whose reason the twin rewords, and an
    entry kept in a block that holds under the question defaults only."""
    twin = _ROOT / "config" / "project.json.jinja"
    if not twin.is_file():
        pytest.skip(_TEMPLATE_ONLY)
    entries = policy["forbidden_phrases"]
    source = twin.read_text(encoding="utf-8")
    assert _twin_phrase_findings(source, entries) == [], "the unplanted twin is clean"
    regex, reason = entries[-1]
    line = "%s: %s" % (json.dumps(regex.pattern), json.dumps(reason))
    assert source.count(line) == 1, "the planted line must be in the twin once"
    # The comma that joins the last entry to the one before it moves with it,
    # so the planted twin still renders as JSON.
    joined = re.search(r",\s*" + re.escape(line), source)
    assert joined, "the last entry must follow another"
    held = joined.group(0)
    if plant == "comment":
        bad = source.replace(held, "{# " + held + " #}")
    elif plant == "if-false":
        bad = source.replace(held, "{% if false %}" + held + "{% endif %}")
    elif plant == "extra-entry":
        bad = source.replace(held, held + ', "(?i)\\\\bplanted\\\\b": "r"')
    elif plant == "answer-dependent-if":
        bad = source.replace(
            held, "{% if " + _default_only_test() + " %}" + held + "{% endif %}"
        )
    else:
        bad = source.replace(
            line, "%s: %s" % (json.dumps(regex.pattern), json.dumps(reason + " x"))
        )
    assert bad != source, "the plant must change the twin"
    found = _twin_phrase_findings(bad, entries)
    assert len(found) == 1, found


def test_the_policy_is_read_through_the_loader(monkeypatch):
    resolved = []
    read = []
    real_resolve = config_loader.resolve
    real_read = config_loader.read

    def resolve_spy(loaded, keys, where, *args, **kwargs):
        keys = tuple(keys)
        resolved.append({key.path for key in keys})
        return real_resolve(loaded, keys, where, *args, **kwargs)

    def read_spy(root, relpath=config_loader.CONFIG_FILE):
        read.append(relpath)
        return real_read(root, relpath)

    monkeypatch.setattr(config_loader, "resolve", resolve_spy)
    monkeypatch.setattr(config_loader, "read", read_spy)
    drift_policy(load_manifest(_ROOT))
    assert read == [config_loader.CONFIG_FILE]
    assert resolved == [{(_BLOCK, _HISTORY_KEY), (_BLOCK, "forbidden_phrases")}]
    assert resolved[0] <= {key.path for key in config_loader.KEYS}


def test_a_loader_refusal_is_a_doc_drift_config_error():
    with pytest.raises(DocDriftConfigError, match="doc_drift.forbidden_phrases"):
        drift_policy(
            {"doc_drift": {"history_paths": ["h/"], "forbidden_phrases": ["x"]}}
        )


def test_no_shipped_doc_cites_a_document_the_template_never_ships():
    excluded = never_shipped_docs(_ROOT)
    if excluded is None:
        pytest.skip(_TEMPLATE_ONLY)
    sources, _binaries = shipped_sources(_ROOT)
    findings = excluded_citation_findings(sources, excluded)
    assert not findings, "\n".join(findings)


def test_a_history_twin_carries_none_of_the_template_s_own_history(policy):
    if not (_ROOT / "copier.yml").is_file():
        pytest.skip(_TEMPLATE_ONLY)
    findings, pairs = leaked_history_findings(_ROOT, policy["history_paths"])
    assert pairs, (
        "no history file with a .md.jinja twin found -- a scan over zero pairs"
    )
    assert not findings, "\n".join(findings)


def test_a_planted_history_entry_in_a_twin_reds_the_scan(tmp_path):
    entry = "- **A template fix (KEEL-PLANTED-1).**"
    (tmp_path / "CHANGELOG.md").write_text(
        "## [Unreleased]\n\n%s\n" % entry, encoding="utf-8"
    )
    twin = tmp_path / "CHANGELOG.md.jinja"
    twin.write_text("## [Unreleased]\n- Generated.\n", encoding="utf-8")
    assert leaked_history_findings(tmp_path, ("CHANGELOG.md",)) == ([], 1)
    twin.write_text("## [Unreleased]\n%s\n- Generated.\n" % entry, encoding="utf-8")
    findings, pairs = leaked_history_findings(tmp_path, ("CHANGELOG.md",))
    assert pairs == 1 and len(findings) == 1, findings
    assert "CHANGELOG.md.jinja:2:" in findings[0] and "KEEL-PLANTED-1" in findings[0]


def test_a_planted_citation_of_a_never_shipped_document_reds_the_scan(exclusion_tree):
    findings = _planted_exclusion_findings(
        exclusion_tree, "CONTRIBUTING.md", "See `docs/secret.md` for why.\n"
    )
    assert len(findings) == 1 and "docs/secret.md" in findings[0], findings


@pytest.fixture
def exclusion_tree(tmp_path):
    if not (_ROOT / "copier.yml").is_file():
        pytest.skip(_TEMPLATE_ONLY)
    (tmp_path / "copier.yml").write_text(
        '_exclude: ["copier.yml", "docs/private/", "docs/secret.md"]\n'
        '_templates_suffix: ".jinja"\n_answers_file: ".copier-answers.yml"\n',
        encoding="utf-8",
    )
    cabinet = tmp_path / "docs" / "private"
    cabinet.mkdir(parents=True)
    (cabinet / "existing.md").write_text("private\n", encoding="utf-8")
    return tmp_path


def _planted_exclusion_findings(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    excluded = never_shipped_docs(root)
    assert excluded is not None
    return excluded_citation_findings([(path, target.read_text())], excluded)


def test_non_docs_exclusions_are_outside_the_citation_gate(exclusion_tree):
    config = exclusion_tree / "copier.yml"
    config.write_text(
        config.read_text().replace(
            '"docs/secret.md"', '"docs/secret.md", ".venv", "wiki/corpus.json"'
        ),
        encoding="utf-8",
    )
    text = "Use .venv and wiki/corpus.json.\n"
    (exclusion_tree / "guide.md").write_text(text, encoding="utf-8")
    venv = exclusion_tree / ".venv"
    venv.mkdir()
    (venv / "probe.py").write_text("# docs/private/existing.md\n")
    excluded = never_shipped_docs(exclusion_tree)
    assert excluded
    sources, binaries = shipped_sources(exclusion_tree, ["guide.md", ".venv/probe.py"])
    assert binaries == 0 and sources == [("guide.md", text)]
    assert excluded_citation_findings(sources, excluded) == []


def test_directory_exclusion_catches_existing_and_nonexistent_descendants(
    exclusion_tree,
):
    findings = _planted_exclusion_findings(
        exclusion_tree,
        "guide.md",
        "docs/private/existing.md\ndocs/private/nonexistent/record.md\n",
    )
    assert len(findings) == 2, findings
    assert "existing.md" in findings[0] and "nonexistent/record.md" in findings[1]
    (exclusion_tree / "probe.bin").write_bytes(b"docs/private/existing.md\0")
    (exclusion_tree / "plain.md").write_text("docs/private/existing.md\n")
    (exclusion_tree / "plain.md.jinja").write_text("A public twin.\n")
    excluded = never_shipped_docs(exclusion_tree)
    files = [
        p.relative_to(exclusion_tree).as_posix()
        for p in exclusion_tree.rglob("*")
        if p.is_file()
    ]
    sources, binaries = shipped_sources(exclusion_tree, files)
    assert binaries == 1
    assert {p for p, _text in sources} == {"guide.md", "plain.md.jinja"}
    assert len(excluded_citation_findings(sources, excluded)) == 2
    assert (
        excluded_citation_findings(
            [("guide.md", "docs/private-sibling/existing.md\n")], excluded
        )
        == []
    )
    with pytest.raises(DocDriftConfigError, match="zero shipped files"):
        shipped_sources(exclusion_tree, ["docs/private/existing.md"])
    for entries, message in (
        ("[]", "zero unconditional docs/ exclusions"),
        (
            '[".venv", "wiki/corpus.json"]',
            "zero unconditional docs/ exclusions",
        ),
        (
            '["docs/private/", "docs/private/*.md"]',
            r"docs/private/\*.md",
        ),
        (
            '["{% if enabled %}docs/private/{% endif %}"]',
            "zero unconditional docs/ exclusions",
        ),
        ('["docs/secret.md"]', "zero directory exclusions"),
    ):
        (exclusion_tree / "copier.yml").write_text("_exclude: " + entries + "\n")
        with pytest.raises(DocDriftConfigError, match=message):
            never_shipped_docs(exclusion_tree)


@pytest.mark.parametrize(
    "path,text",
    [
        ("probe.py", "# docs/private/existing.md\n"),
        ("probe.json", '{"path": "docs/private/existing.md"}\n'),
        ("Makefile", "# docs/private/existing.md\n"),
        ("guide.md.jinja", "{% if enabled %}docs/private/existing.md{% endif %}\n"),
        ("docs/adr/K-0001.md", "[decision](../private/existing.md)\n"),
        (
            "guide.md",
            "| Path | Arrives |\n|---|---|\n| `docs/private/existing.md` | never |\n",
        ),
        ("fenced.md", "```text\ndocs/private/existing.md\n```\n"),
    ],
)
def test_excluded_mentions_count_in_every_source_context(exclusion_tree, path, text):
    findings = _planted_exclusion_findings(exclusion_tree, path, text)
    assert len(findings) == 1 and "docs/private/existing.md" in findings[0], findings
    excluded = never_shipped_docs(exclusion_tree)
    sources, binaries = shipped_sources(exclusion_tree, [path])
    assert binaries == 0 and sources == [(path, text)]
    assert excluded_citation_findings(sources, excluded) == findings


def test_template_only_module_guard_is_the_whole_file_exemption(exclusion_tree):
    guard = (
        "import pytest\nfrom pathlib import Path\n"
        "_ROOT = Path(__file__).resolve().parents[2]\n"
        '_TEMPLATE_ONLY = "not a copier template — this is a generated project"\n'
        "pytestmark = [pytest.mark.integration, pytest.mark.skipif(\n"
        '    not (_ROOT / "copier.yml").is_file(), reason=_TEMPLATE_ONLY)]\n'
    )
    mention = "# docs/secret.md\n"
    assert (
        _planted_exclusion_findings(
            exclusion_tree, "tests/test_probe.py", guard + mention
        )
        == []
    )
    findings = _planted_exclusion_findings(
        exclusion_tree, "tests/test_probe.py", mention
    )
    assert len(findings) == 1, findings


# --- rule (d) is advisory: a change phrase at an opener is review's --------


@pytest.mark.parametrize(
    "text",
    [
        "2. Now run `make verify`, then commit.",
        "| Mode | Rerun |\n|---|---|\n| writer | fixed-point |",
        "Removed entries are reported by the audit.",
        "Added keys need a `KEYS` row.",
        "Moved files keep their history.",
    ],
    ids=["ordered-step", "table-cell", "removed", "added", "moved"],
)
def test_a_present_claim_at_an_opener_reds_no_gate_scan_and_review_reports_it(
    tmp_path, manifest, policy, docs, text
):
    """A past participle or "now" at an opener is as often a present claim as
    a report, so this gate leaves it to scripts/jobs/review_docs.py, whose
    advisory (`make doc-review`) reports it for a reader to judge."""
    (tmp_path / "CONTRIBUTING.md").write_text(
        dict(docs)["CONTRIBUTING.md"] + "\n" + text + "\n", encoding="utf-8"
    )
    found = shipped_docs(tmp_path, policy["history_paths"])
    mention = work_mention(manifest)
    assert moment_and_host_findings(found, policy, mention, tmp_path) == []
    letters = {letter for letter, _fn in cs.CHECKS}
    names = python_names(_ROOT)
    assert letters and names, "a citation scan must judge checks"
    assert check_citation_findings(found, letters, names) == []
    excluded = never_shipped_docs(_ROOT)
    if excluded is not None:
        assert excluded_citation_findings(found, excluded) == []
    phrases, _history = review_docs.opener_policy(str(_ROOT))
    reported = review_docs.change_openers(found, phrases)
    assert [path for path, _line, _phrase in reported] == ["CONTRIBUTING.md"]


@pytest.mark.parametrize(
    "pattern,reason",
    [
        ("HOSTILE[", "a reason"),
        ("(" * 600 + "HOSTILE" + ")" * 600, "a reason"),
        ("HOSTILE{4294967296}", "a reason"),
        ("HOSTILE{" + "9" * 5000 + "}", "a reason"),
        ("HOSTILE" + "x" * 65536, "a reason"),
        ("HOSTILE", ""),
        ("HOSTILE", ["HOSTILE"]),
    ],
    ids=[
        "syntax",
        "depth",
        "overflow",
        "decimal-limit",
        "size",
        "empty-reason",
        "wrong-reason",
    ],
)
def test_forbidden_pattern_faults_refuse_without_echoing(
    pattern: str, reason: object
) -> None:
    manifest = {
        "doc_drift": {
            "history_paths": ["history/"],
            "forbidden_phrases": {pattern: reason},
        }
    }
    with pytest.raises(DocDriftConfigError) as exc:
        drift_policy(manifest)
    message = str(exc.value)
    assert "config/project.json" in message and "doc_drift.forbidden_phrases" in message
    assert "correct" in message and "HOSTILE" not in message


def test_a_missing_or_malformed_doc_drift_block_fails_closed(manifest):
    broken = dict(manifest)
    broken.pop(_BLOCK, None)
    with pytest.raises(DocDriftConfigError, match="doc_drift"):
        drift_policy(broken)
    bad = dict(manifest, doc_drift={"history_paths": [], "forbidden_phrases": {}})
    with pytest.raises(DocDriftConfigError, match="history_paths"):
        drift_policy(bad)
    # The empty map alone, beside valid history paths: paired with an empty
    # history list above, the history guard fails first and hides this one.
    block = dict(manifest[_BLOCK], forbidden_phrases={})
    with pytest.raises(DocDriftConfigError, match="forbidden_phrases"):
        drift_policy(dict(manifest, doc_drift=block))
    for key in (
        "one_hop",
        "audiences",
        "limits_guide",
        "gate_target",
        "settings_reference",
        "features_reference",
    ):
        missing = dict(manifest, doc_drift=dict(manifest.get(_BLOCK) or {}))
        missing[_BLOCK].pop(key, None)
        with pytest.raises(DocDriftConfigError, match=key):
            entry_policy(missing)
    no_naming = dict(manifest)
    no_naming.pop("work_naming", None)
    with pytest.raises(DocDriftConfigError, match="work_naming"):
        work_mention(no_naming)


# --- rule (b): entry documents, the layout tree, guide audiences -----------


def test_the_entry_docs_reach_their_one_hop_targets(entry, markdown):
    known = set(markdown)
    findings = one_hop_findings(entry["one_hop"], markdown, known)
    findings += roster_reach_findings(entry["roster"], markdown, known)
    assert not findings, "\n".join(findings)


def test_the_readme_layout_tree_lists_every_shipping_top_level_directory(
    manifest, entry, markdown
):
    expected = shipping_toplevel_dirs(_ROOT, manifest)
    assert expected, "no shipping top-level directory derived -- zero items"
    findings = layout_findings(
        "README.md", markdown["README.md"], entry["layout_heading"], expected, _ROOT
    )
    assert not findings, "\n".join(findings)


def test_every_guide_roster_row_names_its_audience(entry, markdown):
    roster = entry["roster"]
    assert roster in markdown, "%s does not exist" % roster
    findings = audience_findings(roster, markdown[roster], entry["audiences"])
    assert not findings, "\n".join(findings)


def _blank_first_audience(text):
    """*text* with the first roster row's Audience cell emptied, and that
    row's member."""
    header, rows = cs._roster_table(text)
    col = header.index("audience")
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("| " + rows[0][0] + " |"):
            cells = line.split("|")
            cells[col + 1] = " "
            lines[i] = "|".join(cells)
            return "\n".join(lines), rows[0][0]
    raise AssertionError("the first roster row was not found")


@pytest.mark.parametrize("fault", ["hop", "tree", "audience"])
def test_dropping_a_hop_a_tree_entry_or_an_audience_reds_the_entry_checks(
    manifest, entry, markdown, fault
):
    known = set(markdown)
    texts = dict(markdown)
    readme, roster = "README.md", entry["roster"]
    expected = shipping_toplevel_dirs(_ROOT, manifest)

    def judge(t):
        if fault == "hop":
            return one_hop_findings(entry["one_hop"], t, known)
        if fault == "tree":
            return layout_findings(
                readme, t[readme], entry["layout_heading"], expected, _ROOT
            )
        return audience_findings(roster, t[roster], entry["audiences"])

    assert judge(texts) == [], "the unplanted tree must be clean"
    if fault == "hop":
        target = "CONTRIBUTING.md"
        assert target in entry["one_hop"][readme]
        texts[readme] = texts[readme].replace(target, "CONTRIBUTING")
    elif fault == "tree":
        target = "runtimes/"
        kept = [
            ln
            for ln in texts[readme].split("\n")
            if not re.match(r"^[├└]── runtimes/", ln)
        ]
        assert len(kept) == texts[readme].count("\n"), "no single runtimes/ line"
        texts[readme] = "\n".join(kept)
    else:
        texts[roster], target = _blank_first_audience(texts[roster])
    findings = judge(texts)
    assert len(findings) == 1, findings
    assert target in findings[0], findings


# --- rule (c): the limits guide ------------------------------------------------


def test_the_limits_guide_names_every_waiver(entry, markdown):
    guide = entry["limits_guide"]
    assert guide in markdown, "%s does not exist" % guide
    waivers = derived_waivers(_ROOT)
    assert waivers, "no waiver derived -- zero items"
    findings = waiver_findings(guide, markdown[guide], waivers)
    assert not findings, "\n".join(findings)


def test_dropping_a_waivers_row_reds_it_though_the_guide_names_it_elsewhere(
    entry, markdown
):
    # A waiver is also named in prose (a symptom row, a blind spot), so a
    # rule that read the whole guide would not see its row go.
    guide = entry["limits_guide"]
    text = markdown[guide]
    waivers = derived_waivers(_ROOT)
    assert waivers, "no waiver derived -- zero items"
    assert waiver_findings(guide, text, waivers) == [], (
        "the unplanted guide must be clean"
    )
    for waiver in sorted(waivers):
        lines = text.split("\n")
        rows = [
            i for i, line in enumerate(lines) if line.startswith("| `%s` |" % waiver)
        ]
        assert len(rows) == 1, (waiver, rows)
        del lines[rows[0]]
        findings = waiver_findings(guide, "\n".join(lines), waivers)
        assert len(findings) == 1 and waiver in findings[0], (waiver, findings)


def test_the_limits_guide_names_every_gate_exit_code(entry, markdown):
    guide = entry["limits_guide"]
    assert guide in markdown, "%s does not exist" % guide
    scripts = gate_scripts(_ROOT, entry["gate_target"])
    assert scripts, "make %s runs no script -- zero items" % entry["gate_target"]
    findings = exit_code_findings(guide, markdown[guide], _ROOT, scripts)
    assert not findings, "\n".join(findings)


@pytest.mark.parametrize(
    "fault",
    [
        "generic-ok",
        "child_env.credentialed_values",
        "doc_drift.history_paths",
        "tests.isolation.exempt",
        "exit-code",
    ],
)
def test_removing_a_waiver_or_an_exit_code_from_the_limits_guide_reds_it(
    entry, markdown, fault
):
    # The four waivers come from four sources derived_waivers reads: a
    # checker's pragma, the child-process allowlist's keys, this gate's own
    # history exemption, and the isolation guard's exemptions.
    guide = entry["limits_guide"]
    text = markdown[guide]
    if fault != "exit-code":
        waivers = derived_waivers(_ROOT)
        assert fault in waivers, waivers

        def judge(t):
            return waiver_findings(guide, t, waivers)

        planted = text.replace("`%s`" % fault, fault)
        target = fault
    else:
        scripts = gate_scripts(_ROOT, entry["gate_target"])
        target = "scripts/check_structure.py"
        assert target in scripts

        def judge(t):
            return exit_code_findings(guide, t, _ROOT, scripts)

        lines = text.split("\n")
        # The generated table's row, not the hand-written one below the region.
        begin = lines.index(exit_code_table.BEGIN)
        end = lines.index(exit_code_table.END)
        rows = [
            i for i in range(begin, end) if lines[i].startswith("| `%s` |" % target)
        ]
        assert len(rows) == 1, rows
        cells = lines[rows[0]].split("|")
        cells[2] = re.sub(r",?\s*\b2\b", "", cells[2])
        lines[rows[0]] = "|".join(cells)
        planted = "\n".join(lines)
    assert judge(text) == [], "the unplanted guide must be clean"
    assert planted != text
    findings = judge(planted)
    assert len(findings) == 1, findings
    assert target in findings[0], findings


def test_exit_codes_follows_a_named_member_and_reads_no_code_from_an_unknown_name(
    tmp_path,
):
    """A script is read through the names it binds its members to; a returned
    name nothing binds, or an int literal, yields no code, which
    exit_code_findings reports as zero items rather than passing."""
    script = tmp_path / "named.py"
    head = "from exit_codes import ExitCode, passthrough, report\n"
    values = {m.name: m.value for m in exit_code_table.read_members(str(_ROOT))}

    def member(name):
        return values[name]

    script.write_text(
        head + "def main(flag):\n"
        "    code = report(ExitCode.USAGE, 'a', 'b', 'c')\n"
        "    if flag:\n        return code\n"
        "    kind = ExitCode.FAILURE if flag is None else ExitCode.RED_RECORD\n"
        "    if flag == 0:\n        return report(kind, 'a', 'b', 'c')\n"
        "    return ExitCode.SUCCESS\n"
    )
    assert exit_codes(script) == ({member("SUCCESS"), member("USAGE")}, False)
    script.write_text(
        head + "def main(flag):\n"
        "    return report(\n"
        "        ExitCode.FAILURE if flag else ExitCode.RED_RECORD, 'a', 'b', 'c'\n"
        "    )\n"
    )
    assert exit_codes(script) == ({member("FAILURE"), member("RED_RECORD")}, False)
    script.write_text(head + "def main():\n    return UNKNOWN\n")
    assert exit_codes(script) == (set(), False)
    script.write_text(
        head + "def main():\n    code = %d\n    return code\n" % member("RED_RECORD")
    )
    assert exit_codes(script) == (set(), False)
    script.write_text(head + "def main(child):\n    return passthrough(child)\n")
    assert exit_codes(script) == (set(), True)


# --- rule (d): the upgrade guide (template only) ----------------------------------


def test_the_upgrade_guide_names_every_copier_migration_task_and_exclusion(
    entry, markdown
):
    inventory = copier_inventory(_ROOT)
    if inventory is None:
        pytest.skip(_TEMPLATE_ONLY)
    guide = entry["upgrade_guide"]
    assert guide in markdown, "%s does not exist" % guide
    findings = upgrade_findings(guide, markdown[guide], _ROOT, inventory)
    assert not findings, "\n".join(findings)


@pytest.mark.parametrize("table", ["checklist", "exclusions"])
def test_removing_a_migration_or_an_exclusion_from_the_upgrade_guide_reds_it(
    entry, markdown, table
):
    inventory = copier_inventory(_ROOT)
    if inventory is None:
        pytest.skip(_TEMPLATE_ONLY)
    guide = entry["upgrade_guide"]
    text = markdown[guide]
    assert upgrade_findings(guide, text, _ROOT, inventory) == []
    lines = text.split("\n")
    assert inventory[table], "the mutation must judge an inventory item"
    is_step = table == "checklist"
    target = next(
        item
        for item in inventory[table]
        if not is_step or sum(item in items for _kind, items in inventory["steps"]) == 1
    )
    columns = _CHECKLIST_TABLE if is_step else _EXCLUSION_TABLE
    header, _rows = cs._pipe_table(text, columns)
    start = next(
        i
        for i, ln in enumerate(lines)
        if ln.startswith("|")
        and [c.strip().lower() for c in ln.strip().strip("|").split("|")] == header
    )
    end = next(
        (i for i in range(start, len(lines)) if not lines[i].startswith("|")),
        len(lines),
    )
    hits = [i for i in range(start + 2, end) if target in _backticked(lines[i])]
    assert len(hits) == 1, hits
    del lines[hits[0]]
    findings = upgrade_findings(guide, "\n".join(lines), _ROOT, inventory)
    assert len(findings) == 1, findings
    assert target in findings[0], findings


def _table_line_numbers(lines, columns):
    """The line indexes of the body rows of the first pipe table whose header
    carries every one of *columns*."""
    wanted = [c.lower() for c in columns]
    for i, ln in enumerate(lines):
        header = [c.strip().lower() for c in ln.strip().strip("|").split("|")]
        if ln.startswith("|") and all(c in header for c in wanted):
            end = next(
                (j for j in range(i + 2, len(lines)) if not lines[j].startswith("|")),
                len(lines),
            )
            return list(range(i + 2, end))
    raise AssertionError("no table with the columns %s" % ", ".join(columns))


@pytest.mark.parametrize(
    "fault", ["drop-task-row", "drop-last-migration-row", "swap-two-rows"]
)
def test_each_task_and_migration_has_its_own_row_in_the_order_copier_runs_it(
    entry, markdown, fault
):
    # restamp_docs.py is both the `_tasks` entry and the last `_migrations`
    # entry: one row must not stand in for the other, and the rows must keep
    # copier's order (the task while it renders, then each after-migration in
    # copier.yml's order).
    inventory = copier_inventory(_ROOT)
    if inventory is None:
        pytest.skip(_TEMPLATE_ONLY)
    guide = entry["upgrade_guide"]
    text = markdown[guide]
    assert upgrade_findings(guide, text, _ROOT, inventory) == []
    lines = text.split("\n")
    body = _table_line_numbers(lines, _CHECKLIST_TABLE)
    if fault == "drop-task-row":
        hits = [i for i in body if lines[i].startswith("| task:")]
        assert len(hits) == 1, hits
        target = "restamp_docs.py"
        del lines[hits[0]]
    elif fault == "drop-last-migration-row":
        target = "restamp_docs.py"
        assert target in lines[body[-1]]
        del lines[body[-1]]
    else:
        first, second = body[-2], body[-1]
        target = "restamp_docs.py"
        assert "resolve_stamp_conflicts.py" in lines[first]
        assert target in lines[second]
        lines[first], lines[second] = lines[second], lines[first]
    findings = upgrade_findings(guide, "\n".join(lines), _ROOT, inventory)
    assert len(findings) == 1, findings
    assert target in findings[0], findings


def test_removing_the_copier_version_floor_from_the_upgrade_guide_reds_it(
    entry, markdown
):
    inventory = copier_inventory(_ROOT)
    if inventory is None:
        pytest.skip(_TEMPLATE_ONLY)
    guide = entry["upgrade_guide"]
    text = markdown[guide]
    floor = inventory["min_copier_version"]
    assert upgrade_findings(guide, text, _ROOT, inventory) == []
    planted = text.replace(floor, "the floor")
    assert planted != text
    findings = upgrade_findings(guide, planted, _ROOT, inventory)
    assert len(findings) == 1 and floor in findings[0], findings


def test_a_planted_prose_citation_in_the_upgrade_guide_reds_the_scan(exclusion_tree):
    findings = _planted_exclusion_findings(
        exclusion_tree, "docs/guides/upgrade.md", "See `docs/secret.md` for why.\n"
    )
    assert len(findings) == 1 and "secret.md" in findings[0], findings


def test_an_untracked_dot_directory_is_not_a_shipping_directory(tmp_path, manifest):
    # An editor's settings directory that git does not track ships nowhere;
    # only a dot-directory git tracks is part of the layout.
    if shutil.which("git") is None:
        pytest.skip("git is not installed -- the tracked set cannot be read")
    env = build_child_env()
    for args in (("init", "-q"),):
        subprocess.run(
            review_docs.git_argv(str(tmp_path), *args),
            cwd=str(tmp_path),
            env=env,
            check=True,
        )
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "w.yml").write_text("x\n", encoding="utf-8")
    (tmp_path / ".editor").mkdir()
    (tmp_path / ".editor" / "settings.json").write_text("{}\n", encoding="utf-8")
    subprocess.run(
        review_docs.git_argv(str(tmp_path), "add", ".github"),
        cwd=str(tmp_path),
        env=env,
        check=True,
    )
    found = shipping_toplevel_dirs(tmp_path, {"structure": {"extra_toplevel": []}})
    assert ".github" in found, found
    assert ".editor" not in found, found


@pytest.mark.parametrize(
    "data, docs, expected_count",
    [
        (b"PORT = 59\xff999\n", [("guide.md", "http://localhost:59999")], 2),
        (b"invalid: \xff\n", [("guide.md", "http://localhost:59999")], 1),
        (b"invalid: \xff\n", [("guide.md", "No host-specific setting.")], 1),
    ],
    ids=["cannot-erase-a-byte-to-declare-a-port", "after-port-is-found", "no-port"],
)
def test_invalid_utf8_is_a_named_byte_offset_finding(
    tmp_path, monkeypatch, manifest, policy, data, docs, expected_count
):
    (tmp_path / "a_valid.py").write_text(
        "# café\nPORT = 59999\n" if expected_count == 1 else "# café\n",
        encoding="utf-8",
    )
    (tmp_path / "z_invalid.py").write_bytes(data)
    monkeypatch.setattr(
        sys.modules[__name__],
        "_non_markdown_files",
        lambda root: ["a_valid.py", "z_invalid.py"],
    )
    findings = moment_and_host_findings(docs, policy, work_mention(manifest), tmp_path)
    assert len(findings) == expected_count, findings
    assert any(
        "z_invalid.py" in finding
        and "UTF-8" in finding
        and "byte offset %d" % data.index(b"\xff") in finding
        for finding in findings
    ), findings


def test_non_ascii_utf8_and_nul_binaries_are_not_decode_findings(
    tmp_path, monkeypatch, manifest, policy
):
    (tmp_path / "serve.py").write_text("# café\nPORT = 59999\n", encoding="utf-8")
    (tmp_path / "asset.bin").write_bytes(b"\x00\xff")
    monkeypatch.setattr(
        sys.modules[__name__],
        "_non_markdown_files",
        lambda root: ["serve.py", "asset.bin"],
    )
    assert (
        moment_and_host_findings(
            [("guide.md", "http://localhost:59999")],
            policy,
            work_mention(manifest),
            tmp_path,
        )
        == []
    )


def test_forbidden_backtracking_refuses_within_deadline(tmp_path: Path) -> None:
    pattern, value = "(a+)+$", "a" * 100 + "b"
    policy = drift_policy(
        {
            "doc_drift": {
                "history_paths": ["history/"],
                "forbidden_phrases": {pattern: "a reason"},
            }
        }
    )
    started = time.monotonic()
    with pytest.raises(AssertionError, match="doc_drift.forbidden_phrases.*timeout"):
        moment_and_host_findings(
            [("guide.md", value)],
            policy,
            re.compile("never"),
            tmp_path,
            timeout=0.2,
        )
    assert time.monotonic() - started < 5


def test_forbidden_match_then_backtrack_refuses_within_deadline(tmp_path: Path) -> None:
    """The pattern matches `x`, then backtracks on the tail the finder must
    still scan; no configured regex may run outside the bounded child."""
    pattern, value = r"x|(a+)+$", "x " + "a" * 40 + "b"
    policy = drift_policy(
        {
            "doc_drift": {
                "history_paths": ["history/"],
                "forbidden_phrases": {pattern: "a reason"},
            }
        }
    )
    started = time.monotonic()
    with pytest.raises(AssertionError, match="doc_drift.forbidden_phrases.*timeout"):
        moment_and_host_findings(
            [("guide.md", value)],
            policy,
            re.compile("never"),
            tmp_path,
            timeout=0.5,
        )
    assert time.monotonic() - started < 5
