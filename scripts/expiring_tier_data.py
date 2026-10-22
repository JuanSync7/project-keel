"""
title: expiring_tier_data — the ceiling date and the checks of the tier for a project's own code
kind: script
layer: n/a
summary: Data, not logic (CONVENTIONS §18). `CEILING` is the latest date config/project.json `expiring_tier.expires` may hold: a generated project may set an earlier one, and scripts/expiring_tier.py refuses a later one. `CHECKS` maps each check id that adopts the tier to the pytest node id of the gate test that hands it its findings, which scripts/record_gate_baseline.py runs to record a baseline. keel owns this file and copier rewrites it on every update, so a project's edit to it shows as a diff or a conflict on the next update; nothing inside a repository stops a determined edit. Imports nothing, reads nothing and writes nothing.
effect: read-only
"""

__all__ = ["CEILING", "CHECKS"]

# The date the maintainer ruled (docs/design/downstream-feedback.md, rulings 9
# and 10): from this day a project's own code that breaks a keel gate check is
# red, whatever its baseline records.
CEILING = "2027-01-31"

_CONFIG_READS = "tests/integration/test_config_reads_gate.py::"
_EXIT = "tests/integration/test_exit_gate.py::"

CHECKS = {
    "config-reads-file": _CONFIG_READS
    + "test_no_code_root_reads_a_config_file_outside_the_loader",
    "config-reads-variable": _CONFIG_READS
    + "test_no_code_root_reads_a_declared_variable_outside_the_loader",
    "exit-helper": _EXIT + "test_no_process_in_the_tree_ends_outside_the_helper",
    "exit-shared-module": _EXIT + "test_a_shared_module_never_ends_the_process",
}
