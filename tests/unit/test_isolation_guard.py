"""
title: Unit — the isolation guard judges each reach by the test's tier
kind: tests
layer: n/a
summary: tests/isolation_guard.py's pure parts. `classify` returns no violation for a reach inside the roots and one naming its axis, event and resolved target outside them, for every judged event: an open for writing (by mode or by flags; a read is allowed, a file descriptor skipped), a rename's source and destination, a remove, rmdir, mkdir, truncate and rmtree, a symlink's or link's destination only, an entry removed through a directory file descriptor (resolved through /proc, skipped when /proc is absent), a change of mode, times, owner or an extended attribute (at the link and through it, or at the link alone when the caller stays on it, so a tree copied with a link that points outside reaches nothing), a bytecode write in a `__pycache__` allowed and any other write there refused, a socket connect, sendto or sendmsg (loopback v4, v6, v4-mapped and the literal `localhost` allowed under `loopback`, a hostname refused, an AF_UNIX path judged by the roots, an abstract one refused, a sendmsg with no address allowed), an AF_UNIX bind to a path, a sqlite connect (`:memory:`, an empty name and a memory URI allowed, a `file:` name judged as a URI and as a file in the working directory, bytes decoded), and an open in any mode of a listed store. A root that holds the checkout leaves the checkout outside it, and one inside the checkout is scratch again. The closest tier marker wins, an unmarked test gets the strictest rule, this project's policy loads one rule per configured tier, each a declared marker, an empty scratch variable leaves the configured root, and `load_policy` refuses an unknown value, an unknown axis, a tier missing an axis and a blank reason, naming the key. The message has its fixed shape, and a second store copy changes nothing.
"""

import ipaddress
import json
import os
import shutil
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import isolation_guard as ig

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import config_loader  # noqa: E402

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[2]
_FULL = {
    "unit": {"network": "none", "writes": "temp", "stores": "temp"},
    "integration": {"network": "loopback", "writes": "temp", "stores": "temp"},
}


def _rule(network="none", writes="temp", stores="temp"):
    return ig.TierRule("unit", network, writes, stores)


