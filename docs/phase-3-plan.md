# Phase 3 Implementation Plan: LLM Summarization

**Source:** PR #8 — Hegelian Dialectic Roadmap (`docs/DIALECTIC-PLAN.md`)
**Phase:** 3 ("Summarize") from the 6-phase agent capability roadmap
**Milestone:** M2 ("Trust the Summaries") from the evolution roadmap
**Prerequisites:** Phases 0-2 (Enrich, Gather, Route) must be operational

---

## Overview

Phase 3 introduces the first LLM-powered capability: taking the structured data produced by Phases 0-2 (alert payload, OpenSLO definition, K8s events, error budget burn rate, pod resource stats, routing metadata) and generating a human-readable incident summary.

This is deliberately scoped to **summarization only** — the LLM restates gathered facts in a readable format. It does NOT generate hypotheses, diagnose root causes, or propose actions (those are Phases 4-5).

### Why Summarization First

From the dialectic synthesis:
- Summarization is **low-risk** because the LLM is restating facts, not reasoning
- It provides immediate value: engineers get a concise briefing instead of raw JSON
- It builds trust incrementally — if summaries are accurate, it justifies investing in diagnosis (Phase 4)
- It has a clear **deterministic fallback**: if the LLM fails, Phases 0-2 data is still delivered raw

---

## Task Breakdown

### Task 3.1: Define the Structured Data Envelope

**What:** Formalize the data format that Phases 0-2 produce and Phase 3 consumes.

**Details:**
- Define a JSON schema for the "enriched alert envelope" containing:
  - `alert`: Raw Alertmanager payload (labels, annotations, status, timestamps)
  - `slo`: Parsed OpenSLO definition (objective name, target, window, SLI spec)
  - `context`: Gathered data from Phase 1 (K8s events, error budget burn rate, pod resource utilization, recent deployments)
  - `routing`: Phase 2 output (severity, owning team, channel, runbook URL)
- Store schema in `schemas/enriched-alert-envelope.json`
- Validate that the existing agent code (from TASK-3) can produce this envelope

**Acceptance criteria:**
- JSON schema exists and is documented
- At least one example envelope can be generated from a test alert
- Schema validation passes for the example

---

### Task 3.2: LLM Integration Module

**What:** Build a module that accepts an enriched alert envelope and returns a human-readable summary.

**Details:**
- Create `ai-agent/summarizer.py` (or equivalent module within the existing agent)
- Use the Anthropic SDK (Claude API) for summarization
- The prompt should:
  - Receive the full envelope as structured input
  - Output a concise incident summary (target: 5-10 sentences)
  - Include: what SLO breached, current burn rate, affected service, key events, severity, assigned team
  - NOT include: speculation, diagnosis, recommendations
- Implement a **deterministic fallback**: if LLM call fails (timeout, API error, rate limit), produce a template-based summary from the structured data fields
- Configuration via environment variables: `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_TIMEOUT_SECONDS`

**Acceptance criteria:**
- Given a valid enriched alert envelope, the module returns a readable summary
- LLM failure triggers the fallback template, not an error
- Summary content is factual (verifiable against the input envelope)

---

### Task 3.3: Shadow Mode Infrastructure

**What:** Generate summaries for all alerts but store them without displaying to users.

**Details:**
- Add a `SHADOW_MODE=true|false` environment variable to the agent
- When shadow mode is on:
  - Process every alert through the summarizer
  - Store the result (envelope + generated summary + metadata) to a persistent store
  - Do NOT include the summary in Slack/notification output
  - Log that a shadow summary was generated
- Storage options (pick simplest for PoC):
  - SQLite file mounted as a PVC (simplest)
  - PostgreSQL if already available in the cluster
  - JSON files in a mounted volume (fallback)
- Store: `timestamp`, `alert_fingerprint`, `envelope_json`, `summary_text`, `llm_model`, `llm_latency_ms`, `fallback_used`

**Acceptance criteria:**
- Shadow mode generates and stores summaries without affecting existing alert flow
- Stored summaries are retrievable for batch review
- Performance: summary generation adds < 5s latency to the alert pipeline (non-blocking is preferred)

---

### Task 3.4: Summary Accuracy Review Tooling

**What:** Build a simple tool for engineers to review stored shadow summaries.

**Details:**
- Create a CLI tool or simple script (`scripts/review-summaries.py`) that:
  - Lists stored shadow summaries (most recent first)
  - For each summary, displays: the raw envelope data and the generated summary side-by-side
  - Prompts for a rating: `accurate` / `partially_accurate` / `inaccurate` + optional free-text note
  - Stores the review result alongside the summary
- Generate an accuracy report: % accurate, % partial, % inaccurate, common failure patterns

**Acceptance criteria:**
- Reviewer can process summaries one at a time
- Accuracy metrics are computed and reported
- The review dataset accumulates over time

