# Link Ventures Prep

**Job starts:** Monday, July 20, 2026
**Role:** Internal tooling / building at Link Ventures

## What I'm working toward

Two parallel prep tracks, both feeding the same larger goal: get hands-on and
comfortable with modern AI-assisted, end-to-end building.

**Track 1 — Technical infrastructure (Link Ventures internal tooling):**
- Agent loops & orchestration (ReAct-style reason → act → observe cycles, termination logic)
- Agent harness engineering (tools, context, memory, guardrails)
- Sandboxing agents (Docker Sandboxes, E2B, Modal — isolation vs. speed tradeoffs)
- Containers (Docker: images, Dockerfiles, Compose, registries)
- Cloud deployment (AWS: IAM, EC2 vs. ECS vs. Lambda, actually shipping a container)

**Track 2 — Personal AI assistant (Hermes Agent by Nous Research):**
- Learning how to use Hermes and why its architecture (learning loop, persistent
  memory, skills system, runs-anywhere) is different from a normal chatbot
- Practicing it on real work-adjacent tasks: email/calendar triage, meeting
  summaries, scheduled digests

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
| `agent-capstone/` | Track 1, Days 4–5 | Small end-to-end agent: loop + sandboxed tool execution, containerized, deployed |
| `hermes-assistant/` | Track 2, all days | Install, configure, and practice Hermes Agent for personal/work productivity |

## Picking this back up in a new session

If I'm starting a new chat/session and want continuity: read this file first, then
check the relevant subfolder's `README.md` for where that specific mini-project stands.
Update the "Status" line in a subfolder's README as things progress so future-me (or
Claude) doesn't have to re-derive it.