def _inside(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    return str(root.resolve())


def _outside(tmp_path):
    out = tmp_path / "outside"
    out.mkdir(exist_ok=True)
    return out.resolve()


def _sock(family):
    return SimpleNamespace(family=family)


# --- writes ------------------------------------------------------------------


def test_an_open_for_writing_outside_the_roots_is_a_writes_violation(tmp_path):
    roots = (_inside(tmp_path),)
    target = _outside(tmp_path) / "f"
    got = ig.classify("open", (str(target), "w", 0), _rule(), roots)
    assert got is not None
    assert (got.axis, got.event, got.target, got.value) == (
        "writes",
        "open",
        str(target),
        "temp",
    )
    assert ig.classify("open", (roots[0] + "/f", "w", 0), _rule(), roots) is None


@pytest.mark.parametrize("mode", ["w", "a", "x", "r+", "wb", "ab+"])
def test_every_writing_mode_is_judged(tmp_path, mode):
    roots = (_inside(tmp_path),)
    target = str(_outside(tmp_path) / "f")
    assert ig.classify("open", (target, mode, 0), _rule(), roots) is not None


@pytest.mark.parametrize(
    "flags", [os.O_WRONLY, os.O_RDWR, os.O_CREAT, os.O_TRUNC, os.O_APPEND]
)
def test_os_open_is_judged_by_its_flags(tmp_path, flags):
    roots = (_inside(tmp_path),)
    target = str(_outside(tmp_path) / "f")
    assert ig.classify("open", (target, None, flags), _rule(), roots) is not None
    assert ig.classify("open", (target, None, os.O_RDONLY), _rule(), roots) is None


def test_a_read_and_a_file_descriptor_are_not_writes(tmp_path):
    roots = (_inside(tmp_path),)
    target = str(_outside(tmp_path) / "f")
    assert ig.classify("open", (target, "r", 0), _rule(), roots) is None
    assert ig.classify("open", (target, "rb", 0), _rule(), roots) is None
    assert ig.classify("open", (7, "w", os.O_WRONLY), _rule(), roots) is None


def test_the_null_device_and_a_pycache_are_allowed(tmp_path):
    roots = (_inside(tmp_path),)
    cache = _outside(tmp_path) / "__pycache__"
    assert ig.classify("open", (os.devnull, "w", 0), _rule(), roots) is None
    assert ig.classify("open", (str(cache / "m.pyc"), "wb", 0), _rule(), roots) is None
    assert ig.classify("os.mkdir", (str(cache), 0o777, -1), _rule(), roots) is None
    assert (
        ig.classify(
            "os.rename",
            (str(cache / "m.pyc.1"), str(cache / "m.pyc"), -1, -1),
            _rule(),
            roots,
        )
        is None
    )
    # pytest's assertion rewriter names its own pyc, and its temporary twin
    # carries the writer's process id.
    rewritten = str(cache / "test_m.cpython-311-pytest-8.3.2.pyc")
    for name in (rewritten, rewritten + ".4242", str(cache / "m.opt-1.pyc")):
        assert ig.classify("open", (name, None, os.O_WRONLY), _rule(), roots) is None
    assert ig.classify("os.remove", (rewritten + ".4242", -1), _rule(), roots) is None


@pytest.mark.parametrize(
    ("event", "args"),
    [
        ("open", ("{cache}/notes.json", "w", 0)),
        ("open", ("{cache}/m.pyc.tmp", "w", 0)),
        ("open", ("{cache}/m.pyc.", "w", 0)),
        ("os.remove", ("{cache}/notes.json", -1)),
        ("os.rename", ("{cache}/a", "{cache}/b", -1, -1)),
        ("os.truncate", ("{cache}/m.pyc", 0)),
        ("shutil.rmtree", ("{cache}", None)),
        ("os.mkdir", ("{cache}/sub", 0o777, -1)),
    ],
)
def test_a_pycache_allows_only_the_bytecode_the_interpreter_writes(
    tmp_path, event, args
):
    roots = (_inside(tmp_path),)
    cache = str(_outside(tmp_path) / "__pycache__")
    filled = tuple(a.format(cache=cache) if isinstance(a, str) else a for a in args)
    got = ig.classify(event, filled, _rule(), roots)
    assert got is not None and got.axis == "writes", (event, filled)


@pytest.mark.parametrize(
    ("event", "args"),
    [
        ("os.remove", ("{out}/f", -1)),
        ("os.rmdir", ("{out}/d", -1)),
        ("os.mkdir", ("{out}/d", 0o777, -1)),
        ("os.truncate", ("{out}/f", 0)),
        ("shutil.rmtree", ("{out}/d", None)),
        ("os.rename", ("{out}/a", "{in}/b", -1, -1)),
        ("os.rename", ("{in}/a", "{out}/b", -1, -1)),
        ("os.symlink", ("{in}/a", "{out}/l", -1)),
        ("os.link", ("{in}/a", "{out}/h", -1, -1)),
    ],
)
def test_each_tree_changing_event_outside_the_roots_is_a_violation(
    tmp_path, event, args
):
    inside = _inside(tmp_path)
    out = str(_outside(tmp_path))

    def fill(a):
        return a.format(out=out, **{"in": inside}) if isinstance(a, str) else a

    filled = tuple(fill(a) for a in args)
    got = ig.classify(event, filled, _rule(), (inside,))
    assert got is not None and got.axis == "writes" and got.event == event
    assert got.target.startswith(out + os.sep), got
    inside_only = tuple(
        a.format(out=inside, **{"in": inside}) if isinstance(a, str) else a
        for a in args
    )
    assert ig.classify(event, inside_only, _rule(), (inside,)) is None


def test_a_link_is_judged_by_its_destination_only(tmp_path):
    inside = _inside(tmp_path)
    out = str(_outside(tmp_path))
    rule = _rule()
    assert (
        ig.classify("os.symlink", (out + "/t", inside + "/l", -1), rule, (inside,))
        is None
    )
    assert (
        ig.classify("os.link", (out + "/t", inside + "/h", -1, -1), rule, (inside,))
        is None
    )


def test_removing_a_link_is_judged_by_the_link_not_what_it_points_at(tmp_path):
    inside = _inside(tmp_path)
    out = _outside(tmp_path)
    (out / "t").write_text("x")
    link = Path(inside) / "l"
    link.symlink_to(out / "t")
    assert ig.classify("os.remove", (str(link), -1), _rule(), (inside,)) is None
    # Writing THROUGH the link reaches its target, so an open follows it.
    got = ig.classify("open", (str(link), "w", 0), _rule(), (inside,))
    assert got is not None and got.target == str(out / "t")


def test_a_directory_descriptor_resolves_through_proc(tmp_path):
    inside = _inside(tmp_path)
    out = _outside(tmp_path)
    fd_out = os.open(str(out), os.O_RDONLY)
    fd_in = os.open(inside, os.O_RDONLY)
    try:
        got = ig.classify("os.remove", ("x", fd_out), _rule(), (inside,))
        assert got is not None and got.target == str(out / "x")
        assert ig.classify("os.remove", ("x", fd_in), _rule(), (inside,)) is None
        # No /proc to read the descriptor through: the reach is skipped.
        assert (
            ig.classify(
                "os.remove",
                ("x", fd_out),
                _rule(),
                (inside,),
                fd_dir=str(tmp_path / "no-proc"),
            )
            is None
        )
    finally:
        os.close(fd_out)
        os.close(fd_in)


def test_a_relative_path_resolves_against_the_working_directory(tmp_path, monkeypatch):
    inside = _inside(tmp_path)
    monkeypatch.chdir(inside)
    assert ig.classify("open", ("f", "w", 0), _rule(), (inside,)) is None
    got = ig.classify("open", ("../outside/f", "w", 0), _rule(), (inside,))
    assert got is not None and got.target == str(_outside(tmp_path) / "f")


@pytest.mark.parametrize(
    ("event", "args"),
    [
        ("os.chmod", ("{path}", 0o777, -1)),
        ("os.utime", ("{path}", None, None, -1)),
        ("os.chown", ("{path}", 0, 0, -1)),
        ("os.setxattr", ("{path}", "user.k", b"v", 0)),
        ("os.removexattr", ("{path}", "user.k")),
        ("os.chflags", ("{path}", 0)),
    ],
)
def test_a_metadata_change_outside_the_roots_is_a_writes_violation(
    tmp_path, event, args
):
    inside = _inside(tmp_path)
    out = _outside(tmp_path)

    def fill(path):
        return tuple(a.format(path=path) if isinstance(a, str) else a for a in args)

    got = ig.classify(event, fill(str(out / "f")), _rule(), (inside,))
    assert got is not None and (got.axis, got.event) == ("writes", event)
    assert got.target == str(out / "f")
    assert ig.classify(event, fill(inside + "/f"), _rule(), (inside,)) is None
    # A file descriptor names no path: fchmod and its kin are not placed.
    fd_args = (7,) + fill("x")[1:]
    assert ig.classify(event, fd_args, _rule(), (inside,)) is None
    # The event does not say whether the call follows a link, so a link
    # inside the roots that points outside is judged at both ends.
    (out / "t").write_text("x")
    link = Path(inside) / ("l-" + event)
    link.symlink_to(out / "t")
    got = ig.classify(event, fill(str(link)), _rule(), (inside,))
    assert got is not None and got.target == str(out / "t")
    assert ig.classify(event, fill(str(out / "f")), _rule(writes="any"), ()) is None


def test_a_call_that_stays_on_the_link_is_judged_at_the_link(tmp_path):
    inside = _inside(tmp_path)
    out = _outside(tmp_path)
    (out / "t").write_text("x")
    link = Path(inside) / "l"
    link.symlink_to(out / "t")
    args = (str(link), None, None, -1)
    got = ig.classify("os.utime", args, _rule(), (inside,))
    assert got is not None and got.target == str(out / "t")
    assert ig.classify("os.utime", args, _rule(), (inside,), follows=False) is None
    # Staying on the link does not move a link that is itself outside.
    outer = out / "l"
    outer.symlink_to(out / "t")
    got = ig.classify(
        "os.utime", (str(outer), None, None, -1), _rule(), (inside,), follows=False
    )
    assert got is not None and got.target == str(outer)


@pytest.mark.parametrize(
    "code, local, value, follows",
    [
        (shutil.copystat.__code__, "follow", False, False),
        (shutil.copystat.__code__, "follow", True, True),
        (shutil.copystat.__code__, "other", False, True),
        (shutil._copyxattr.__code__, "follow_symlinks", False, False),
        (shutil._copyxattr.__code__, "follow_symlinks", True, True),
        (shutil.copytree.__code__, "follow", False, True),
    ],
)
def test_only_a_link_aware_caller_saying_so_stays_on_the_link(
    code, local, value, follows
):
    frame = SimpleNamespace(f_code=code, f_locals={local: value})
    assert ig._caller_follows(frame) is follows
    assert ig._caller_follows(None) is True


def test_copying_a_tree_with_an_outbound_link_reaches_nothing(tmp_path):
    # Under the guard this suite runs with: shutil.copystat and its xattr
    # copy stay on a link when symlinks=True, so the checkout is not touched.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "link").symlink_to(_ROOT)
    (tmp_path / "src" / "f").write_text("x")
    shutil.copytree(str(tmp_path / "src"), str(tmp_path / "dst"), symlinks=True)
    assert os.readlink(str(tmp_path / "dst" / "link")) == str(_ROOT)


def test_a_metadata_change_through_a_directory_descriptor_is_placed(tmp_path):
    inside = _inside(tmp_path)
    out = _outside(tmp_path)
    fd_out = os.open(str(out), os.O_RDONLY)
    try:
        got = ig.classify("os.chmod", ("x", 0o644, fd_out), _rule(), (inside,))
        assert got is not None and got.target == str(out / "x")
        got = ig.classify("os.utime", ("x", None, None, fd_out), _rule(), (inside,))
        assert got is not None and got.target == str(out / "x")
    finally:
        os.close(fd_out)


def _fenced(tmp_path):
    """(roots, fenced, checkout): a root that holds the checkout."""
    holder = tmp_path / "holder"
    checkout = holder / "checkout"
    checkout.mkdir(parents=True)
    return (str(holder.resolve()),), (str(checkout.resolve()),), checkout.resolve()


def test_the_checkout_stays_outside_a_root_that_holds_it(tmp_path):
    roots, fenced, checkout = _fenced(tmp_path)
    target = str(checkout / "README.md")
    got = ig.classify("open", (target, "w", 0), _rule(), roots, fenced=fenced)
    assert got is not None and (got.axis, got.target) == ("writes", target)
    got = ig.classify("os.chmod", (target, 0o777, -1), _rule(), roots, fenced=fenced)
    assert got is not None and got.axis == "writes"
    got = ig.classify("sqlite3.connect", (target,), _rule(), roots, fenced=fenced)
    assert got is not None and got.axis == "stores"
    unix = (_sock(socket.AF_UNIX), str(checkout / "s"))
    got = ig.classify("socket.connect", unix, _rule(), roots, fenced=fenced)
    assert got is not None and got.axis == "network"
    # The rest of the root is still scratch.
    beside = roots[0] + "/beside.txt"
    assert ig.classify("open", (beside, "w", 0), _rule(), roots, fenced=fenced) is None
    assert ig.classify("open", (target, "w", 0), _rule(), roots) is None


def test_a_root_inside_the_checkout_is_scratch_again(tmp_path):
    roots, fenced, checkout = _fenced(tmp_path)
    basetemp = checkout / "bt"
    basetemp.mkdir()
    roots = roots + (str(basetemp),)
    target = str(basetemp / "f")
    assert ig.classify("open", (target, "w", 0), _rule(), roots, fenced=fenced) is None
    # A root that is the checkout itself is fenced: the fence wins a tie.
    same = (str(checkout),)
    got = ig.classify(
        "open", (str(checkout / "f"), "w", 0), _rule(), same, fenced=fenced
    )
    assert got is not None


def test_load_policy_fences_the_checkout(tmp_path):
    policy = _policy(tmp_path)
    assert policy.fenced == (os.path.realpath(str(tmp_path)),)


def test_writes_any_allows_a_write_anywhere(tmp_path):
    target = str(_outside(tmp_path) / "f")
    got = ig.classify(
        "open", (target, "w", 0), _rule(writes="any"), (_inside(tmp_path),)
    )
    assert got is None


# --- network -----------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        ("127.0.0.1", 80),
        ("127.5.5.5", 80),
        ("localhost", 80),
        ("::1", 80, 0, 0),
        ("::ffff:127.0.0.1", 80, 0, 0),
    ],
)
def test_loopback_is_allowed_under_loopback_and_refused_under_none(address):
    family = socket.AF_INET6 if len(address) == 4 else socket.AF_INET
    for event in ("socket.connect", "socket.sendto"):
        args = (_sock(family), address)
        assert ig.classify(event, args, _rule(network="loopback"), ()) is None
        got = ig.classify(event, args, _rule(network="none"), ())
        assert got is not None and got.axis == "network" and got.value == "none"
        assert got.target == repr(address)
        assert ig.classify(event, args, _rule(network="any"), ()) is None


