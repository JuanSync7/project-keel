"""
title: checks_data — the closed structure-check identity registry
kind: script
layer: n/a
summary: One id, enforcement sentence and pytest fault-injection twin for each dispatched structure check. Data under CONVENTIONS section 18, following audit_dependencies_data.py. Imports nothing, reads nothing and writes nothing.
effect: read-only
"""

__all__ = ["CHECKS"]

CHECKS = (
    {
        "id": "CHECK-A",
        "check": "check_A",
        "enforces": "Governed documents have valid frontmatter and visibility.",
        "twin": "tests/unit/scripts/test_check_a.py::test_check_a_reports_the_contradiction_over_a_tree",
    },
    {
        "id": "CHECK-B",
        "check": "check_B",
        "enforces": "Top-level directories belong to the taxonomy and carry labels.",
        "twin": "tests/unit/scripts/test_check_b.py::test_a_taxonomy_directory_without_a_label_errors",
    },
    {
        "id": "CHECK-C",
        "check": "check_C",
        "enforces": "Python source directories declare a package and public API.",
        "twin": "tests/unit/scripts/test_check_faults.py::test_missing_package_boundary_fails",
    },
    {
        "id": "CHECK-D",
        "check": "check_D",
        "enforces": "Callers respect private package boundaries.",
        "twin": "tests/unit/scripts/test_check_d.py::test_a_private_submodule_imported_from_outside_its_package_errors",
    },
    {
        "id": "CHECK-E",
        "check": "check_E",
        "enforces": "Exported symbols defined in a module carry docstrings.",
        "twin": "tests/unit/scripts/test_check_o.py::test_exported_symbol_without_docstring_is_an_error_now",
    },
    {
        "id": "CHECK-F",
        "check": "check_F",
        "enforces": "Tool specifications and accountability fields satisfy their contracts.",
        "twin": "tests/unit/scripts/test_check_f.py::test_a_tree_with_a_tbd_agent_and_no_default_errs_in_f",
    },
    {
        "id": "CHECK-G",
        "check": "check_G",
        "enforces": "Tool specifications and agent manifests agree on their bindings.",
        "twin": "tests/unit/scripts/test_config_loaders.py::test_unreadable_tool_spec_is_reported",
    },
    {
        "id": "CHECK-H",
        "check": "check_H",
        "enforces": "Declared project facts agree with the tree.",
        "twin": "tests/unit/scripts/test_check_h.py::test_an_absent_manifest_is_an_error_naming_the_fix",
    },
    {
        "id": "CHECK-I",
        "check": "check_I",
        "enforces": "Agent rule aliases link to their canonical sibling.",
        "twin": "tests/unit/scripts/test_check_faults.py::test_copied_agent_rules_fail",
    },
    {
        "id": "CHECK-J",
        "check": "check_J",
        "enforces": "Library boundaries do not raise foreign exception types.",
        "twin": "tests/unit/scripts/test_check_structure_parse.py::test_a_syntax_error_is_an_error_from_any_check_that_reads_it",
    },
    {
        "id": "CHECK-K",
        "check": "check_K",
        "enforces": "Marked configuration classes are provably immutable.",
        "twin": "tests/unit/scripts/test_check_structure_parse.py::test_the_frozen_config_and_tensor_checks_report_it_too",
    },
    {
        "id": "CHECK-L",
        "check": "check_L",
        "enforces": "Enabled tensor profiles warn on parameters without shape annotations.",
        "twin": "tests/unit/scripts/test_config_loaders.py::test_check_L_is_not_silently_disabled_by_an_unreadable_project_json",
    },
    {
        "id": "CHECK-M",
        "check": "check_M",
        "enforces": "Lint and type settings preserve the declared ruleset.",
        "twin": "tests/unit/scripts/test_check_m.py::test_an_absent_pyproject_with_a_declared_ruleset_is_an_error",
    },
    {
        "id": "CHECK-N",
        "check": "check_N",
        "enforces": "Template twins match their declarations and parity claims.",
        "twin": "tests/unit/scripts/test_check_faults.py::test_undeclared_template_twin_fails",
    },
    {
        "id": "CHECK-O",
        "check": "check_O",
        "enforces": "Code modules carry explicit title and summary headers.",
        "twin": "tests/unit/scripts/test_check_o.py::test_check_o_reports_through_the_gate",
    },
    {
        "id": "CHECK-P",
        "check": "check_P",
        "enforces": "Make help lists every annotated target.",
        "twin": "tests/unit/scripts/test_check_p.py::test_a_nested_include_is_read",
    },
    {
        "id": "CHECK-Q",
        "check": "check_Q",
        "enforces": "Relative links and section citations resolve.",
        "twin": "tests/unit/scripts/test_check_faults.py::test_dead_document_link_fails",
    },
    {
        "id": "CHECK-R",
        "check": "check_R",
        "enforces": "The check catalogue agrees with its executable triggers.",
        "twin": "tests/unit/scripts/test_check_faults.py::test_catalogue_of_absent_script_fails",
    },
    {
        "id": "CHECK-S",
        "check": "check_S",
        "enforces": "Declared rosters match directory membership and state negative scope.",
        "twin": "tests/unit/scripts/test_check_s.py::test_renaming_the_heading_of_a_listed_roster_fails_check_s",
    },
    {
        "id": "CHECK-T",
        "check": "check_T",
        "enforces": "Practice enforcement references resolve to existing mechanisms.",
        "twin": "tests/unit/scripts/test_check_faults.py::test_absent_practice_mechanism_fails",
    },
    {
        "id": "CHECK-U",
        "check": "check_U",
        "enforces": "Policy documents are reachable from root agent rules within one hop.",
        "twin": "tests/unit/scripts/test_check_faults.py::test_unreachable_policy_fails",
    },
    {
        "id": "CHECK-V",
        "check": "check_V",
        "enforces": "Writers declare effects, rerun behavior and resolvable proofs.",
        "twin": "tests/unit/scripts/test_check_v.py::test_check_v_reports_through_the_gate",
    },
    {
        "id": "CHECK-W",
        "check": "check_W",
        "enforces": "Make targets declare effects and guard writes.",
        "twin": "tests/unit/scripts/test_check_w.py::test_a_missing_policy_block_is_an_error_when_a_makefile_exists",
    },
    {
        "id": "CHECK-X",
        "check": "check_X",
        "enforces": "Child processes use the declared environment allowlist.",
        "twin": "tests/unit/scripts/test_check_x.py::test_a_spawn_without_env_is_an_error",
    },
    {
        "id": "CHECK-Y",
        "check": "check_Y",
        "enforces": "Project and template ADRs occupy their declared number spaces.",
        "twin": "tests/unit/scripts/test_check_y.py::test_y_rejects_template_prefix_in_project_space",
    },
    {
        "id": "CHECK-Z",
        "check": "check_Z",
        "enforces": "Campaigns and slices use declared, contiguous work names.",
        "twin": "tests/unit/scripts/test_check_z.py::test_z_rejects_a_malformed_slice_cell",
    },
)
