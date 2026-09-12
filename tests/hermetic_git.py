"""
title: Test helper — a git environment that ignores the developer's machine
kind: tests
layer: n/a
summary: One canonical hermetic git config for every test that shells out to git or lets copier do it. Neutralises global + system config AND `core.excludesFile`, whose default value git reads from $XDG_CONFIG_HOME/git/ignore with no config entry at all — so GIT_CONFIG_GLOBAL/SYSTEM alone do not reach it and a single `*.yml` line on someone's laptop fails a correct tree.
"""

import os
import subprocess

# Every knob below broke a real run, or would have:
#   user.*             — `git commit` refuses without an identity
#   init.defaultBranch — assertions that name `main`
#   commit/tag.gpgSign — a signing prompt hangs the suite
#   core.fsmonitor     — a stale daemon reports phantom changes
#   gc.auto            — background gc racing a throwaway repo
#   core.excludesFile  — THE subtle one. It is not merely "another config key":
#     git falls back to $XDG_CONFIG_HOME/git/ignore (i.e. ~/.config/git/ignore)
#     as this key's DEFAULT, so replacing global+system config leaves it live.
#     `git add -A` then silently skips files the test expects to be staged and
#     the failure surfaces far away, as a false red on a correct tree.
#     Pinning it at os.devnull is what actually disarms the XDG fallback.
HERMETIC_GITCONFIG = (
    "[user]\n\tname = Keel Test\n\temail = keel-test@example.invalid\n"
    "[init]\n\tdefaultBranch = main\n"
    "[commit]\n\tgpgsign = false\n"
    "[tag]\n\tgpgSign = false\n"
    "[core]\n\texcludesFile = %s\n\tfsmonitor = false\n"
    "[gc]\n\tauto = 0\n"
) % os.devnull


def git_env_vars(work_dir):
    """Write the hermetic config under work_dir; return the env vars that select it.

    Returned as a plain dict so a caller can either splice it into a subprocess
    `env=` (see `git_env`) or feed it to `monkeypatch.setenv` when the git calls
    are made by a library — copier shells out to git itself, so the
    neutralisation has to be the environment, not `git -c`.
    """
    cfg = os.path.join(str(work_dir), "gitconfig")
    with open(cfg, "w", encoding="utf-8") as fh:
        fh.write(HERMETIC_GITCONFIG)
    return {
        "GIT_CONFIG_GLOBAL": cfg,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }


def git_env(work_dir):
    """The current environment plus `git_env_vars` — ready for subprocess `env=`."""
    env = dict(os.environ)
    env.update(git_env_vars(work_dir))
    return env


def clone_including_worktree(src, dest, work):
    """Clone the repo at *src* into *dest* INCLUDING its uncommitted working tree.

    `git clone` carries only HEAD, so an edit you have not committed yet is
    invisible to the template a generation test actually exercises. That is not
    hypothetical: a whole `_migrations` block sat in the working tree while the
    update suite ran against a clone that had none, so the migrations "silently
    did nothing" — they did not exist. The symptom (a feature that no-ops) looks
    nothing like the cause (the harness tests a different tree), which is what
    made it expensive.

    So replay the working-tree diff as a real commit in the clone: what you are
    editing is what gets tested. On a clean tree — CI, and any run after you
    commit — the patch is empty and this is exactly a plain clone.

    `git diff HEAD` covers modifications, deletions and files already `git add`ed;
    a brand-new file that has never been staged is still invisible, so `git add`
    it before expecting a test to see it.

    The clone is also a CLEAN checkout, which is the condition generation
    determinism is stated under: copier renders a dirty template by committing it
    afresh each run, and two such commits differ in their sha (see
    docs/guides/idempotency.md §6). `make new` refuses a dirty template for the
    same reason.
    """

    def _git(*argv, **kwargs):
        cwd = kwargs.pop("cwd")
        r = subprocess.run(
            ("git",) + argv, cwd=str(cwd), capture_output=True, text=True
        )
        assert r.returncode == 0, "git %s failed:\n%s%s" % (
            " ".join(argv),
            r.stdout,
            r.stderr,
        )
        return r.stdout

    _git("clone", "--quiet", "--no-hardlinks", str(src), str(dest), cwd=work)
    patch = subprocess.run(
        ("git", "diff", "HEAD", "--binary"), cwd=str(src), capture_output=True
    )
    assert patch.returncode == 0, patch.stderr.decode("utf-8", "replace")
    if patch.stdout.strip():
        applied = subprocess.run(
            ("git", "apply", "--index", "-"),
            cwd=str(dest),
            input=patch.stdout,
            capture_output=True,
        )
        assert applied.returncode == 0, (
            "could not replay the working tree onto its clone:\n"
            + applied.stderr.decode("utf-8", "replace")
        )
        _git("commit", "--quiet", "-m", "uncommitted working tree under test", cwd=dest)
    return dest