def test_sendmsg_is_judged_by_its_address_and_a_connected_one_by_its_connect():
    routable = (_sock(socket.AF_INET), ("192.0.2.1", 9))
    loop = (_sock(socket.AF_INET), ("127.0.0.1", 9))
    got = ig.classify("socket.sendmsg", routable, _rule(network="none"), ())
    assert got is not None and (got.axis, got.event) == ("network", "socket.sendmsg")
    assert got.target == repr(("192.0.2.1", 9))
    assert ig.classify("socket.sendmsg", routable, _rule(network="loopback"), ())
    assert ig.classify("socket.sendmsg", loop, _rule(network="loopback"), ()) is None
    assert ig.classify("socket.sendmsg", loop, _rule(network="none"), ()) is not None
    assert ig.classify("socket.sendmsg", routable, _rule(network="any"), ()) is None
    # No address: the socket is connected, and its connect was judged; or it
    # is one end of a socketpair, whose peer is this process.
    for family in (socket.AF_INET, socket.AF_UNIX):
        connected = (_sock(family), None)
        assert ig.classify("socket.sendmsg", connected, _rule(), ()) is None


def test_binding_a_unix_socket_is_a_write_of_its_path(tmp_path):
    inside = _inside(tmp_path)
    out = str(_outside(tmp_path))
    unix = _sock(socket.AF_UNIX)
    got = ig.classify("socket.bind", (unix, out + "/s"), _rule(), (inside,))
    assert got is not None and (got.axis, got.target) == ("writes", out + "/s")
    assert ig.classify("socket.bind", (unix, inside + "/s"), _rule(), (inside,)) is None
    assert ig.classify("socket.bind", (unix, b"\0name"), _rule(), (inside,)) is None
    assert ig.classify("socket.bind", (unix, "\0name"), _rule(), (inside,)) is None
    assert (
        ig.classify("socket.bind", (unix, out + "/s"), _rule(writes="any"), (inside,))
        is None
    )


