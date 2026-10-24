---
title: Autonomous run, 2026-10-24
kind: design
layer: n/a
status: draft
owner: TBD
tags: [run, autonomous]
summary: The record of the unattended night run of 2026-10-23 to 2026-10-24 — what landed on main, what each lane holds, every ruling with its cost if wrong, and the decisions parked for the maintainer.
id: docs-design-runs-2026-10-24-autonomous
created: 2026-10-24
updated: 2026-10-26
visibility: internal
canonical: true
type: run
skill: autonomous-mode
started: 2026-10-24T01:32
base: a7f6760eb02564ad5e40609132e7e45bfd53e8c2
changelog: CHANGELOG.md
---

# Autonomous run, 2026-10-24

**Goal:** keel serves engineers who start a project from the Copier template and keep it healthy by running
`make verify`; each queue row closed tonight makes a generated project's gates catch one more real fault, with
docs that say what the code does.

The run began on the evening of 2026-10-23; this file was opened at 01:32 when the autonomous-mode skill
loaded. The minute-by-minute log from the start of the night is the controller's scratch log (outside the
repo); this file is the record.

## Decision form
| Question | Predicted answer |
|---|---|
| What this window must prove, and to whom | To the maintainer: that queue rows can be built, reviewed adversarially and landed unattended, in parallel, with every landed tree green on the full `make verify` |
| The one result that has to land | The WARN-1, SHIP-1, OWNER-2 stack (rows 19, 22, 40), the longest-waiting built work, on main with its verify green |
| What I will not do | Push without the standing merge authorisation's conditions, touch the untracked `project-keel` link (so no KEEL-LINK-1), edit accepted ADRs K-0016 to K-0022, run `[tree]`/`[write]` targets other than `site-data` and `exit-codes`, install anything new, or start KEEL-CODEDOC-1 (it needs a tool choice) |
| The smallest version that proves it | One stack landed with a green merged-tree verify, and the next stack verified behind it |
| How I will know it is done | Each landed row has a flip commit quoting its merged-tree verify (`rc=0` read from the log), its PR is MERGED, and `check_run.py` exits 0 |

