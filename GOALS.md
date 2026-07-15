# Link Ventures Prep

**Job starts:** Monday, August 3, 2026
**Role:** Internal tooling / building at Link Ventures

## What I'm working toward

Three prep tracks, all feeding the same larger goal: get hands-on and
comfortable with modern AI-assisted, end-to-end building.

**Track 1 — Technical infrastructure (Link Ventures internal tooling):**
- Agent loops & orchestration (ReAct-style reason → act → observe cycles, termination logic)
- Agent harness engineering (tools, context, memory, guardrails)
- Sandboxing agents (Docker Sandboxes, E2B, Modal — isolation vs. speed tradeoffs)
- Containers (Docker: images, Dockerfiles, Compose, registries)
- Cloud deployment (AWS: IAM, EC2 vs. ECS vs. Lambda, actually shipping a container)

**Track 3 — LLM training fundamentals + ternary quantization (added 2026-07-14):**
- Core: train a small transformer from scratch — own tokenizer, attention,
  activation layers, training loop — to build *in-practice* intuition for
  tokens/attention/activations, not just conceptual understanding
- Stretch: implement ternary weight quantization ({-1, 0, 1}) on top of that
  from-scratch model, following BitNet b1.58 (Ma et al., Microsoft Research,
  arXiv:2402.17764 — "The Era of 1-bit LLMs") as the inspiration/starting
  point, not necessarily the exact target architecture
- Why: the actual role involves training an LLM with ternary weight
  quantization, with the company's broader goal being to use ternary
  weights — whose matmul reduces to integer addition, no multiplication —
  to make photonics the primary compute substrate instead of GPUs
- See `llm-training/README.md` for the working plan

**Track 2 — Personal AI assistant (Hermes Agent by Nous Research):**
- Learning how to use Hermes and why its architecture (learning loop, persistent
  memory, skills system, runs-anywhere) is different from a normal chatbot
- Practicing it on real work-adjacent tasks: email/calendar triage, meeting
  summaries, scheduled digests

## Current priority order (as of 2026-07-15)

1. **`eval-harness/`** — DONE. All 8 planned tasks implemented (SQLite
   storage, Anthropic client wrapper, Docker-sandboxed code-gen scorer,
   Opus-as-judge API-design scorer, model configs/task suite, sequential
   runner, HTML/CSV report generator, docs), plus several follow-on fixes
   (temperature→effort handling for Sonnet configs, judge cost tracked
   separately from subject cost, reports scoped to the latest run by
   default, SQLite schema migration). See `eval-harness/README.md`'s
   "Status"/"Findings" sections for the latest full run's results.
2. **Track 3 — `llm-training/`** — infra done, core work not started. The
   `llm-training-fleet` Terraform plan (dedicated VPC, EC2 training box,
   S3 checkpoint bucket, fleet start/stop/ssh scripts) is fully built and
   provisioned for real on AWS, verified end-to-end (SSH, S3 read/write,
   stop/start Elastic IP stability), and left stopped. The actual Track 3
   goal — tokenizer, from-scratch Transformer, training loop, and the
   BitNet b1.58 ternary-quantization stretch goal — hasn't been started
   yet; see `llm-training/README.md`'s task checklist.
3. **Track 2** — Hermes Agent (`hermes-assistant/`, not yet started)
4. **Track 1 remainder** — `agent-capstone/` (the infra side of Track 1 is
   otherwise done: Docker, AWS deploy, and CI/CD all shipped; only the
   agent-capstone slot is still unstarted, and its scope may end up
   subsumed by `eval-harness/` — see that folder before restarting it)

## Source of truth

- Track 1 itinerary (Jul 3–7): `Link_Ventures_Prep_Itinerary.pdf`
- Track 2 itinerary (flexible, ~4-5 days, runs alongside Track 1): `Hermes_Prep_Itinerary.pdf`
- Task tracking: **Nick's Tasks Tracker** in Notion — all itinerary items from both
  tracks are logged there with effort level and assigned to me. Check status there, not here.
- This repo is for the *hands-on artifacts* (code, notes, configs) — Notion is for
  *task status*. Don't duplicate task tracking here.

## Mini-projects in this folder

| Folder | Maps to | Goal |
|---|---|---|
| `docker-101/` | Track 1, Day 2 | Get fluent with Docker: Dockerfiles, Compose, registries |
| `aws-deploy-demo/` | Track 1, Day 3 | Deploy the Day 2 container to AWS (ECS Fargate or Lambda) |
| `agent-capstone/` | Track 1, Days 4–5 | Superseded by `eval-harness/` — see its README |
| `eval-harness/` | Track 1, Days 4–5 | LLM eval harness: compare Claude models on code-gen + API-design tasks, Docker-sandboxed scoring, cost/quality tradeoffs |
| `llm-training/` | Track 3, all days | Train a transformer from scratch; stretch: ternary (BitNet b1.58-style) quantization |
| `hermes-assistant/` | Track 2, all days | Install, configure, and practice Hermes Agent for personal/work productivity |

## Picking this back up in a new session

If I'm starting a new chat/session and want continuity: read this file first, then
check the relevant subfolder's `README.md` for where that specific mini-project stands.
Update the "Status" line in a subfolder's README as things progress so future-me (or
Claude) doesn't have to re-derive it.