def test_a_v4_mapped_loopback_is_loopback_on_an_interpreter_that_says_not(
    monkeypatch,
):
    # Measured: ipaddress calls ::ffff:127.0.0.1 loopback on 3.11.15 and not
    # on 3.6.8; the guard must agree on both, so the older answer is planted.
    monkeypatch.setattr(
        ipaddress.IPv6Address,
        "is_loopback",
        property(lambda self: int(self) == 1),
    )
    address = ("::ffff:127.0.0.1", 80, 0, 0)
    args = (_sock(socket.AF_INET6), address)
    assert ig.classify("socket.connect", args, _rule(network="loopback"), ()) is None
    mapped_out = (_sock(socket.AF_INET6), ("::ffff:192.0.2.1", 9, 0, 0))
    assert ig.classify("socket.connect", mapped_out, _rule(network="loopback"), ())


@pytest.mark.parametrize(
    "address",
    [
        ("192.0.2.1", 9),
        ("example.com", 80),
        ("::ffff:192.0.2.1", 9, 0, 0),
        ("2001:db8::1", 9, 0, 0),
    ],
)
def test_any_other_host_is_refused_under_loopback(address):
    family = socket.AF_INET6 if len(address) == 4 else socket.AF_INET
    got = ig.classify(
        "socket.connect", (_sock(family), address), _rule(network="loopback"), ()
    )
    assert got is not None and got.value == "loopback"
    assert got.target == repr(address)


