"""
title: Unit — scripts hide configured text that holds an @
kind: tests
layer: n/a
summary: No message a script under scripts/, models/ or tests/isolation_guard.py, or the evals config, builds from configured text shows that text when it holds an `@`, at any depth: a value, a list member, a nested member, a key name, a path segment or a piece of a joined value, and an exception's own text that embeds it. Each row plants a sentinel in one position (keel's own config served in memory, or a variable set for the test; the tree untouched), runs the one reader that turns it into a message, and asserts the reader still refuses, the sentinel never shows and the line says it is hidden; the rows run over script families and mutation kinds. Beside them, a joined line still shows its harmless members and a value of the wrong type still reads as that type. In a generated project a row that plants into a block keel's own config has and the project's lacks is skipped naming the block.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import launch  # noqa: E402

pytestmark = pytest.mark.unit

# Not credential-shaped: the `@` alone is what the rule keys on.
_STEM = "SENTINEL"
_AT = "tok-SENTINEL@h.invalid"
_HIDDEN = "<hidden: it holds an @>"


def _load(relpath="config/project.json"):
    with open(_ROOT / relpath, encoding="utf-8") as fh:
        return json.load(fh)


def _node(doc, path):
    for seg in path:
        doc = doc[seg]
    return doc


def _mutate(doc, path, kind, value=_AT):
    """One planted fault: V sets the value at *path*, K renames its last key,
    A adds a key to the object at *path*, M appends a member to the list at
    *path*, D appends a nested list holding the member, N replaces the value
    with a nested object, P inserts the value as a path segment, S joins it
    to the value with separators."""
    if kind == "V":
        _node(doc, path[:-1])[path[-1]] = value
    elif kind == "K":
        parent = _node(doc, path[:-1])
        items = list(parent.items())
        parent.clear()
        for k, v in items:
            parent[value if k == path[-1] else k] = v
    elif kind == "A":
        _node(doc, path)[value] = "x"
    elif kind == "M":
        _node(doc, path).append(value)
    elif kind == "D":
        _node(doc, path).append([value])
    elif kind == "N":
        _node(doc, path[:-1])[path[-1]] = {value: [value]}
    elif kind == "P":
        parent = _node(doc, path[:-1])
        parent[path[-1]] = value + "/" + parent[path[-1]]
    elif kind == "S":
        parent = _node(doc, path[:-1])
        parent[path[-1]] = parent[path[-1]] + "," + value + ".x"
    else:
        raise ValueError(kind)


def _planted(path, kind, value=_AT):
    """keel's config/project.json with one fault planted; in a generated
    project a block it lacks skips the row, in the template it fails."""
    doc = _load()
    try:
        _mutate(doc, path, kind, value)
    except KeyError as missing:
        if (_ROOT / "copier.yml").is_file():
            raise
        pytest.skip("this project's config has no %s: a block keel's own has" % missing)
    return doc


def _hides(text, *neighbours):
    """The sentinel never shows, the line says it is hidden, and each harmless
    *neighbour* on the same line still shows."""
    assert text.strip(), "the reader refused with no message"
    assert _STEM not in text, text
    assert _HIDDEN in text, text
    for shown in neighbours:
        assert shown in text, (shown, text)


# --- scripts/launch.py -----------------------------------------------------

_L = ("launcher",)
_SLURM = _L + ("farm", "adapters", "slurm")
_LAUNCH_ROWS = [
    ("cpus-value", _L + ("default_size", "cpus"), "V", ()),
    ("long-script-size", _L + ("long_scripts", "make verify", "minutes"), "V", ()),
    ("unknown-top-key", _L, "A", ("launcher.",)),
    ("unknown-size-key", _L + ("default_size",), "A", ("launcher.default_size.",)),
    ("renamed-key", _L + ("_comment",), "K", ("launcher.",)),
    ("credentials-entry", _L + ("credentials",), "A", ("launcher.credentials.",)),
    ("long-scripts-entry", _L + ("long_scripts",), "A", ("launcher.long_scripts.",)),
    ("farm-adapter-value", _L + ("farm", "adapter"), "V", ("none", "slurm")),
    ("farm-adapter-segment", _L + ("farm", "adapter"), "P", ()),
    ("farm-adapter-joined", _L + ("farm", "adapter"), "S", ()),
    ("adapter-name", _L + ("farm", "adapters"), "A", ("launcher.farm.adapters.",)),
    ("adapter-kind", _SLURM + ("kind",), "V", ("launcher.farm.adapters.slurm.kind",)),
    ("env-name", _SLURM + ("env",), "A", ("launcher.farm.adapters.slurm.env.",)),
    ("env-template", _SLURM + ("env", "SLURM_EXIT_ERROR"), "V", ()),
    ("submit-word", _SLURM + ("submit",), "D", ("submit[7]",)),
    ("submit-template", _SLURM + ("submit", 0), "S", ()),
    ("inside-env-value", _SLURM + ("inside_env",), "V", ()),
    ("inside-env-member", _SLURM + ("inside_env",), "M", ("'SLURM_JOB_ID'",)),
    ("inside-env-nested", _SLURM + ("inside_env",), "D", ("'SLURM_JOB_ID'",)),
    ("inside-env-object", _SLURM + ("inside_env",), "N", ()),
    ("status", _SLURM + ("farm_error_status",), "V", ()),
    ("load-per-cpu", _L + ("spare", "max_load_per_cpu"), "V", ()),
    ("state-path", _L + ("own_hosts_file",), "P", ()),
]


@pytest.mark.parametrize(
    "path, kind, neighbours",
    [r[1:] for r in _LAUNCH_ROWS],
    ids=[r[0] for r in _LAUNCH_ROWS],
)
def test_launch_hides_configured_text_holding_an_at(path, kind, neighbours):
    value = _AT
    if kind == "V" and path[-1] == "own_hosts_file":
        value = "/" + _AT
    if path[-1:] == (0,) or path[-1] == "SLURM_EXIT_ERROR":
        # A template refusal: a placeholder outside the closed set.
        value = "{" + _AT + "}"
    manifest = _planted(path, kind, value)
    if path[-1] == "SLURM_EXIT_ERROR":
        _node(manifest, path[:-1])[path[-1]] = value
    if path[-1:] == (0,):
        _node(manifest, path[:-1])[0] = value
    if path[-1] == "own_hosts_file":
        _node(manifest, path[:-1])[path[-1]] = "/" + _AT
    with pytest.raises(launch.LauncherConfigError) as refused:
        launch.load_launcher_config(manifest)
    _hides(str(refused.value), *neighbours)


def test_launch_shows_a_value_of_the_wrong_type_as_itself():
    manifest = _planted(_L + ("default_size", "cpus"), "V", [True, "a"])
    with pytest.raises(launch.LauncherConfigError) as refused:
        launch.load_launcher_config(manifest)
    assert "is [true, 'a'], not a whole number" in str(refused.value)


def test_launch_hides_a_state_path_and_a_credential_name_holding_an_at(
    monkeypatch, capsys
):
    class Cfg:
        durations_file = ".launch/" + _AT
        own_hosts_file = "config/own-hosts.local.json"

    # Both paths reported as linked: the refusal names each configured path.
    monkeypatch.setattr(launch.git_tree, "through_symlink", lambda _root, paths: paths)
    found = launch._unsafe_state(str(_ROOT), Cfg())
    _hides(found[0], "config/own-hosts.local.json")
    launch._stopped(("credential", ["LC_" + _AT, "OTHER_NAME"]), ["make"], False, None)
    _hides(capsys.readouterr().err, "OTHER_NAME")
