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

# llm-training-fleet SDD progress (branch: worktree-llm-training-track-planning)

Plan: docs/superpowers/plans/2026-07-14-llm-training-fleet.md

BASE commit: 0342bdf

Task 1: complete (commits 0342bdf..5c7911b, review clean — Approved, no findings)
Task 2: complete (commits 5c7911b..75a307c, review clean — Approved, no findings)
Task 3: complete (commits 75a307c..0ee0780, review clean — Approved, no findings)
Task 4: complete (commits 0ee0780..8138c65, review found extra unrequested lock-file commit inconsistent with Task 1 precedent — fixed via non-interactive rebase dropping it, re-reviewed and approved)
Task 5: complete (commits 8138c65..ba89c89, review clean — Approved, no findings; did not repeat Task 4's lock-file mistake)
Task 6: complete (commits ba89c89..81bc8f0, review clean — Approved. Minor findings, both plan-inherited not implementer defects: (1) .ssh dir created by root without explicit chmod/chown, only the two files inside get 600/ec2-user; (2) no idempotency guard on git clone if user-data re-runs. Not blocking.)
Task 7: complete (commits 81bc8f0..7c4758a, review clean — Approved. Minor findings, both plan-inherited: (1) terraform fmt alignment gap copied verbatim from the brief's own snippet, repo isn't fmt-enforced anywhere yet; (2) associate_public_ip_address=true is redundant given the EIP but harmless, brief's own design. Not blocking.)
Task 8: complete (commits 7c4758a..2f8d12f, review clean — Approved, no findings. Critical EIP-vs-instance-IP constraint independently verified by reviewer.)
Task 9: complete (commits 2f8d12f..00233ce, review clean — Approved. Minor findings, both plan-inherited: (1) fleet_start.sh SSH-poll loop has no timeout; (2) no empty-output guard on terraform output -raw before use. Not blocking.)
Task 10: complete (commits 00233ce..e3f65cd, review clean — Approved, no findings. All cross-references independently verified against source by reviewer.)

STATUS: Tasks 1-10 complete (all file-writing). Proceeding to final whole-branch review before Task 11 (real terraform apply — requires explicit user go-ahead).
Final whole-branch review: complete (base 8f240e8..e3f65cd). Ready to merge: Yes. 3 Important cross-task integration findings that only surface at real-apply time: (1) sudo -u ec2-user git clone could fail publickey auth due to $HOME handling — fixed with -H flag (commit 2141594); (2) Task 11 checklist missing deploy-key precondition reminder — added (commit 5cfc965); (3) Task 11 S3 verification recipe required s3:ListAllMyBuckets, a permission the least-privilege IAM policy deliberately withholds — rewritten to use terraform output instead (commit 5cfc965). Also applied 2 minor cleanups: terraform fmt on ec2.tf/network.tf (d1dea0b), gitignore real *.tfvars (0e3510c). Fix pass re-reviewed and confirmed all resolved, no new issues, ready for Task 11 (commits e3f65cd..0e3510c).
Note: this environment's AWS credentials (nick-link-sandbox) lack ssm:GetParameter, so terraform plan/apply cannot be exercised end-to-end from this worktree/job — confirmed via git-stash comparison this is a pre-existing environment limitation, not a code defect. Flag for whoever runs Task 11 for real.

STATUS: Tasks 1-10 complete, reviewed, and fixed. All infra file-writing work merged into branch worktree-llm-training-track-planning (18 commits ahead of main: 4 planning/spec docs + 14 SDD-executed), later squash-merged into main via PR #21 (commit 3daa849).

**Update 2026-07-15:** Task 11 is now complete — `terraform apply` was run for real from the main checkout against a live AWS account. All 9 resources (VPC, subnet, IGW, route table, security group, S3 bucket, IAM role/policy/instance profile, key pair, EC2 instance, Elastic IP) are provisioned and verified end-to-end (SSH via deploy key, repo clone, S3 read/write via the scoped IAM role, stop/start cycle with stable Elastic IP), then left stopped. One real gap hit during `apply` not caught by prior reviews: the security group description's em dash/apostrophe tripped AWS's `CreateSecurityGroup` ASCII-only validation — fixed in commit 18bf054 (`network.tf`, plus committing the provider lock file). Also: this account's Free Tier restriction rejected the `t3.medium` instance-type default, so the live instance runs `t3.small` instead, set via a local (gitignored) `terraform.tfvars` override — see `llm-training/terraform/README.md`'s "Provisions" and "Cost notes" sections and `docs/superpowers/specs/2026-07-14-llm-training-fleet-design.md`'s Architecture section, both now updated to reflect this. STATUS: llm-training-fleet plan fully complete; the fleet is provisioned, verified, and stopped. Next work on Track 3 is the *core* model (tokenizer/attention/transformer/training loop) per `docs/superpowers/specs/2026-07-14-llm-training-core-design.md` — not further fleet work.