def test_a_unix_socket_is_judged_by_the_roots(tmp_path):
    inside = _inside(tmp_path)
    out = str(_outside(tmp_path))
    unix = _sock(socket.AF_UNIX)
    for network in ("none", "loopback"):
        rule = _rule(network=network)
        assert (
            ig.classify("socket.connect", (unix, inside + "/s"), rule, (inside,))
            is None
        )
        assert (
            ig.classify(
                "socket.connect", (unix, (inside + "/s").encode()), rule, (inside,)
            )
            is None
        )
        got = ig.classify("socket.connect", (unix, out + "/s"), rule, (inside,))
        assert got is not None and got.target == out + "/s"
        abstract = ig.classify("socket.connect", (unix, "\0name"), rule, (inside,))
        assert abstract is not None and abstract.axis == "network"


# --- stores ------------------------------------------------------------------


@pytest.mark.parametrize("name", [":memory:", "", b":memory:"])
def test_an_in_memory_database_is_allowed(name):
    assert ig.classify("sqlite3.connect", (name,), _rule(), ()) is None


@pytest.mark.parametrize("name", ["file::memory:?cache=shared", "file:x?mode=memory"])
def test_a_file_name_is_judged_as_the_literal_file_sqlite_opens_without_uri(
    tmp_path, monkeypatch, name
):
    inside = _inside(tmp_path)
    out = _outside(tmp_path)
    # Without uri=True sqlite opens the name as a file in the working
    # directory, and the event does not carry the flag.
    monkeypatch.chdir(str(out))
    got = ig.classify("sqlite3.connect", (name,), _rule(), (inside,))
    assert got is not None and got.axis == "stores"
    assert got.target == str(out / name)
    monkeypatch.chdir(inside)
    assert ig.classify("sqlite3.connect", (name,), _rule(), (inside,)) is None


def test_a_database_outside_the_roots_is_a_stores_violation(tmp_path, monkeypatch):
    inside = _inside(tmp_path)
    out = _outside(tmp_path)
    # A `file:` name's literal reading lands in the working directory.
    monkeypatch.chdir(inside)
    for name in (str(out / "a.db"), (str(out / "a.db")).encode(), out / "a.db"):
        got = ig.classify("sqlite3.connect", (name,), _rule(), (inside,))
        assert got is not None
        assert (got.axis, got.event, got.target, got.value) == (
            "stores",
            "sqlite3.connect",
            str(out / "a.db"),
            "temp",
        )
    uri = "file:%s?mode=ro" % (out / "a%20b.db")
    got = ig.classify("sqlite3.connect", (uri,), _rule(), (inside,))
    assert got is not None and got.target == str(out / "a b.db")
    assert (
        ig.classify("sqlite3.connect", (inside + "/a.db",), _rule(), (inside,)) is None
    )
    assert (
        ig.classify("sqlite3.connect", ("file:%s/a.db" % inside,), _rule(), (inside,))
        is None
    )
    assert (
        ig.classify(
            "sqlite3.connect", (str(out / "a.db"),), _rule(stores="any"), (inside,)
        )
        is None
    )


