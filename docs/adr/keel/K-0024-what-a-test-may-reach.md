---
title: "ADR-K-0024: what a test may reach"
kind: adr
layer: n/a
status: proposed
owner: TBD
tags: [adr, tests, isolation, scratch, guard]
summary: "A test's rule for the network, writes and stores is a row of config/project.json tests.isolation.tiers, picked by the test's closest tier marker, and tests/isolation_guard.py, which tests/conftest.py installs as a Python audit hook, fails a test that reaches past it, even when the test caught the error. A reach a test needs is a per-test exemption with a reason, and an unused one is red. Test scratch lives in a per-user memory directory, tests.memory_scratch_root, when the host can hold it, else under tests.scratch_root, never the system temporary directory or the checkout. Defence-in-depth, not a sandbox: a child process is not audited."
id: docs-adr-0024-what-a-test-may-reach
created: 2026-10-18
updated: 2026-10-24
visibility: internal
canonical: true
---

# ADR-K-0024: what a test may reach

**Status:** proposed. It edits no other ADR. It takes the stance of
[ADR-K-0012](K-0012-child-process-environment-allowlist.md), which is
accepted: a rule enforced inside the process is defence-in-depth, not a
sandbox, and says so.

## Context

`tests/AGENT.md` said that a unit test touches no network, disk or process,
and nothing in the suite refused one that did. A unit test that reaches a live
database changes it, and nothing stops it. keel ships its `tests/` scaffolding into every generated project,
so a guard keel lacks, every generated project lacks too.

Test scratch went to the system temporary directory. About 80 test files used
`tmp_path` with no configured basetemp, and the hermetic git directory of
`tests/conftest.py` was made there too. Where that directory is
memory-backed and shared, the directories failed runs keep fill it.

When the guard was first run over keel's suite, it found four tests in
`tests/integration/test_practice_refactor.py` writing refactor checkpoints
under the checkout's `wiki/.runtime`. Each now passes a `FileCheckpointer`
under its own `tmp_path`, so the suite ships with no exemption.

## Decision

1. **A tier's rule lives in config, on three axes.** config/project.json
   `tests.isolation.tiers` maps a tier marker to a value on each of three
   axes:
   - `network`: `none`, `loopback` or `any`;
   - `writes`: `temp` or `any`;
   - `stores`: `temp` or `any`.

   keel ships the following rules:
   - `unit`: no network, writes under scratch only, and no live store;
   - `integration` and `e2e`: the same, except that loopback is allowed, which
     `tests/live_server.py` needs;
   - `smoke`: any network.

   The closest tier marker on a test picks the row. A test with no tier marker
   gets the strictest value on every axis.
2. **The test process judges itself.** `tests/isolation_guard.py` is a Python
   audit hook, which `tests/conftest.py` installs once per process, before any
   test module is imported. It judges each test's setup, call and teardown,
   and raises `IsolationError` at the reach. `IsolationError` is not an
   `OSError`, so a handler that catches I/O failures does not catch it. After
   each phase, `tests/conftest.py` fails the test for every violation it
   recorded. It does this even when the test caught the error, and an `xfail`
   does not hide a violation. The failure line names the test, the phase, the
   tier, the event, the target and the fix.
3. **An exemption is config, per test and axis, with a reason.**
   `tests.isolation.exempt.<axis>` maps a node id to the reason that test may
   reach outside its tier on that axis. There is no marker and no blanket
   switch. A blank reason stops pytest before any test runs. An exemption
   whose test ran and reached nothing on its axis fails the run, so an
   exemption cannot outlive its reason.
4. **A live store is reached through a copy.** `tests.isolation.stores` lists
   the project's live stores. An open of a listed store, in any mode, is a
   violation. The `store_copy` fixture copies a listed store into the test's
   own directory, together with its `-wal`, `-shm` and `-journal` siblings.
