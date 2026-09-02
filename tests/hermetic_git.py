"""
title: Test helper — a git environment that ignores the developer's machine
kind: tests
layer: n/a
summary: One canonical hermetic git config for every test that shells out to git or lets copier do it. Neutralises global + system config AND `core.excludesFile`, whose default value git reads from $XDG_CONFIG_HOME/git/ignore with no config entry at all — so GIT_CONFIG_GLOBAL/SYSTEM alone do not reach it and a single `*.yml` line on someone's laptop fails a correct tree.
"""

import os

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