def test_a_listed_store_is_refused_in_any_mode_unless_the_copy_reads_it(tmp_path):
    inside = _inside(tmp_path)
    store = str(_outside(tmp_path) / "live.db")
    stores = (store,)
    got = ig.classify("open", (store, "rb", 0), _rule(), (inside,), stores=stores)
    assert got is not None and (got.axis, got.event) == ("stores", "open")
    got = ig.classify(
        "open", (store + "-wal", "r", 0), _rule(), (inside,), stores=stores
    )
    assert got is not None and got.axis == "stores"
    allowed = ig.classify(
        "open", (store, "rb", 0), _rule(), (inside,), stores=stores, readable=(store,)
    )
    assert allowed is None
    # The allowance is for reading: a write to the store is still refused.
    still = ig.classify(
        "open", (store, "wb", 0), _rule(), (inside,), stores=stores, readable=(store,)
    )
    assert still is not None


def test_an_event_the_guard_does_not_judge_is_none(tmp_path):
    assert ig.classify("os.listdir", (str(tmp_path),), _rule(), ()) is None
    assert (
        ig.classify("socket.bind", (_sock(socket.AF_INET), ("0.0.0.0", 0)), _rule(), ())
        is None
    )


# --- the message and the tier ------------------------------------------------


def test_the_message_has_its_fixed_shape():
    v = ig.Violation(
        "open",
        "/srv/x",
        "writes",
        "temp",
        nodeid="tests/unit/t.py::test_a",
        phase="call",
        tier="unit",
    )
    assert v.message() == (
        "tests/unit/t.py::test_a [call] reached outside its tier 'unit': open /srv/x "
        "(writes=temp). Use tmp_path or the store_copy fixture; or exempt it with a "
        'reason in config/project.json tests.isolation.exempt.writes."tests/unit/t.py::test_a"'
    )


def _policy(tmp_path, tiers=None, exempt=None, stores=None):
    _write_config(tmp_path, tiers=tiers, exempt=exempt, stores=stores)
    return ig.load_policy(str(tmp_path))


def _write_config(tmp_path, tiers=None, exempt=None, stores=None, drop=()):
    isolation = {
        "tiers": _FULL if tiers is None else tiers,
        "exempt": {"network": {}, "writes": {}, "stores": {}}
        if exempt is None
        else exempt,
        "stores": [] if stores is None else stores,
    }
    for key in drop:
        del isolation[key]
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"tests": {"isolation": isolation}}), encoding="utf-8"
    )


def test_the_closest_tier_marker_wins(tmp_path):
    policy = _policy(tmp_path)
    assert ig.rule_for(policy, ["integration", "unit"]).tier == "integration"
    assert ig.rule_for(policy, ["parametrize", "unit", "integration"]).tier == "unit"
    assert ig.rule_for(policy, ["integration"]).network == "loopback"


def test_an_unmarked_test_gets_the_strictest_rule(tmp_path):
    policy = _policy(tmp_path)
    for names in ([], ["slow"], ["smoke"]):
        rule = ig.rule_for(policy, names)
        assert (rule.network, rule.writes, rule.stores) == ("none", "temp", "temp")
    assert (ig.STRICTEST.network, ig.STRICTEST.writes, ig.STRICTEST.stores) == (
        "none",
        "temp",
        "temp",
    )


def _declared_markers(pytestconfig):
    """The marker names the project's pytest ini declares, read by pytest."""
    return {
        line.split(":", 1)[0].split("(", 1)[0].strip()
        for line in pytestconfig.getini("markers")
    }


def test_this_projects_policy_loads_a_rule_per_configured_tier(pytestconfig):
    policy = ig.load_policy(str(_ROOT))
    key = ("tests", "isolation", "tiers")
    rows = config_loader.resolve(
        config_loader.read(str(_ROOT)),
        config_loader.rows(key),
        config_loader.CONFIG_FILE,
    )[key]
    assert rows, "no tier row in config/project.json -- zero items"
    assert {
        tier: (rule.network, rule.writes, rule.stores)
        for tier, rule in policy.tiers.items()
    } == {
        tier: (row["network"], row["writes"], row["stores"])
        for tier, row in rows.items()
    }
    # A tier no marker declares could never pick a rule.
    declared = _declared_markers(pytestconfig)
    assert set(policy.tiers) <= declared, sorted(set(policy.tiers) - declared)
    assert policy.roots, "no root a test may write under -- zero items"