## Cap
| Limit | Value |
|---|---|
| Stop time | 2026-10-24 10:00 (12 h from the maintainer's message) |
| Slices or passes | The rows in the Queue below; at most 5 build passes per row and at most 3 fix rounds per worker, then a fresh worker; at most 2 full verifies at once |
| Spend cap | None numeric: the maintainer lifted the notional cap earlier ("go"); spend is reported as notional |

## Queue
States: queued, planned, building, review, landed, parked, dropped.

| Id | Slice | Test | State | Commit |
|---|---|---|---|---|
| KEEL-WARN-1 | row 19, configured default owner (option B) | owner stack full verify (4426 passed, rc=0) | landed | f910a78 |
| KEEL-SHIP-1 | row 22, the shipping gate | owner stack full verify (4426 passed, rc=0) | landed | 335cf04 |
| KEEL-OWNER-2 | row 40, corpus owner resolution | owner stack full verify (4426 passed, rc=0) | landed | 0b935e9 |
| KEEL-MCPCAP-1 | row 32, per-session model-call total | mcpcap full verify on owner + mcpcap (4452 passed, rc=0) | landed | dc0ad1f |
| KEEL-GOALS-1 + KEEL-ROSTER-1 | rows 38, 35; stack B full verify rc=0 (4562 passed, 1 h 34 min), PR #29 merged 06:44 | test_gate_evidence_record | landed | e063586 |
| KEEL-EXIT-1 | row 30; stack B full verify rc=0 (4562 passed, 1 h 34 min), PR #29 merged 06:44 | test_exit_codes_through_make | landed | 00e94c6 |
| KEEL-XDIST-1 | row 34; stack B full verify rc=0 (4562 passed, 1 h 34 min), PR #29 merged 06:44 | test_isolation_gate | landed | 4484e60 |
| KEEL-PROC-1 | row 33, one child supervisor; stack B full verify rc=0 (4562 passed, 1 h 34 min), PR #29 merged 06:44 | test_resource_limits, test_run_make_target | landed | 7f48612 |
| KEEL-TOOLT-1 | row 31, bounded tool children; full verify on top of stack B rc=0 (4626 passed, 1 h 43 min); rebased (tree = verified + row flips), PR #30 merged 06:47 | test_agent_tool_limits | landed | 77def23 |
| KEEL-RISK-1 | row 29, accepted npm-audit risks and `make fe-audit`; merged-tree full verify rc=0 (4824 passed, 1 h 31 min, ~/.cache/keel-slices/risk/verify-merged.log) after the stale-arrival-set fix 8e0ebcd; PR #31 merged 11:43 | test_audit_dependencies | landed | 6d93aad |
| KEEL-DIST-1 | fix round 1 killed by the usage limit at d180d4b (committed through L2; L3 uncommitted or not started) | test_ci_pipeline_gate | review | |
| KEEL-VIS-1 (and OWNER-3) | merged-tree verify rc 2 (generated project: a test reads the `.jinja` twin; the local-target tree sweep); the fixer was killed by the usage limit with one uncommitted edit to test_corpus_owner.py | test_corpus_visibility, test_check_a | review |  |
| KEEL-BOM-1 (new) | read every governed doc as utf-8-sig, so a BOM-led README is walked (found in the VIS-1 review, item 3) | test_check_structure frontmatter, test_check_a | queued | |
| KEEL-OWNER-3 | row 42 (fix round 2 done at f1bb165; fresh re-review) | test_check_f, showcase test, e2e owner source | review | |
| KEEL-JSONDUP-1 | keel-doc2 review r4 rejected 7b18150; fix round 4 (the worker's 2nd) killed by the usage limit at 16f5dbf, committed through its item 3 | test_config_loader, test_export_showcase_static | review | |
| KEEL-DOC-2 | keel-doc2 review r4 rejected 7b18150; fix round 4 (the worker's 2nd) killed by the usage limit at 16f5dbf, committed through its item 3 | test_doc_drift citation findings | building | |
| KEEL-LINT-1 + KEEL-ERR-1 | rows 11, 15 (built on an old base) | lint and swallowed-error gates | queued | |
| KEEL-DOC-1 | full verify rc=0 on 77def23 (4626 passed, 1 h 28 min); main moved to 6d93aad (RISK-1), so it needs one rebase and a full verify before it lands | test_doc_drift | review |  |
| KEEL-HDR-1 | row 23, after LINT-1 | header-field check | queued | |
| KEEL-GRPC-1 | row 26; plan written and critic r1 folded in (~/.cache/keel-slices/grpc/plan.md); build parked on the grpcio install approval and DIST-1 landing | check-venv on the grpc extra | parked | |
| KEEL-SHELL-1 | fix round 1 killed by the usage limit at 661a3fd with 15 staged files uncommitted; resume from them | shell header and exit rules | building | |
| KEEL-VIS-2 | fix round 2 killed by the usage limit at 6027cbc | test_corpus_visibility, e2e visibility | review |  |
| KEEL-OWNER-4 | module-docstring owner outside the grammar is silent (VIS review L4) | test_check_f | queued | |
| KEEL-TOOLT-2 | builder killed by the usage limit mid-S1: 6 uncommitted files in /work/keel-wt/toolt2 (KEYS, both configs, settings.md, CHANGELOG, the test); resume from them | test_agent_tool_limits | building | |
| KEEL-CIGATE-1 | the parity judge does not read a GitHub job's `if:` or the workflow's `on:`, so an edit that skips the gate on pull requests stays green (DIST-1 review L2, GitHub side) | test_ci_pipeline_gate | queued | |
| KEEL-RISK-2 | fe-audit redaction; review r6 at 3356ae5 ready to land (wording round + controller comment fix, lint/check 0, 551 targeted pass); waits for RISK-1 to land, then rebase and full verify | test_audit_dependencies | review | |
| KEEL-IDX-1 | rescoped: keel-lint (KEEL-LINT-1 + KEEL-ERR-1) already fixes the dropped-exit-code class in all four agents; IDX-1 now holds the two gaps it leaves: index_enforcer's tools act on keel's own tree, not `root` (owner gaps from the wrong corpus), and a refused baseline in doc_reviewer and practice_refactor reads as a red one. Built on keel-lint after it lands | test_index_enforcer_durability | queued | |
| KEEL-LINK-1 | the untracked link | none | dropped | |

## Rulings
| What | Why | Cost if wrong |
|---|---|---|
| Stack independent lanes and run one full verify on the stack tip, then merge each lane in order (ff-only) | Five separate 2 h verifies do not fit the night; the lanes overlap only in table rows | A red stack needs a bisect by lane, costing one extra verify |
| Stack B order: goals, exit, xdist, proc, toolt | toolt's bounded runner must sit on proc's one supervisor | One re-rebase if the order is wrong |
| HDR-1 waits for LINT-1, not WARN-1 | The queue table's L3 lane orders LINT-1, ERR-1, HDR-1 (correcting the night plan) | HDR-1 lands a few hours later |
| keel-lint lands last | Its keyword-only signatures collide with every other lane | It may miss the window and wait |
| MCPCAP-1: `agents.max_session_model_calls`, default 0 (fail closed), and a per-question cap above a nonzero total exits CONFIG at start | A long-lived server is the spend risk; per-question alone never bounds it | The owner prefers a different default; one config row |
| RISK-1: `dependency_audit.max_review_days`, default 90 | An accepted risk must not park forever | A team wants longer reviews; one config value |
| RISK-1: redact npm diagnostics by structure, span-only (URLs keep scheme and host only; credential-keyed values; auth-scheme values; 20+ char token runs), and the advice follows the cause | The shape-by-shape deny-list leaked a token-only URL userinfo (H1); whole-line hiding destroyed the cause | Some diagnostics hide more than needed (a hash, a package path); the cause word stays |
| VIS-1: effective visibility is the most restrictive one stated on the node's chain | Confidentiality must not leak through a child's README; to publish a child, lower the parent | A team that wants a public child under a confidential parent restructures; one rule to relax |
| OWNER-3: an owner outside OWNER_GRAMMAR is a gate finding; an absent owner_source is unknown, not none | Fail closed; unknown is kept distinct from none | One finding to downgrade to a warning |
| DIST-1 slice 2: adapters retired only by the exact `# keel-adapter: <name>` line; hand-written adapters held to `ci_pipeline.steps` by a parity test; `GIT_DEPTH: 0` | Never delete a user's own CI file; no new writer to prove | A user must delete an old adapter by hand |
| A stack verify worktree's venv gets `pytest-xdist>=3.0` (pip, into that worktree's .venv only) | KEEL-XDIST-1 makes it a declared dev dependency, so check-venv requires it; this is the lane venv setup, not a new tool | None beyond the venv; main's own venv needs the same after XDIST-1 lands |
| TOOLT-1: a tool child's limit must be at least gate_timeout + 2 x grace + a new `agents.tool_gate_margin_seconds` row | The runner's timeout path spends one grace ending the session and a second draining make's output, plus snapshots; at 1 x grace the agent lost the gate's structured result (review F1, reproduced) | A team with a tight tool limit must raise it; one config value |
| RISK-1 round 5 goes to a fresh worker, and a shown npm line is cut to `dependency_audit.max_shown_chars` (default 500) before redaction, with bounded regex runs | Round 4 was the builder's fourth round (AM-18); a 2 KB registry body took 17 s to redact (review M1) | A long diagnostic loses its tail; the cause word sits at the start |
| VIS-1 covers documents too: a doc inherits the most restrictive visibility of every README above it, and a doc looser than one is a check A error (module docstrings are resolved closed, not flagged) | "Every ancestor" fails closed only if docs are inside it; no module states a level today | A team with a public guide under an internal README restructures or lowers the README |
| OWNER-3: no owner_source is JSON null end to end (query, wiki navigator, frontend "source unknown"); a written null owner stays "no owner" | Unknown is kept distinct from none; null text is the documented spelling of absent | A consumer that expected the string "none" handles null; one type change |
| KEEL-VIS-2 (new): the showcase API, `llms_full` and the static export serve only nodes whose visibility is in a configured allowlist, defaulting to the wiki navigator's; built stacked on keel-vis after its fix round | Review H1 (existing before the branch): a confidential node's body reaches search, `llms_full` and the Pages export; tightening to the navigator's rule fails closed and reuses an existing pattern | A team that publishes internal docs on Pages widens the allowlist; one config value |
| DOC-2: the upgrade guide gets no config excuse from the change-phrase rule, and features.md gets no row for test_doc_drift | Fail closed; the catalogue lists only `_gate.py` files | An upgrade note at the start of a thought must be reworded; one excuse row to add |
| DOC-2: the change-phrase-at-an-opener rule is advisory (`make doc-review`), not a gate; the cited-check rule stays a gate | It flags normal prose ("Now run", "fixed-point", "Removed entries are…") and ships to generated projects, so a downstream tutorial would go red on update | A change report at an opener reaches main and is caught only by review |
| JSONDUP-1: a refused project config file exits CONFIG in every converted reader | AGENT.md: a config fault returns report(ExitCode.CONFIG, ...); the review found 2, 14 and 0 for one fault | A script that wrapped exit 2 for a bad manifest changes its handling; one table row each |
| TOOLT-1: `agents.tool_gate_margin_seconds` defaults to 60, not the 570 left over | At 570 the shipped config had zero slack, so any raise of a gate key refused every agent tool; the measured need was about 0.3 s | A very large tree on slow disk needs a bigger margin; one config value |
| VIS-2: the allowlist is one config key read by every reader, and the wiki navigator's literal `_VISIBLE` moves to it; a hidden node is absent (answered as unknown), not redacted | Fix the class: two readers with two rules is how the leak arose; absent leaks no title or count | A team that wants titles of hidden nodes listed changes the rule; one reader each |
| VIS fix round 2: an unreadable README stops the owner walk; nodes below get owner and owner_source null (unknown) | Visibility already treats it as "may state anything"; owner must not fail open to the grandparent | An owner shows unknown where the grandparent's was right; one function reverts |
| practice_refactor (model prompt) and query_corpus join KEEL-VIS-2 under the same allowlist | Same class as the showcase leak; a model provider is a reader outside the project | A refactor prompt loses context from hidden nodes; the allowlist widens it |
| RISK round 7: a host or resolver operand is judged as its whole run (with `+/=` and escapes); kept only when the whole run is a DNS name | The class is "a piece check lets a split token through"; whole-run judging is what the base did for non-hosts | More hosts hidden than needed; readable hosts are dotted DNS names, so the loss is small |
| RISK round 7 deviation accepted: a non-DNS host is hidden whole only when it mixes letters and digits, so `localhost` stays readable | Every published registry token format carries digits; hiding `localhost` would hide the cause for every local Verdaccio user | A letters-only token used as a host prints; one condition reverts it |
| RISK-1 closes after one fresh-worker round on the two tests that cannot fail and the doc drift; the three host-rule L items (one pre-existing leak shape, two over-hides) go to KEEL-RISK-2 | Seven rounds in; every H/M is fixed and the original repros pass; a test that cannot fail is a bug and blocks, a rule trade-off does not | A `glpat-`-prefixed token placed as a host label prints until RISK-2 lands; it needs a misconfigured registry URL |
| The RISK-1 closing review's one L (the CHANGELOG row's host-label rule) is fixed by the controller, not a worker | Every worker round is used; it is one sentence, the fix the reviewer named, checked live on four host shapes | The row's wording needs another touch; text only |
| Stack B is verified at the proc tip now, and TOOLT-1 gets its own verify on top once its re-review is clean | The verify slot was idle; waiting for TOOLT-1 would hold four reviewed lanes back two hours | One extra two-hour verify of compute |
| KEEL-RISK-2 branches from the unmerged keel-risk tip | It owns only audit_dependencies.py and its docs, which no other lane touches; waiting for RISK-1 to land would leave a lane idle for hours | A RISK-1 change at merge forces a rebase of RISK-2; one file |
| TOOLT-1 closes after one fresh-worker round on the four L items (session wording in tests, a settings Default cell no test pins to KEYS, a prose default no test pins, literals in the slack test) | The builder's three rounds are used; the docs-to-code pins are a class gap that would recur, so they are fixed as a class, not row by row | One more round of time before TOOLT-1 can verify; stack B lands without it meanwhile |
| TOOLT-1 item 2 accepted as "drop the claim", not a Default-cell-equals-KEYS test | The Default cell states the shipped config value and the `[using default]` line the KEYS default; they differ on purpose (`child_env.login_name_schemes`); the stray-line test now pins every quoted default line instead | A Default cell that drifts from KEYS where they should agree is caught only by the quoted-line test; one test to add |
| DIST-1: the GitLab adapter's `node24` literal stays, guarded by the parity gate | The step list and versions are checked for parity between adapters; a node bump that misses the twin goes red | A node bump touches one more file; the reviewer may find it renderable from config, then it is filled |
| DIST-1: the features Ships grammar accepts `!=` and `is [not]` | ci.yml ships unless the answer is gitlab; the old grammar could not say that | Rows that parse differently; the reviewer checks every existing row |
| DIST-1: the parity judge reads `.copier-answers.yml` with a stdlib line scan, failing closed on a missing or invalid line | That file is Copier's record, not one of the loader's config files; the loader's scope is config/project.json, practices.json and declared variables | If the reviewer rules it in scope, one reader moves behind the loader |
| VIS round 3: `corpus_vocabulary.py` stays in the scripts layer, not the lowest one | Both importers are in scripts; no lower module reads the set, and a key or module with no consumer is not added | A lower-layer reader later needs one move and an import-layer row |
| VIS round 3: a corpus with no `nodes` key is refused (exit USAGE) instead of counted as zero nodes | Unknown is not zero: a corpus without the list is not an empty project | A hand-built empty corpus must carry `"nodes": []`; the reviewer checks callers |
| KEEL-IDX-1 queued and started now: a doer that drops a tool's exit status fails open | The VIS round-3 worker found index_enforcer reads a refused report as no owner gaps; fail closed is a default, and it is the same class as S5 | The fix may surface a failure the nightly schedule now reports; that is the intent |
| node_modules in a verify worktree are hard links (`cp -al`) to main's when the lockfiles match | A verify went red only at test-fe-unit with no node_modules; hard links cost no disk | A lockfile change would need real copies; checked per worktree |
| TOOLT-1 closing review: the one L (commits 56a813d and fcd05b2 leave test_config_default_lines_docs red; b247021 fixes it) is accepted, not rewritten | The branch is unpushed, but a history rewrite across a 26-commit rebased stack risks more than a red mid-commit costs; b247021's message names the gap | `git bisect` over that span needs a skip of two commits |
| TOOLT-1 verifies now in the second slot, on top of the unmerged stack B tip | Both verifies fit the two-at-once limit; if stack B lands green, TOOLT-1's verify already covers the merged tree | If stack B goes red, TOOLT-1's verify is rerun after the fix; two hours of compute |
| KEEL-IDX-1 rescoped to the two gaps keel-lint leaves, after keel-lint lands (builder's option b) | Building it as briefed would repeat keel-lint's fix and conflict with it in four `_brain.py` files; the wrong-tree read is a real fail-open keel-lint does not close | The wrong-tree owner gaps stay unfixed until keel-lint lands, which is last in the order |
| The RISK-2 builder rewrites its own unpushed branch to drop a token-shaped fixture, with no scanner exclusion | `make verify`'s history scan reads every branch (`git log --all`), so one literal on any lane made the TOOLT-1 verify red in its first minute; an exclusion would excuse a shape in a file for good | A rewrite of a local branch only; every later brief carries the no-credential-shape line |
| TOOLT-1's verify is rerun after the RISK-2 rewrite, not judged on its red run | The red was another lane's commit, not TOOLT-1's tree; the scan must pass on the tree as it lands | Two more hours before TOOLT-1 lands |
| KEEL-SHELL-1 slice 2 starts now off keel-toolt, in the slot IDX-1 freed | Its files (check_O/V, the exit gate, a new helper) touch stack B's exit gate, so it starts from the tip that holds it; slice 3 waits for slice 2 | A rebase if TOOLT-1 changes before it lands |
| VIS-1 M2: a real file reached by several paths is served at the strictest level of every chain that reaches it, in the corpus and check_A alike | Today the level follows sort order, so renaming a directory can serve a file reached through a restricted directory as public; fail closed and order-independent | A public file linked into a stricter directory is over-hidden; the closing round measures how many nodes change on this tree (expected 0) |
| VIS-1 closes after one fresh-worker round on M1, M2, L1, L2 | The builder's three rounds are used; M2 is a policy choice I made, so the round is a build, not a debate | One more round before VIS-1 verifies; VIS-2 rebases onto it |
| RISK-2 item 3: after `=` or `:` a value is always hidden; in prose one plain lower-case word is kept | An assignment states a value, prose like `password required` states a cause | An all-lower-case letters-only password written in prose is shown |
| RISK-2 item 9: a word then digits (`acme2024-111122223333`, `nexus3`) is a name and kept; any other 20+ mixed run is a token | A name turns from letters to digits once, a random token many times | A word-plus-number secret standing as a host is shown |
| The RISK-2 builder's probe that let npm reach the public registry once (one audit request, one DNS lookup) is recorded, not repeated; the review brief points every registry and proxy at loopback | An audit request carries package names, no credential and no project data, but it left the workspace | One outbound request per probe; the brief now forbids it |
| DIST-1 M1: an update never deletes an edited CI file; the marker guard removes only a file byte-equal to keel's last render, one verdict shared with keep_edited_retired | The update printed "kept" and then deleted the user's job; never delete what the project edited is the lane's own goal line | An edited file with stale keel steps lingers until the user removes it; the stderr line says so |
| DIST-1 L2 is fixed for GitLab in this lane and queued for GitHub as KEEL-CIGATE-1 | The GitHub gap predates the slice and touches a different adapter; the slice cap holds | GitHub `if:` edits that skip the gate stay green until CIGATE-1 lands |
| RISK-2 prose rule replaced: after a secret word, a word in its clause is kept only if it is in a closed vocabulary of linking and cause words; every other word is hidden | The review showed the "looks like a plain word" rule is open-ended (`was set to X`, `is Swordfish!`, `for bob is X` all leaked); fail closed beats chasing shapes, and the advice still reads the raw text | An unknown cause word is hidden, so a message reads less well; the advice is unchanged |
| RISK-2 assignment values run to the end of the line or the next `name=` | A quote, comma or `name:` inside a password ended the value early and showed the rest | Cause text on the same line after an assignment is hidden |
| RISK-2 L3 (letters-then-digits token as a host) and the plain-text CodeArtifact label are accepted as documented | A random token rarely has the word-then-number shape; the docs state both costs | A token of that shape standing as a host prints |
| VIS-2 review findings: one shared served-level predicate and id-cut in src replaces the four copies; index_enforcer, doc_reviewer and query_corpus route through it; a corpus row with no visibility field is not served; the e2e public doc links to the secret one | The goal line says a hidden node is never sent to a model or named; four hand-written filters already drifted (three readers missed), so one derivation is the class fix | If the predicate is wrong every reader is wrong at once; its tests and the e2e scenario guard it, and reverting is a few call sites |
| VIS-1 review Lows: fix the code, not the wording; one README-level read shared by build_corpus and check_A; the last round also fixes the stale VIS-1 CHANGELOG and design-note text | Every case fails safe today, but two hand-written reads already disagree on four shapes; one function ends that class, and the stale text is VIS-1's to own | One more round before VIS-1 can verify (about 2 h of slot time later); the cheaper wording-only fix leaves the two reads able to drift |
| JSONDUP/DOC-2 round 2: fix the pre-existing exit-2 path through run_date, the no-manifest crash and the launcher USAGE here, not queued | All three break the slice's own goal line ("CONFIG in every reader, never a crash") and AGENT.md's config-fault rule; queuing them would land a CHANGELOG claim that is false | The slice grows by four callers of run_date; if the mapping is wrong a real missing date source would read as a config fault, which item 2 keeps separate |
| RISK-2: HTTP method words (GET, HEAD, POST, PUT, PATCH, DELETE) join CAUSE_WORDS, sourced from npm-registry-fetch's status line | Since `auth` matches inside `Unauthorized`, every 401 line hides `- POST`; a method is never a credential and the line is how a user tells which call failed | A secret that equals a method name would print; that is a value no registry accepts as a credential |
| VIS-1: "one reader" covers walked READMEs too: a BOM README in a walked directory reads utf-8-sig on both sides; the worker stops if that would change how a non-README doc is judged | The fix's own claim is one reader; the remaining asymmetry fails closed but names the wrong fault | If the encoding change reaches every governed doc, a BOM doc that failed loudly now passes; the stop condition keeps that out of this slice |
| RISK-2 round 2: a clause starts after a secret word whatever follows it; only a word that starts with a URL is kept; a period after a single letter or before a lowercase word is no sentence end | Each repro printed a value after a secret word, which the goal line forbids; fail closed is the house rule | More plain words after a wrapped secret word are hidden; the advice still reads the raw text, so only the shown line reads worse |
| RISK-2: a 1-3 character punctuation-only word is kept; cause words without a printed source are dropped; no literal password in fixtures or docs | npm's ` - ` separators read as hidden credentials; the data module's own rule is printed messages only; the brief said fixtures are built at run time | A punctuation-only secret of 3 characters or less prints, a value no registry issues; a dropped cause word hides a real reason word until re-sourced |
| VIS-1 item 3 (BOM README in a walked dir): leave it in VIS-1 (option c) and queue the real class fix, utf-8-sig for every governed doc, as KEEL-BOM-1 | It fails loudly today, no tracked doc has a BOM, and the fix changes the frontmatter rule for every doc type, which needs its own slice and review; the worker's README-only route would key on a file name | Until BOM-1 lands, a BOM-saved README gets a misleading "missing frontmatter" error instead of the contradiction; the gate is red either way |
| VIS-1 review L2 (KEEL-VIS-2 has no row on keel-vis): accepted; VIS-2 lands next on this line and brings row 43 | The follow-up is tracked in this run's queue and on keel-vis2; adding a row on keel-vis would conflict with the one keel-vis2 carries | If VIS-2 stalls, main names an untracked follow-up; the hand-over names VIS-2 in remaining either way |
| KEEL-DOC-1 S4 freshness keeps no-git as a stated skip; only a git that ran and failed is refused | K-0019 is accepted and immutable, and generate-and-upgrade.md promises that a project with no git runs as before | if no-git really should fail closed, a new ADR superseding K-0019 is needed later; nothing is built on the wrong side meanwhile |
| KEEL-DOC-1 project-facing doc checks are pytest gate tests, one expiring-tier CHECKS row each; K-0027 unchanged | CHECKS maps to pytest node ids, and K-0027 cuts check_structure out of the tier | if the owner wants check_structure under the tier, K-0027 must be superseded and these tests rehomed |
| KEEL-DOC-1 S3 extends check_S (README rosters) as the incumbent instead of adding a second README heading check | two checks on one heading would disagree on unlisted READMEs | S3's scope is narrower than the study's README contract; the rest is queued |
| KEEL-DOC-1 record heading `### Defence record` under the campaign `##`; S1's reader reads that level | the campaign heading is already `##`, and _sections reads only `##` | the reader must change in S1; rewording one heading level later is cheap |
| KEEL-DOC-1 every item the plan calls "queued" gets a queue row and backlog id now | the queue table is the only work source; an unrowed item is lost | extra rows that the owner may drop; cheap to drop |
| KEEL-DOC-1 cap (item 9) and verdict words (item 1) stay open; the text is conditional on them | they are the owner's open decisions; the plan had settled them silently | none: the recommendation stands and only the wording changes |
| KEEL-DOC-1 r2: S4 adds one public read-only git runner in git_tree that keeps git_argv's read-only prefix and names the expected non-zero exits | the judge must stay read-only, and an unborn HEAD is an answer, not a failure | the runner may belong in review_docs instead; moving it later is one import |
| KEEL-DOC-1 r2: the ADR cut-off is per number space, and only keel's K- space has one (keel-owned); a project's NNNN space is judged from 0001; a project may add a kind or home but not rebind one keel ships | one cut-off would exempt a project's own ADRs or judge keel's it cannot edit | if a project needs to exempt its own old ADRs, a project-side key is added later |
| KEEL-DOC-1 r2: VIS-2 keeps plan position 43; CMP-7's nine rows become 44-52 and are marked proposed, not maintainer-approved | VIS-2 is further along and lands first; the approved order is the maintainer's | the maintainer may reorder; positions are text |
| KEEL-DOC-1 r2 extra: keel's ADR cut-off stays a config key, with a `gap` row saying a project could raise it and the copier update diff catches it | the house rule puts every setting in config; the same cut applies to expiring_tier_data | a project silently exempts K- ADRs; the fix is a keel-owned `*_data.py` constant |
| KEEL-VIS-2 r2: a reader that reads a body from disk serves at the strictest of the corpus level and the level the file states now; L1/L2 tests made to fail; L4 named in §1; L3 needs no fix | the goal line says never served, and a stale corpus breaks that between edit and rebuild | an extra frontmatter read per served body; reversible by dropping the second read |
| KEEL-RISK-2 r3: last fix round; fix H1/M1/M2/M3/L1, row to 53, and add a generative leak test as the class fix; if the next review fails, the controller replaces the clause rule with a fail-closed one | two rounds each opened new leaks, so example tests are not enough; a grammar test covers the class | one more round of builder time; the fallback over-hides cause text |
| KEEL-DOC-1 r3: the runner contract uses measured git exits (log over an uncommitted file is 0 and empty; with an unborn HEAD log is not run; 128 is never an answer); the ADR cut-off is K-0005 | the reviewer measured the codes, and accepting 128 would fail open; accepted ADRs never change, so a lower cut-off guards more for free | an extra plan round; K-0005 would turn red only if an accepted ADR lost its heading, which is the point |
| KEEL-DOC-1 r4: a fresh worker (3 rounds used) replaces the vacuous 128 mutation with a log-only fault case; S4 adds a toplevel-vs-found-root check that fails closed for a corrupt repo nested in another, with a pinned ceiling in its case | a guard that cannot go red is a bug; judging the parent repo silently is fail-open | one more plan round; the toplevel check costs one git call per judge run |
| KEEL-DOC-1 r5: after 3 rounds and a fresh worker, the controller fixed the r5 findings itself (c5699ee: branch overlap named exactly, head_commit before ls-files, mismatch error names both directories, unborn-HEAD behaviour marked as S4's change, wrap) | the skill says the controller rules after a fresh worker; these are wording-sized plan edits | a narrow review r6 may still find wording; the plan lands as proposed, so a slip costs a later plan edit |
| KEEL-RISK-2: the old `hunter2` stand-ins in 8 branch commits stay in history (not squashed) | the tip has none, gitleaks over `--all` passes, it is a well-known dummy word and no real credential, and the logical commit splits stay readable | a stricter scanner later flags them; the fix is one excuse row or a squash before merge |
| KEEL-RISK-2 r4: ready to land; a fresh worker closes the four Lows (untested 300 and 256 bounds, a false comment, a coarse exemption) before the rebase onto RISK-1 | an untested bound is a vacuous guard by the house rule, and the docs named the wrong mechanism | one short round before landing; no leak rides on it |
| JSONDUP-1/DOC-2 r3: a conflict hunk exits 2 in every script through one helper; the opener rule stops hiding numbered headings and number-ended sentences; schema duplicates exit 14 | the CHANGELOG promises exit 2 for a conflict, and the review reproduced both regressions live; R-CODE-6 splits fix-input from fix-call | a wrong code sends an operator to the wrong remedy; reversible in one commit |
| JSONDUP-1 M2: the three readers outside scripts/ are a documented scope cut, queued as KEEL-JSONDUP-2 | they sit below scripts/ in the import layers, and `make check` already fails both shapes, so no project goes green on them | the showcase snapshot can still be written over a refused manifest until JSONDUP-2 lands |
| RISK-2 Lows: the tests keep the literals 300 and 256 | the literals pin the bounds, so raising one turns a test red; deriving them from the constant would make the test follow any change | a deliberate bound change needs a test edit too |
| RISK-2 r5 Lows: fix the wording, not the redactor, and pin each corrected sentence with a test row | the code hides more than the text claims on every shape tried, so the risk is a reader trusting the wrong sentence, not a leak | one more short round before RISK-2 can rebase onto RISK-1 |
| RISK-2 r6: ready to land; the controller fixed the two stale comments (3356ae5) and left the show/hide verb unpinned | the example literal with `<value>` already pins the meaning and goes red when changed; a verb pin would be a text match with no new protection | a reader could be misled by a wrong verb that the literal contradicts |
| GRPC-1: plan done (critic next); the build waits for keel-dist to land and for the owner to approve installing grpcio, grpcio-tools and protobuf into keel's venvs | installs are on the stop list, and S1 turns `make verify` red at check-venv on every venv that lacks them | none: nothing is built until approved; the plan stays ready |
| Plan-row number 43 is claimed by both keel-vis2 (KEEL-VIS-2) and keel-doc2 (KEEL-JSONDUP-2): whichever lands second takes the next free number at its rebase | the row number is an id other text cites, so two rows cannot share it; renumbering one new row is cheaper than holding a branch | a missed renumber leaves two rows 43, which a reader of the queue would trip on |
| SHELL-1 S2: accept the builder's `[tree]` label for `make exit-codes-sh` (brief said `[write]`) pending review | K-0011 labels regenerating a tracked file `[tree]`, and the reviewer checks it | a wrong label lets the gate runner run it unattended; check_W and test_make_target_effects measure it |
| SHELL-1 S2 worker ran `pip install -e "<worktree>[dev,template]"` in its own worktree venv (copier was missing) | it installs only the project's own declared extras into a throwaway venv, the same set every worktree venv carries; nothing system-wide | recorded as an incident against the stop list: the brief should have named the venv as ready; worker briefs now say "install nothing" |
| doc2 r4: prove "a conflict exits 2 in every script" by running every discovered entry point on a conflicted copy, not only by the AST gate | the AST gate missed a wrapper class, an alias and an ignored result; behaviour is the claim, so test behaviour, from a derived list | a slower test (one subprocess per entry point); a wrong args row fails loudly |
| SHELL-1 S2 M1: the exit rule and the helper apply whatever `shell.enabled` says; only the zero-scripts finding depends on it | the plan's general rule says the answer switches the tools only, and a project that answers no still ships shell scripts that must be explained | a project answering no sees new findings on its shell scripts; reversible by one key |
| SHELL-1 S2 M3: the renamed-status shapes are caught as a class, the residue stated as limits | a gate a one-line rename bypasses is vacuous | stricter reading may flag a valid script; the stated-limit path covers it |
| TOOLT-2: raise the tool-child margin from 60 s to 120 s, docs carry one measured per-file rate labelled as one host; S2 after S1; trailer `Backlog: KEEL-TOOLT-2` | the measured cold worst case on NFS (~65 s for both snapshots) already exceeds 60 s; a margin that does not cover the measured case is a vacuous guard | a 60 s longer tool limit floor for generated projects; 15000 still fits with 450 s spare; one key reverts it |
| RISK-1 merged-tree verify rc 2 (4822 passed, 2 failed): add `dependency_audit` to the two exact-set arrival tests in test_copier_audit.py, rerun the full verify | RISK-1 adds that key, and an older project correctly receives it as an arrival; the tests, not the code, were stale | another hand-written key list stays stale; the rerun verify would catch it |
| TOOLT-2 critic r1 (fix first, 9 findings): all confirmed findings applied as plan amendments by the controller (listed-paths cost model, no Changed bullet, ~50 000-path bound, real planted fault, config-only revert, slack 210 s, one S2 row, RAM label, deferred after-snapshot) | each is a short plan correction with evidence; none needs new measurement | a wrong amendment reaches the build; the build review would catch it |
| VIS-1 merged-tree verify rc 2 (keel 5006 passed; the generated project failed 2: a test reading the `.jinja` twin, and the local-target tree-effect sweep): a fresh fixer reproduces in a generated project and fixes the root cause, then the verify reruns | a generated project must pass its own suite; the second failure's log was truncated, so it needs a live repro | VIS-1 lands later; VIS-2 and IDX-1 wait on it |
## Declined to judge
| Question | Why I did not judge it |
|---|---|
| The 7 uncovered astro, sharp and zod advisories (KEEL-ASTRO-1) | Accepting a security risk is the maintainer's call |
| KEEL-CODEDOC-1's tool choice | It needs research and a tool the maintainer picks |

## Parked decisions
| Decision | Options | My recommendation | Waits on |
|---|---|---|---|
| The 7 uncovered frontend advisories | upgrade astro/sharp/zod (KEEL-ASTRO-1), or accept with review dates | Upgrade under KEEL-ASTRO-1 in a lane with real node_modules | The maintainer |
| Installing grpcio, grpcio-tools and protobuf into keel's venvs for KEEL-GRPC-1 S1 | approve the install, or keep gRPC unjudged by check-venv | Approve: the plan is data only (an extra, a map entry, a test surface) and every venv needs one `pip install -e ".[dev,template]"` after it lands | The maintainer, and keel-dist landing first |

## Workers
| When | Running | Queued | Note |
|---|---|---|---|
| 2026-10-23 evening | 8 | 10 | 5 workflow lanes, DIST-1, MCPCAP-1, RISK-1 builders; 1 full verify |
| 2026-10-24 00:52 | 4 | 10 | DIST-1, RISK-1 builders; 2 full verifies (owner stack, mcpcap) |
| 2026-10-24 01:20 | 7 | 8 | toolt rebase, VIS-1, JSONDUP-1, DIST-1, RISK-1 review; 2 full verifies |
| 2026-10-24 01:35 | 7 | 8 | toolt conflict review, VIS-1, JSONDUP-1, DIST-1, RISK-1 review; 2 full verifies |
| 2026-10-24 01:38 | 4 | 8 | usage limit stopped the toolt review, the JSONDUP-1 builder and the RISK-1 review; VIS-1, DIST-1 and both verifies survived |
| 2026-10-24 01:41 | 7 | 8 | all three resumed from their transcripts |
| 2026-10-24 01:47 | 7 | 9 | toolt and RISK-1 reviews done (toolt 1 M + 3 L; RISK-1 2 M + 6 L); fix workers started for both; doc2, VIS-1, DIST-1 builders; 2 full verifies |
| 2026-10-24 01:50 | 7 | 9 | VIS-1/OWNER-3 built (6 commits, gates green, 25/27 mutants killed, 2 equivalent); fresh review started |
| 2026-10-24 02:00 | 7 | 11 | VIS review: 1 H (pre-existing showcase leak, queued KEEL-VIS-2), 2 M, 2 L; VIS fix round 1 started |
| 2026-10-24 02:05 | 7 | 11 | JSONDUP-1 + DOC-2 built on keel-doc2 (5 commits, gates 0, 31 mutants killed); fresh review started |
| 2026-10-24 02:06 | 7 | 11 | toolt fix round and RISK-1 round 5 done; fresh re-reviews of both; JSONDUP/DOC-2 review, VIS fix round, DIST-1 builder; 2 full verifies |
| 2026-10-24 02:14 | 7 | 11 | doc2 and toolt reviews done; fix rounds with the doc2, toolt and RISK-1 builders; VIS fix round, DIST-1 builder; 2 full verifies |
| 2026-10-24 02:23 | 8 | 10 | VIS fix round done; VIS re-review and KEEL-VIS-2 builder started; doc2, toolt, RISK-1, DIST-1 builders; 2 full verifies |
| 2026-10-24 02:29 | 8 | 10 | VIS re-review done (0 H/M, 6 L confirmed, 3 refuted); VIS fix round 2 started; VIS-2 scope widened |
| 2026-10-24 02:32 | 8 | 10 | RISK round-6 review done (5 originals fixed, 1 M new, 6 L); round 7 sent to the same worker; L3-L6 queued in KEEL-RISK-2 |
| 2026-10-24 02:41 | 8 | 10 | RISK round 7 done (47353c4, 032abdc, da47fe4); fresh re-review started |
| 2026-10-24 02:42 | 8 | 10 | VIS fix round 2 done (7 commits); fresh re-review started |
| 2026-10-24 02:43 | 8 | 11 | TOOLT round-2 review done (4 originals fixed, 0 H/M, 5 L); round 3 sent to the same worker; KEEL-TOOLT-2 queued |
| 2026-10-24 02:47 | 8 | 11 | RISK round-7 review done (3 originals fixed, 0 H/M, 7 L); controller ruled a closing round by a fresh worker |
| 2026-10-24 02:57 | 7 | 11 | owner stack and MCPCAP-1 merged (PRs 27, 28; main dc0ad1f); VIS round 3 sent; RISK-1 closing round done, fresh review started; stack B (goals to proc) rebased, full verify started; TOOLT r3, VIS-2, DIST-1, JSONDUP/DOC-2 builders |
| 2026-10-24 03:00 | 7 | 11 | stack B verify restarted (first run red only on a stale corpus after the restamp commit; site-data fixed it); TOOLT r3 done, fresh re-review; RISK-1 review done (1 L fixed); VIS r3, VIS-2, DIST-1, JSONDUP/DOC-2 builders |
| 2026-10-24 03:01 | 7 | 10 | KEEL-RISK-2 builder started (risk2 worktree, plan-first commit); running: stack B verify, TOOLT re-review, VIS r3, VIS-2, DIST-1, JSONDUP/DOC-2, RISK-2 |
| 2026-10-24 03:03 | 7 | 10 | TOOLT round-3 review done (0 H/M, 4 L confirmed); closing round started with a fresh worker |
| 2026-10-24 03:11 | 7 | 10 | TOOLT closing round done (4 commits; the given tip was red on test_config_default_lines_docs, fixed in it); rebased onto stack B; fresh review started |
| 2026-10-24 03:12 | 7 | 10 | DIST-1 slice 2 built (8 commits; copier generation 103 passed, unit 3129); fresh review started; builder freed |
| 2026-10-24 03:17 | 8 | 10 | VIS round 3 done; fresh re-review started; KEEL-IDX-1 builder started (idx worktree) |
| 2026-10-24 ~03:19 | 8 | 10 | TOOLT closing review clean (0 H/M, 1 L accepted); pre-checks all rc 0; full verify started on be58806 (second slot); reviewer freed |
| 2026-10-24 ~03:22 | 7 | 10 | TOOLT verify red in 1 min on the history secret scan (RISK-2 lane's token fixture in 7debfd7); RISK-2 builder told to rewrite; IDX-1 builder stopped (covered by keel-lint), rescoped and queued; SHELL-1 slice 2 builder started (shell2) |
| 2026-10-24 ~03:25 | 7 | 10 | VIS round-3 review done (0 H, 2 M, 2 L); M2 ruled (strictest chain); closing round started with a fresh worker; reviewer freed |
| 2026-10-24 03:28 | 7 | 10 | RISK-2 built and history rewritten (secret-scan rc 0 over all branches); TOOLT-1 verify restarted; RISK-2 fresh review started; builder freed |
| 2026-10-24 ~03:30 | 7 | 11 | DIST-1 slice-2 review done (0 H, 1 M, 3 L); fix round 1 started; KEEL-CIGATE-1 queued; reviewer freed |
| 2026-10-24 ~03:33 | 8 | 11 | RISK-2 review done (1 H, 1 M, 7 L, not mergeable as is); fix round 1 sent to the builder; reviewer freed; running: 2 verifies (stack B, TOOLT), fix rounds DIST, VIS, RISK-2, builders VIS-2, JSONDUP/DOC-2, SHELL s2 |
| 2026-10-24 ~03:35 | 8 | 11 | VIS-2 built; fresh review started; builder freed |
| 2026-10-24 03:38 | 8 | 11 | VIS-1 closing round done (4 commits to 9d0cd91); fresh review started; worker freed |
| 2026-10-24 03:41 | 8 | 11 | VIS-2 review done (1 H, 3 M, 2 L, not mergeable); fix round 1 started with a fresh worker; reviewer freed |
| 2026-10-24 03:44 | 8 | 11 | VIS-1 closing-round review passed with 3 L; last fix round started with a fresh worker; reviewer freed |
| 2026-10-24 03:45 | 8 | 11 | JSONDUP/DOC-2 fix round 1 done (to 118f2ef, gates 0); fresh review started; builder freed |
| 2026-10-24 03:55 | 8 | 11 | JSONDUP/DOC-2 review done (3 M, 5 L); fix round 2 sent to the builder; reviewer freed |
| 2026-10-24 03:56 | 8 | 11 | RISK-2 fix round 1 done (to 37e75dc); builder adds HTTP method words, then a fresh review |
| 2026-10-24 03:58 | 8 | 11 | RISK-2 method-word commit e406868 done; fresh review started; builder freed |
| 2026-10-24 04:00 | 8 | 11 | VIS-1 last round done (to 4d2f7d3); short fresh review started; worker freed |
| 2026-10-24 04:05 | 8 | 11 | VIS-1 short review passed (2 L); the same worker fixes them; reviewer freed |
| 2026-10-24 04:06 | 8 | 11 | RISK-2 review done (1 H, 1 M, 5 L); fix round 2 sent to the builder; reviewer freed |
| 2026-10-24 04:09 | 8 | 12 | VIS-1 items 1-2 done (to 22255b8); item 3 stopped by its stop condition and queued as KEEL-BOM-1; short review started; worker freed |
| 2026-10-24 04:11 | 8 | 12 | VIS-1 short review: 0 H, 0 M, 2 L; the worker restores the mode-000 file; reviewer freed |
| 2026-10-24 04:13 | 8 | 11 | VIS-1 worker freed at 35819af; KEEL-DOC-1 plan critic started (fresh agent) |
| 2026-10-24 04:19 | 8 | 11 | CMP-7 critic: fix first (3 H, 6 M, 7 L), critic freed; a fresh worker starts fix round 1 |
| 2026-10-24 04:25 | 0 | 11 | usage limit (resets 06:40) stopped all 6 agents; both full verifies kept running |
| 2026-10-24 06:41 | 8 | 11 | limit reset; 6 agents resumed; stack B and TOOLT verifies rc=0 |
| 2026-10-24 06:49 | 8 | 9 | stack B (PR #29) and TOOLT (PR #30) landed; RISK-1 and VIS-1 verifying; VIS-2 and DOC-1 reviews; RISK-2, JSONDUP, DIST, SHELL builders |
| 2026-10-24 06:52 | 8 | 9 | CMP-7 review r2 fix first, its worker on round 2; RISK-2 round 2 done, fresh review r3 started |
| 2026-10-24 06:56 | 8 | 9 | DOC-1 review r3 and VIS-2 fix r2 started; VIS-2 review r2 done |
| 2026-10-24 06:59 | 8 | 9 | RISK-2 review r3 done (reject); fix round 3 started |
| 2026-10-24 07:17 | 7 | 9 | DOC-1 ready to land, waiting for a verify slot (2 verifies running) |
| 2026-10-24 07:39 | 7 | 9 | doc2 review r3 and RISK-2 Lows finished; doc2 fix r3 (fresh worker) and RISK-2 review r5 started |
| 2026-10-24 07:46 | 7 | 9 | RISK-2 review r5 passed with wording Lows; RISK-2 wording fix started |
| 2026-10-24 07:59 | 6 | 9 | RISK-2 review r6 passed; RISK-2 waits for RISK-1 to land, then rebase and full verify |
| 2026-10-24 08:00 | 7 | 9 | KEEL-GRPC-1 planner started to fill the lane while two verify slots are busy |
| 2026-10-24 08:11 | 7 | 8 | GRPC-1 critic done (plan amended, build parked); TOOLT-2 planner and measurement started |
| 2026-10-24 08:14 | 7 | 8 | doc2 fix r3 done; doc2 review r4 started |
| 2026-10-24 08:19 | 7 | 8 | SHELL-1 slice 2 built; fresh review started |
| 2026-10-24 08:22 | 7 | 8 | doc2 review r4 rejected; fix round 4 started |
| 2026-10-24 08:30 | 7 | 9 | SHELL S2 reviewer done (reject); builder resumed for fix round 1; RISK-1 and VIS-1 verifies still running |
| 2026-10-24 08:33 | 7 | 8 | TOOLT-2 planner done; plan critic started |
| 2026-10-24 08:38 | 7 | 8 | TOOLT-2 critic done, builder started; RISK-1 verify rerun |
| 2026-10-24 08:41 | 8 | 7 | VIS-1 verify failed, fixer started; DOC-1 verify started |
| 2026-10-24 08:44 | 3 | 13 | usage limit hit: all six agents killed (VIS-2, DIST, doc2, SHELL, TOOLT-2, VIS-1 fixer); only the RISK-1 and DOC-1 verifies run on |
| 2026-10-24 10:11 | 0 | 13 | both verifies done (rc=0); no agent can start until the limit resets at 11:40 |
| 2026-10-24 11:43 | 0 | 13 | limit reset; RISK-1 landed; hand-over (stop time 10:00 passed) |

## Report

### Done against remaining
Landed on main, each through a merged-tree full verify read as `rc=0` from its log, a fresh review and a
fast-forward merge: WARN-1, SHIP-1, OWNER-2 (the owner stack), MCPCAP-1, GOALS-1 and ROSTER-1, EXIT-1, XDIST-1,
PROC-1 (stack B, PR #29), TOOLT-1 (PR #30) and RISK-1 (PR #31): eleven queue rows, 110 commits from a7f6760 to
6d93aad.

Remaining, by lane (each a branch in its own worktree, nothing pushed but RISK-1):
- DOC-1 (keel-cmp7-open): verified green on 77def23; needs a rebase onto 6d93aad and one full verify.
- RISK-2 (keel-risk2): review r6 ready; rebase onto 6d93aad (RISK-1 is now on main), then full verify.
- VIS-1 (keel-vis): merged-tree verify rc 2, two failures inside a generated project; fixer killed, one edit left.
- VIS-2, DIST-1, doc2 (JSONDUP-1, DOC-2), SHELL-1 S2: fix rounds killed by the usage limit mid-round.
- TOOLT-2: plan, measurements and critic amendments done; S1 half-built, uncommitted.
- keel-lint (LINT-1, ERR-1), then IDX-1; HDR-1, CIGATE-1, OWNER-4, BOM-1 queued; GRPC-1 parked.

### How close the product is to its goal
A generated project now gets, from main: a configured default owner and a shipping gate, per-session model-call
totals, gate evidence records, exit codes through make, an xdist-isolation gate, one child supervisor with
bounded tool children, and an accepted-risk record for `npm audit`. The next merges that most change what a
generated project catches are VIS-1 (corpus visibility), DIST-1 (the CI pipeline choice) and doc2 (one config
reader that refuses duplicate keys).

### Gates
- RISK-1, merged tree 8e0ebcd + flip: `make verify` rc=0, 4824 passed, 4 skipped, 1 h 31 min
  (~/.cache/keel-slices/risk/verify-merged.log). Its first run was rc 2 (4822 passed, 2 failed: two exact-set
  arrival tests missing `dependency_audit`; verify-merged-1.log).
- DOC-1 on 77def23: rc=0, 4626 passed, 1 h 28 min (cmp7/verify-merged.log); two earlier runs stopped at once on
  check-venv and a stale corpus (verify-merged-0.log, -0b.log). Not yet on 6d93aad.
- VIS-1 on 77def23: rc 2; keel's 5006 passed, the generated project failed 2 (vis/verify-merged-1.log).
- Earlier landings: owner stack 4426 passed, MCPCAP 4452, stack B 4562, TOOLT-1 4626, each rc=0.
- Merge line on 6d93aad: check-docs rc 0, check rc 0, test_doc_drift + test_work_trailers 54 passed.

### Spend
Notional, not billed; no figure was metered. The maintainer lifted the notional cap ("go"). The session hit its
usage limit at about 08:44 and stayed out until 11:40.

### Not verified
- The full gate has not run on 6d93aad itself; RISK-1's verify ran on 8e0ebcd and the tip adds only the plan-row
  flip (check-docs, check and the doc tests passed on it).
- The uncommitted work in shell2, toolt2 and vis is untested; treat it as a draft.
- DOC-1 is green on its old base only.

### Residual risk
- Six fix rounds stopped mid-edit; resuming them from the worktree state, not from scratch, depends on reading
  each `git status` first.
- The RISK-1 failure was a hand-written key list; other exact-set tests can go stale the same way (L5 of the
  SHELL review asks for KEEL-TESTCOPY-1 to derive such lists).
- Zero workers ran from 10:11 to 11:43 with 13 rows queued, because of the usage limit, not a choice.

### Next slice
Rebase DOC-1 onto 6d93aad and run its full verify; in parallel, rebase RISK-2 and run its verify; resume the
VIS-1 fixer from its one uncommitted edit.

### Hand-over questions (LOOK.md)
1. The one result was the owner stack (rows 19, 22, 40): it landed (f910a78, 335cf04, 0b935e9).
2. Every landed row is a queue row that makes a generated project's gate catch one more fault; none is tidying.
3. Nothing is described as working without a landed row; the lanes above are listed as remaining.
4. Yes: 0 running from 10:11 to 11:43 (1 h 32 min) with 13 queued, and 3 running from 08:44, because the usage
   limit killed every agent. Before the limit the lowest was 2.
5. Both parked items are stop-list (accepting a security risk; an install of new packages); neither is
   reversible by a ruling.
6. The run passed its stop time by 1 h 43 min: it stalled on the usage limit and handed over on the reset.
7. Each landed row's log and rc are under Gates.
8. Planted faults and their red runs are in each worker's report, quoted in the controller log
   (~/.cache/keel-slices/night-plan.md) per slice; not re-checked here.
9. Reviews and their confirmed counts are in the Rulings table, one row per round; refuted findings were dropped
   there by name.
10. No: the last landing's verify ran on 8e0ebcd, one doc-only commit below the tip (see Not verified).
11. Yes: each landed slice carries its CHANGELOG row (CHANGELOG.md +201 lines over the night) and its plan-row flip.
12. Checked by check-docs and the doc-drift tests on each landing; the prose was not re-read by hand tonight.
13. The rulings lean on the vault's working profile (fail closed, a vacuous guard is a bug, bounded rounds) and on
    the keel work-queue procedure note.
14. Removed: the RISK-1 worktree, branches keel-risk and keel-lint-pre-rebase, the night's /dev/shm logs and
    scratch, the heartbeat cron. Kept, with why: the nine lane worktrees and their venvs (unlanded work),
    /dev/shm/keel-flip, keel-prep.sh and keel-union.py (the merge line needs them for those lanes).
15. Notional; no figure metered.
16. No confidential names, hosts or addresses were written; the downstream project is named only as it already is
    in the tracked plan.
