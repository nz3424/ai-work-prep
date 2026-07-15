# eval-harness SDD progress (branch: eval-harness-tasks-2-8)

Plan: docs/superpowers/plans/2026-07-06-eval-harness.md

Task 1: complete (merged to main via PR #1, commit 0d9fcd4 / 7740571 on main)
Task 8 (Steps 1-5, docs/integration): complete (commits 2b8589a..c80ae90, review clean — Approved, no findings). Step 6 (real end-to-end run against live Anthropic API, spends real money) deliberately deferred pending explicit user go-ahead.
Final whole-branch review: complete (base fa09c63..c80ae90). Found 2 Important integration bugs missed by per-task review: (1) PROMPT_VARIANT_SUFFIXES never applied — sonnet-terse was a no-op duplicate of sonnet-default; (2) scorer calls (Docker/judge) unguarded — any failure aborted the whole run and skipped report generation. Fixed in commit 7c3ed55, re-reviewed and approved. Minor findings deferred (not blocking): judge cost/rationale not tracked in ResultRow, max_tokens=2048 may truncate api_design responses, no markdown-fence stripping on generated code, run artifacts (eval_results.db/report.html/report.csv) not in .gitignore, no pids_limit on sandbox container.

STATUS: All automated implementation (Tasks 2-8 minus Task 8 Step 6) complete, tested, reviewed, and approved on branch eval-harness-tasks-2-8. Remaining: Task 8 Step 6 (real end-to-end run against live Anthropic API, spends real money + requires Docker) — deliberately deferred pending explicit user go-ahead. Full suite: 23/23 passing at commit 7c3ed55.

---

# eval-harness SDD progress (branch: worktree-eval-harness-judge-cost)

Plan: docs/superpowers/plans/2026-07-14-eval-harness-run-scoping.md (fixes issue #13: report blends all runs instead of scoping to latest)

BASE commit: 40b7065

STATUS: starting Task 1.
Task 1: complete (commits 40b7065..445fd14, review clean — Approved, no findings)
Task 2: complete (commits 445fd14..0a901f2, review clean — Approved, no findings)
Task 3: complete (commits 0a901f2..14afcb0, review clean — Approved; reviewer's cannot-verify-from-diff item on README/report.py accuracy resolved by controller via direct grep, confirmed accurate)

STATUS: All three tasks complete. Proceeding to final whole-branch review.
Final whole-branch review: complete (base 40b7065..14afcb0). Ready to merge: Yes. Minor findings (not blocking, noted in PR): (1) no generate_report test exercises the literal-run_id branch that run_eval.py's __main__ actually uses in production; (2) scatter-plot point labels in "all" mode don't include run_id, so same-config points from different runs are visually indistinguishable; (3) CSV has run_id as first column, HTML has it second (cosmetic only). All 32 tests passing.

STATUS: All work complete. Proceeding to finishing-a-development-branch.