def test_load_policy_resolves_stores_against_the_project(tmp_path):
    policy = _policy(tmp_path, stores=["data/live.db", "/abs/x.db"])
    assert policy.stores == (
        os.path.realpath(str(tmp_path / "data" / "live.db")),
        "/abs/x.db",
    )


@pytest.mark.parametrize(
    ("tiers", "key"),
    [
        (
            {"unit": {"network": "nowhere", "writes": "temp", "stores": "temp"}},
            "tests.isolation.tiers.unit.network",
        ),
        (
            {"unit": {"network": "none", "writes": "temp"}},
            "tests.isolation.tiers.unit.stores",
        ),
        (
            {
                "unit": {
                    "network": "none",
                    "writes": "temp",
                    "stores": "temp",
                    "disk": "x",
                }
            },
            "tests.isolation.tiers.unit.disk",
        ),
        ({"unit": "strict"}, "tests.isolation.tiers.unit"),
    ],
)
def test_load_policy_refuses_an_unknown_tier_value_naming_the_key(tmp_path, tiers, key):
    _write_config(tmp_path, tiers=tiers)
    with pytest.raises(ig.ConfigError) as caught:
        ig.load_policy(str(tmp_path))
    assert key in str(caught.value)


@pytest.mark.parametrize("reason", ["", "   "])
def test_load_policy_refuses_a_blank_reason(tmp_path, reason):
    nodeid = "tests/unit/t.py::test_a"
    _write_config(tmp_path, exempt={"writes": {nodeid: reason}})
    with pytest.raises(ig.ConfigError) as caught:
        ig.load_policy(str(tmp_path))
    assert 'tests.isolation.exempt.writes."%s"' % nodeid in str(caught.value)


def test_load_policy_refuses_an_unknown_axis_and_a_missing_table(tmp_path):
    _write_config(tmp_path, exempt={"disk": {}})
    with pytest.raises(ig.ConfigError) as caught:
        ig.load_policy(str(tmp_path))
    assert "tests.isolation.exempt.disk" in str(caught.value)
    _write_config(tmp_path, drop=("tiers",))
    with pytest.raises(ig.ConfigError) as caught:
        ig.load_policy(str(tmp_path))
    assert "tests.isolation.tiers" in str(caught.value)


def test_an_exempt_axis_left_out_exempts_nothing(tmp_path):
    policy = _policy(tmp_path, exempt={"writes": {"t::a": "a reason"}})
    assert policy.exempt == {
        "network": {},
        "writes": {"t::a": "a reason"},
        "stores": {},
    }


def test_install_is_idempotent():
    # conftest installed the guard when this session started.
    assert ig.install(ig.load_policy(str(_ROOT))) is False


# --- the store copy ----------------------------------------------------------


def _store(tmp_path):
    live = _outside(tmp_path) / "live.db"
    live.write_bytes(b"main")
    (live.parent / "live.db-wal").write_bytes(b"wal")
    return live


def test_a_listed_store_is_copied_with_its_siblings(tmp_path):
    live = _store(tmp_path)
    policy = _policy(tmp_path, stores=[str(live)])
    dest = tmp_path / "t" / "stores"
    got = ig.copy_store(policy, str(tmp_path), str(live), str(dest))
    assert got == dest / "live.db"
    assert got.read_bytes() == b"main"
    assert (dest / "live.db-wal").read_bytes() == b"wal"
    assert not (dest / "live.db-shm").exists()
    assert sorted(p.name for p in dest.iterdir()) == ["live.db", "live.db-wal"]


def test_a_second_store_copy_changes_nothing(tmp_path):
    live = _store(tmp_path)
    policy = _policy(tmp_path, stores=[str(live)])
    dest = tmp_path / "t" / "stores"
    ig.copy_store(policy, str(tmp_path), str(live), str(dest))
    first = {p.name: p.read_bytes() for p in dest.iterdir()}
    ig.copy_store(policy, str(tmp_path), str(live), str(dest))
    assert {p.name: p.read_bytes() for p in dest.iterdir()} == first


def test_an_unlisted_or_absent_store_is_refused_naming_the_key(tmp_path):
    live = _store(tmp_path)
    policy = _policy(tmp_path, stores=[str(live.with_name("gone.db"))])
    for name in (str(live), str(live.with_name("gone.db"))):
        with pytest.raises(ig.StoreError) as caught:
            ig.copy_store(policy, str(tmp_path), name, str(tmp_path / "d"))
        assert "tests.isolation.stores" in str(caught.value)


# --- the scratch root --------------------------------------------------------

_SCRATCH_VAR = "KEEL_TEST_SCRATCH"


