#!/bin/sh
# title: exit_codes.sh — the exit codes, and the two ways a shell script ends through them
# summary: Generated from the ExitCode enum of scripts/exit_codes.py by `make exit-codes-sh`; do not edit it, because `make check-exit-codes` fails a copy the enum has moved past. Source it (`. scripts/exit_codes.sh`), then end with `exit "$EXIT_<NAME>"`, with `exit_fail "$EXIT_<NAME>" WHAT ON NEXT` for a failure, which prints `WHAT: ON; NEXT` to stderr first, or with `exit_passthrough "$status"` for a wrapped tool's status. Inside `$(...)` either one ends only that subshell.
# effect: read-only
# shellcheck shell=sh disable=SC2034

# it ran and found nothing wrong, or it skipped and said why -- nothing
EXIT_SUCCESS=0

# it ran and the answer is no: a check found something, or the work did not succeed -- read the last stderr line, fix what it names, and run it again
EXIT_FAILURE=1

# it refused before judging: wrong usage, bad config, or an input it could not read -- correct the call or the input the last stderr line names, and run it again
EXIT_USAGE=2

# every step it ran passed, and the record it wrote of the run says fail -- read `reasons` in the record the last stderr line names, fix what they name, and run it again
EXIT_RED_RECORD=10

# the backend it was told to use did not answer, so nothing was judged -- start or configure the backend the last stderr line names, and run it again
EXIT_BACKEND_ABSENT=11

# nothing ran: the farm did not start the job within the wait bound and this host had no spare compute -- run it again later, or raise config/project.json launcher.farm.wait_seconds
EXIT_NO_CAPACITY=12

# it ran and found no item to judge, so it cannot answer yes -- give it something to judge, as the last stderr line names, then run it again
EXIT_NOTHING_JUDGED=13

# it refused before judging: a config value is missing or wrong, in config/project.json or a variable it declares -- set or correct each key a `[not set]` or `accepted:` line on stderr names, then run it again
EXIT_CONFIG=14

# it was interrupted before it finished -- run it again; what it had written so far is not a result
EXIT_INTERRUPTED=130

# Refuse a misuse of this helper: the message on stderr, then EXIT_USAGE.
_exit_codes_refuse() {
    printf '%s\n' "$1" >&2
    exit "$EXIT_USAGE"
}

# End the script with CODE, a member other than SUCCESS, after printing
# `WHAT: ON; NEXT` to stderr: what failed, on which input, what to do next.
exit_fail() {
    if [ "$#" -ne 4 ]; then
        _exit_codes_refuse "exit_fail: takes four arguments, CODE WHAT ON NEXT, and got $#"
    fi
    case "$1" in
    "$EXIT_FAILURE" | "$EXIT_USAGE" | "$EXIT_RED_RECORD" | "$EXIT_BACKEND_ABSENT" | "$EXIT_NO_CAPACITY" | "$EXIT_NOTHING_JUDGED" | "$EXIT_CONFIG" | "$EXIT_INTERRUPTED") ;;
    *) _exit_codes_refuse "exit_fail: $1 is not a failure member; pass \"\$EXIT_<NAME>\" for a member other than SUCCESS" ;;
    esac
    for _exit_codes_part in "$2" "$3" "$4"; do
        case "$_exit_codes_part" in
        *[![:space:]]*) ;;
        *) _exit_codes_refuse "exit_fail: a message part is blank; say what failed, on which input and what to do next" ;;
        esac
    done
    printf '%s: %s; %s\n' "$2" "$3" "$4" >&2
    exit "$1"
}

# End the script with STATUS, the status a wrapped tool exited with.
exit_passthrough() {
    if [ "$#" -ne 1 ]; then
        _exit_codes_refuse "exit_passthrough: takes one argument, the wrapped tool status, and got $#"
    fi
    # Four digits or more is refused before `[` could overflow on it.
    case "$1" in
    '' | *[!0-9]* | ????*) _exit_codes_refuse "exit_passthrough: $1 is not a status from 0 to 255" ;;
    esac
    if [ "$1" -gt 255 ]; then
        _exit_codes_refuse "exit_passthrough: $1 is not a status from 0 to 255"
    fi
    exit "$1"
}