---

### Task 3.5: Slack Summary Delivery

**What:** When shadow mode is off and accuracy threshold is met, include the LLM summary in Slack notifications.

**Details:**
- Extend the existing Slack notification (from Phase 2 routing) to include an "AI Summary" section
- The summary must be clearly labeled: **"AI-Generated Summary"** header
- Slack Block Kit formatting:
  - Header block: alert name + severity
  - Section block: AI summary text
  - Context block: "Generated by [model name] — Feedback: Was this helpful?"
  - Actions block: three buttons — "Accurate" / "Partially Accurate" / "Inaccurate"
- Button clicks store structured feedback (same schema as Task 3.4 review)
- Gate: only enable when `SHADOW_MODE=false` (manually toggled after review confirms accuracy)

**Acceptance criteria:**
- Slack message includes the summary with clear AI labeling
- Feedback buttons work and store responses
- Without the LLM summary (fallback), message still renders with structured data only

---

### Task 3.6: Feedback Storage and Reporting

**What:** Persist all feedback (from review tooling and Slack buttons) and produce accuracy dashboards.

**Details:**
- Feedback schema: `timestamp`, `alert_fingerprint`, `summary_id`, `reviewer` (engineer name or "slack_user_id"), `rating`, `notes`
- Store in the same database as shadow summaries (SQLite/PostgreSQL)
- Reporting script (`scripts/feedback-report.py`):
  - Overall accuracy rate (accurate + partially / total)
  - Accuracy trend over time (weekly buckets)
  - Most common "inaccurate" failure modes (from notes)
- This dataset is the **exit criteria gate**: Phase 4 (Diagnosis) should only proceed if summary accuracy >= 80%

**Acceptance criteria:**
- Feedback from both CLI review and Slack buttons lands in the same store
- Accuracy report can be generated on demand
- Report clearly shows whether the 80% accuracy threshold is met

---

## Architecture Decisions

Per the dialectic synthesis, these principles govern Phase 3:

1. **Independently deployable.** Phase 3 can be enabled/disabled without affecting Phases 0-2. The `SHADOW_MODE` toggle and deterministic fallback ensure this.

2. **Deterministic fallback always available.** If Claude API is down during an incident, the agent still delivers structured data + template summary. No silence.

3. **LLM is stateless enrichment.** The summarizer module receives the full envelope and returns text. It has no memory, no session state, no access beyond the envelope contents.

4. **Feedback is a first-class feature.** Not an afterthought — it's what determines whether we proceed to Phase 4.

---

## Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| Phase 0 (Enrich) — alert parsing + SLO attachment | Required | Covered by existing TASK-3/TASK-4 |
| Phase 1 (Gather) — K8s events, burn rate, pod stats | Required | Must be implemented before Phase 3 is useful |
| Phase 2 (Route) — severity, team, channel, runbook | Required | Routing metadata included in envelope |
| Slack integration | Required | For Task 3.5 delivery |
| Claude API access | Required | For LLM summarization |
| Persistent storage in cluster | Required | For shadow mode + feedback |

---

## Exit Criteria (from Dialectic Plan)

Phase 3 is complete when:
- LLM summaries are generated for all alerts (shadow mode validated)
- Engineer review shows **>= 80% accuracy** on a batch of summaries
- Summaries are live in Slack notifications with feedback buttons
- Feedback pipeline is operational and producing accuracy reports
- Decision is documented: proceed to Phase 4 (Diagnosis) or iterate on Phase 3

---

## Estimated Scope

Per the dialectic roadmap, this is a **4-6 week milestone** (M2).

| Task | Estimated Effort | Blocking? |
|------|-----------------|-----------|
| 3.1 Define envelope schema | Small | Yes — everything depends on this |
| 3.2 LLM integration module | Medium | Yes — core capability |
| 3.3 Shadow mode infrastructure | Medium | Yes — needed before live delivery |
| 3.4 Review tooling | Small | No — can build while shadow data accumulates |
| 3.5 Slack delivery | Medium | Blocked by 3.2, 3.3 |
| 3.6 Feedback storage + reporting | Small | Blocked by 3.4, 3.5 |

---

## Open Questions

1. **Which LLM model?** The dialectic plan is model-agnostic. Recommendation: Claude Sonnet for cost/speed balance on summarization. Configurable via env var.
2. **Storage backend?** SQLite is simplest for PoC; PostgreSQL if the cluster already has one. Decision should be made when Phase 1-2 infrastructure is clearer.
3. **Async vs sync summarization?** Non-blocking (async) is preferred so the alert pipeline isn't delayed. But sync is simpler. Start sync, move to async if latency is a problem.
4. **How many shadow summaries before review?** The dialectic plan says "4-6 weeks of enriched alerts." Practical minimum: 20-30 summaries covering diverse alert types.