def _scratch_config(tmp_path, value):
    checkout = tmp_path / "checkout"
    (checkout / "config").mkdir(parents=True)
    (checkout / "config" / "project.json").write_text(
        json.dumps({"tests": {"scratch_root": value}}), encoding="utf-8"
    )
    return str(checkout)


def _systemp(tmp_path):
    systemp = tmp_path / "systemp"
    systemp.mkdir(exist_ok=True)
    return str(systemp.resolve())


def test_the_scratch_root_is_the_configured_path_with_home_expanded(tmp_path):
    systemp = _systemp(tmp_path)
    absolute = str((tmp_path / "scratch").resolve())
    checkout = _scratch_config(tmp_path, absolute)
    assert ig.scratch_root(checkout, {}, systemp) == absolute
    tilde = "~/keel-unit-scratch-that-is-never-made"
    (Path(checkout) / "config" / "project.json").write_text(
        json.dumps({"tests": {"scratch_root": tilde}}), encoding="utf-8"
    )
    assert ig.scratch_root(checkout, {}, systemp) == os.path.realpath(
        os.path.expanduser(tilde)
    )
    assert not os.path.exists(os.path.expanduser(tilde))


def test_an_empty_variable_leaves_the_configured_root(tmp_path):
    configured = str((tmp_path / "configured").resolve())
    checkout = _scratch_config(tmp_path, configured)
    got = ig.scratch_root(checkout, {_SCRATCH_VAR: ""}, _systemp(tmp_path))
    assert got == configured
    with pytest.raises(ig.ConfigError) as caught:
        ig.scratch_root(checkout, {_SCRATCH_VAR: ""}, os.path.dirname(configured))
    assert _SCRATCH_VAR not in str(caught.value), str(caught.value)


def test_a_root_that_holds_the_checkout_is_accepted(tmp_path):
    checkout = _scratch_config(tmp_path, str(tmp_path.resolve()))
    assert ig.scratch_root(checkout, {}, _systemp(tmp_path)) == str(tmp_path.resolve())


def test_the_variable_wins_over_the_configured_root(tmp_path):
    checkout = _scratch_config(tmp_path, str(tmp_path / "configured"))
    chosen = str((tmp_path / "chosen").resolve())
    got = ig.scratch_root(checkout, {_SCRATCH_VAR: chosen}, _systemp(tmp_path))
    assert got == chosen


@pytest.mark.parametrize(
    "where", ["relative", "parent-part", "system-temp", "checkout"]
)
@pytest.mark.parametrize("source", ["config", "variable"])
def test_a_scratch_root_that_is_unsafe_is_refused_naming_the_key(
    tmp_path, where, source
):
    systemp = _systemp(tmp_path)
    base = tmp_path / source
    checkout = str(base / "checkout")
    value = {
        "relative": "scratch",
        "parent-part": str(tmp_path / "a" / ".." / "b"),
        "system-temp": os.path.join(systemp, "x"),
        "checkout": os.path.join(checkout, "scratch"),
    }[where]
    if source == "config":
        _scratch_config(base, value)
        environ = {}
    else:
        _scratch_config(base, str(tmp_path / "configured"))
        environ = {_SCRATCH_VAR: value}
    with pytest.raises(ig.ConfigError) as caught:
        ig.scratch_root(checkout, environ, systemp)
    assert "tests.scratch_root" in str(caught.value), str(caught.value)
    if source == "variable":
        assert _SCRATCH_VAR in str(caught.value), str(caught.value)
    assert sorted(os.listdir(systemp)) == []


def test_an_absent_scratch_root_is_refused_naming_the_key(tmp_path):
    checkout = tmp_path / "checkout"
    (checkout / "config").mkdir(parents=True)
    (checkout / "config" / "project.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ig.ConfigError) as caught:
        ig.scratch_root(str(checkout), {}, _systemp(tmp_path))
    assert "tests.scratch_root" in str(caught.value)


def test_pointing_temp_at_the_root_twice_changes_nothing_more(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", tempfile.tempdir)
    root = str((tmp_path / "scratch").resolve())
    environ = {"GIT_CEILING_DIRECTORIES": "/an/outer/ceiling"}
    ig.point_temp_at(root, environ)
    first = dict(environ)
    assert os.path.isdir(root)
    assert tempfile.tempdir == root
    assert first["TMPDIR"] == root
    # A nested session inherits the root rather than reading its own config.
    assert first[_SCRATCH_VAR] == root
    assert first["GIT_CEILING_DIRECTORIES"] == os.pathsep.join(
        ["/an/outer/ceiling", root]
    )
    ig.point_temp_at(root, environ)
    assert environ == first
    assert sorted(os.listdir(str(tmp_path))) == ["scratch"]