5. **Scratch prefers memory, and falls back to one configured disk root.**
   `tests/conftest.py` points `tempfile`, `TMPDIR` and pytest's basetemp,
   before anything else is made, at the first root that applies:
   `KEEL_TEST_SCRATCH`; `tests.memory_scratch_root` with `-<uid>` appended;
   `tests.scratch_root`.
   - Memory comes first because test scratch is thrown away within seconds
     and needs no durability. Measured on a host whose home directory is a
     network mount, with scratch there: the processors were 28% busy and 25%
     waiting on I/O, and one copier render took 9.8 s while copying its
     output took 0.03 s.
   - The memory root is taken only when its parent exists, its file system
     has `tests.memory_scratch_min_free_mb` free at session start, the parent
     is not writable by other users without the sticky bit, and the directory
     is this user's with mode 0700, made so when absent, because a memory
     directory such as `/dev/shm` is writable by every user. A link at the
     configured name is never followed, so no other user can make the root
     refused for everyone.
     Otherwise the session falls back to `tests.scratch_root`, and pytest's
     `scratch:` header line names the root in use and why.
   - It is not the system temporary directory: that is shared with every
     program, while the memory root is the project's own, with a floor.
   - It refuses, before any test runs, a root that is relative, has a `..`
     part, sits under the system temporary directory, or sits inside the
     checkout.
   - It accepts a root that holds the checkout, because a nested session
     inherits its caller's root, and keeps the checkout outside it: of the
     roots and the checkout, the deepest that holds a path decides.
   - `pyproject.toml` keeps a failed test's directory and removes a passed
     one's.
   - `child_env.names` carries `KEEL_TEST_SCRATCH`, so a nested pytest keeps
     its caller's root.

## Consequences

- A test that writes into the checkout, opens a database outside its scratch
  or connects to a remote host fails in the change that adds it. It does not
  fail later, in the store it damaged.
- The guard sees only what a Python audit event carries, in the pytest
  process. It does not see:
  - a write, socket or store opened by a child process;
  - a C extension's own file or socket calls;
  - a FIFO or device node, because `os.mkfifo` and `os.mknod` raise no
    event;
  - the directory an `os.open` with a relative path and a `dir_fd` lands in,
    because the open event does not carry the `dir_fd`; the path is judged
    against the working directory.

  It does not judge a name lookup, by choice: library code looks names up
  without reaching anywhere, and the connect that follows is judged. The
  `sqlite3.connect` event does not say whether a call passed `uri=True`, so
  a name that starts `file:` is judged both as a URI and as a file in the
  working directory; a test that opens a `file:` URI changes directory to its
  `tmp_path` first.

  A test that runs `make`, git or a nested pytest is unjudged inside that
  child.
- The shipped scratch root, `~/.cache/project_keel/tests`, is under the home
  directory. Where the home directory is a network mount, the suite is slower
  and file times can differ. `KEEL_TEST_SCRATCH` moves the root to local
  disk.
- A project that adds a store lists it in `tests.isolation.stores`, and its
  tests reach the store through `store_copy`.

## Alternatives considered

- **Keep the rule as prose.** Rejected: a rule in prose refuses nothing, so
  it does not stop a test that reaches a live store.
- **Monkeypatch `socket`, `open` and `sqlite3` per test.** Rejected:
  - a patch misses another name bound to the same function, such as `io.open`
    or `os.open`;
  - a patch can leak across tests when a teardown fails;
  - the audit hook sees each of those calls at one event, and needs no
    restore.
- **A plugin such as a socket-blocking package.** Rejected: it covers the
  network only, adds a dependency to every generated project, and has no
  per-test reasoned exemption with an unused-exemption check.
- **Run each test in an OS sandbox (a namespace or a container).** Rejected:
  it costs a process per test, needs privileges a shared host does not grant,
  and is not portable to every host a generated project runs on.
- **A `--basetemp` in `addopts`.** Rejected: pytest empties a given basetemp
  at the start of each session, so two sessions that share it, such as a
  nested pytest, would delete each other's files.

## Scope cuts

Not built:
- auditing a child process, for example with a `sitecustomize` the child
  imports;
- a judgement under pytest-xdist, which the suite did not use when this was
  decided; `make test` has since run on workers, and the controller judges
  the unused exemptions over every worker's record (`tests/README.md`);
- a live store in keel itself, so `store_copy` has no consumer in keel's own
  suite.
