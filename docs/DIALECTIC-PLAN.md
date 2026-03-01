# Hegelian Dialectic Planning: SLO-Enriched Alert System

**Date:** 2026-02-28
**Method:** Thesis (Gemini) / Antithesis (Claude Opus) / Synthesis — 3 rounds

---

## Question 1: What Should the AI Agent Actually DO When It Receives an SLO Breach?

### THESIS (Gemini)

**Position: "Augmented Intelligence" — Build a diagnostic assistant first, remediator second.**

Gemini advocates a three-phase approach:

1. **Phase 1 — Diagnostic Assistant (Read-Only):** The agent's highest-leverage activity is rapid root-cause analysis. On alert, it queries Prometheus (golden signals for the affected service and dependencies), Loki (error logs), K8s API (recent deployments/rollouts), and traces (Jaeger/OTel). It feeds this correlated data into an LLM to generate a hypothesis, then posts a structured diagnostic report to Slack: what SLO breached, evidence gathered, hypothesis, and recommended runbook.

2. **Phase 2 — Human-in-the-Loop Remediator:** Once trust is earned, the agent proposes concrete `kubectl` commands alongside Slack approval buttons. Execution happens via one-time K8s Jobs with narrowly-scoped RBAC ServiceAccounts. Every action is audited.

3. **Phase 3 — Scoped Autonomy:** Only for narrow, well-understood problems (e.g., OOMKilled pods). Requires machine-readable autonomy policies (OPA), confidence thresholds, and mandatory circuit breakers that auto-revert failed actions.

**Key tech:** FastAPI webhook, LLM (Claude/GPT/Gemini), RAG over runbooks via vector DB (ChromaDB/pgvector), read-only K8s RBAC, Slack Block Kit for interactive approval.

**Gemini's core argument:** Invest 90% in Phases 1-2. A transparent "glass box" diagnostic assistant cuts MTTR far more safely than premature automation.

### ANTITHESIS (Claude Opus)

**Position: "Start with the boring stuff" — The agent should do deterministic, composable actions before any LLM reasoning.**

Gemini's vision is seductive but inverted. It starts with the hardest, most expensive, most failure-prone component (LLM-powered diagnosis) and treats simple automation as a later phase. This is backwards. Here's why:

**1. LLM diagnosis is a luxury; structured triage is a necessity.**
Before the agent can generate useful hypotheses, it needs to reliably do boring things: parse the alert, look up the SLO definition, check the error budget burn rate, determine severity, and route to the correct channel/team. These are deterministic operations that don't need an LLM and shouldn't depend on one. If your LLM provider has an outage during your SLO breach, you still need triage to work.

**2. The "diagnostic report" is only useful if it's consistently right.**
An LLM that generates a wrong hypothesis during an incident is worse than no hypothesis at all — it sends the on-call engineer down a false trail. The RAG-over-runbooks approach sounds clean but in practice requires: (a) runbooks that are actually maintained and accurate, (b) embeddings that reliably retrieve the right runbook, (c) an LLM that correctly reasons about operational context. Each of these is a hard problem. Shipping an unreliable diagnostic system destroys trust permanently — you don't get a second chance.

**3. Simple automated actions are safer than LLM-guided ones.**
Gemini puts "propose a kubectl command" in Phase 2, gated by human approval. But the simplest, highest-value automations don't need LLM involvement at all:
- **Automated data gathering:** On SLO breach, immediately pull recent pod events, deployment history, and resource utilization — no LLM needed, just K8s API calls and Prometheus queries. Attach this structured data to the alert notification.
- **Runbook linking:** Match the `slo_name` label to a runbook URL via a simple lookup table (a ConfigMap or annotation). No embeddings needed.
- **Escalation routing:** Use SLO severity + service ownership metadata to route to the correct PagerDuty service. Deterministic, reliable, testable.

**4. The feedback loop should exist from day one, not Phase 2.**
Every alert the agent processes should be logged with the full context (alert payload, SLO definition, actions taken, outcome). This structured dataset is what eventually makes LLM-powered features viable — but you need to be collecting it from the start, not waiting until you've already built the LLM pipeline.

**5. Circuit breakers aren't enough for Phase 3.**
Gemini's "auto-revert after 5 minutes" circuit breaker assumes the action is cleanly reversible. Many Kubernetes operations aren't — a rollback that triggers a migration, a scale-up that exhausts cluster resources, a restart that clears an in-memory cache. The risk model needs to be action-specific, not time-based.

**Opus's counter-proposal:** Build bottom-up:
- **Layer 0:** Reliable alert parsing + SLO enrichment (already exists)
- **Layer 1:** Structured data gathering (K8s events, Prometheus context queries) — deterministic, no LLM
- **Layer 2:** Deterministic routing + runbook linking + escalation
- **Layer 3:** LLM-powered summarization of the data gathered in Layers 0-2
- **Layer 4:** LLM-powered diagnosis (only after Layer 3 has proven accurate)
- **Layer 5:** Proposed actions (only after diagnosis is trusted)

### SYNTHESIS

**Agreed direction: Build deterministic layers first, add LLM capabilities as enrichment on a proven foundation.**

Both positions agree on:
- The agent should NOT start with full autonomy
- Human-in-the-loop is the right trust model for write operations
- Structured data gathering is high-value and low-risk
- Feedback/audit logging is essential

The synthesis reconciles the disagreement on *when to introduce LLMs* and *what order to build features*:

**Concrete plan:**

| Phase | What | LLM? | Timeline |
|-------|------|------|----------|
| **0. Enrich** | Parse alert → attach OpenSLO definition → structured log | No | Current (done) |
| **1. Gather** | On alert, auto-query: K8s events for affected deployment, Prometheus error budget burn rate, pod resource utilization. Attach as structured JSON to notification. | No | Next sprint |
| **2. Route** | Deterministic escalation: severity from burn rate, team from service ownership labels, channel from routing config. Runbook link from lookup table. | No | Same sprint |
| **3. Summarize** | LLM takes structured data from phases 0-2 and generates a human-readable incident summary. This is low-risk because the LLM is summarizing facts, not generating hypotheses. | Yes (summarization only) | Following sprint |
| **4. Diagnose** | LLM generates root-cause hypotheses from gathered data + runbook context (RAG). Clearly labeled as "AI suggestion" in notifications. | Yes (reasoning) | After trust metrics show Phase 3 summaries are accurate |
| **5. Propose** | LLM suggests concrete remediation actions. Human approval required via Slack buttons or GitOps PR. | Yes (action proposal) | After diagnosis accuracy is validated |

**Key architectural decisions:**
- **Every phase is independently deployable and independently valuable.** If LLM phases fail or are disabled, phases 0-2 still function.
- **Feedback logging from Phase 0 onward.** Store every alert + context + actions taken. This dataset enables LLM evaluation before you turn on LLM features.
- **OPA for action policies** (from Gemini's Phase 3) but also for **routing policies** in Phase 2. Unify the policy layer early.
- **Structured data format** for inter-phase communication. Each phase outputs to a standard envelope (alert + SLO + gathered_context + routing + summary + diagnosis + proposed_actions). Downstream phases consume upstream outputs.

---

## Question 2: How Should OpenSLO Definitions Be Managed at Scale?

### THESIS (Gemini)

**Position: "GitOps-first, automated, highly standardized" — SLOs as first-class infrastructure-as-code.**

Gemini advocates:

1. **Git as single source of truth.** OpenSLO YAML files organized by team/service/type in a dedicated repository. Every change is a PR with review.

2. **Multi-layer validation pipeline:**
   - Schema validation (`yamllint`, JSON Schema against OpenSLO spec)
   - Semantic validation (custom tool verifies metrics actually exist in Prometheus)
   - Generated rule validation (`promtool check rules`)

3. **Generation from service metadata — the "Golden Path."** Services annotate their K8s manifests with SLO requirements (e.g., `slo.example.com/latency-target: "99p500ms"`). A generation tool (Jsonnet, ytt, or custom CLI) reads these annotations and produces OpenSLO YAML. This prevents manual SLO sprawl.

4. **Decentralized ownership, centralized governance.** Service teams own their SLOs via PRs. Platform/SRE team provides tooling, templates, and review guardrails.

5. **Full CI/CD integration:** Lint → validate schema → validate semantics → generate rules → validate rules → deploy via ArgoCD/Flux (pull-based GitOps).

**Key tech:** Git, yamllint, Jsonnet/ytt, `sloctl`, `promtool`, ArgoCD/Flux, PrometheusRule CRDs.

### ANTITHESIS (Claude Opus)

**Position: "You're over-engineering for a problem you don't have yet" — Start with convention over configuration.**

Gemini's proposal is a full-blown SLO platform. It's the right answer for an organization with 50+ services and 5+ teams. For this project — a PoC with a single example service — it's a cathedral when you need a tent.

**1. The "Golden Path" generation approach has hidden costs.**
Generating OpenSLO from K8s annotations sounds elegant, but it creates a tight coupling between deployment manifests and SLO definitions. Now every service deployment is also an SLO deployment. If the generation tool has a bug, it can silently corrupt your SLOs across the fleet. If a team wants an SLO that doesn't fit the template, they're fighting the system. The "escape hatches" that Gemini acknowledges are needed will proliferate and become the actual system.

**2. A dedicated SLO repository is premature separation.**
Gemini proposes organizing SLOs in a centralized `slos/` repository. But SLOs are meaningless without the services they measure. They should live *with* the service code, not in a separate repo that requires cross-repo coordination for every change. The "decentralized ownership" model actually works better when each service repo contains its own `slos/` directory — the team that changes the service also changes the SLOs in the same PR.

**3. Semantic validation against Prometheus is fragile.**
Verifying that a metric exists in Prometheus during CI assumes Prometheus is available to your CI pipeline, the metric has already been scraped (chicken-and-egg problem for new services), and label sets are stable. In practice, this validation will flake. A better approach: validate the OpenSLO definition against a known metric catalog (a static document listing standard metric names and labels), not a live system.

**4. Jsonnet/ytt add tooling burden without proportional value at this scale.**
These are powerful tools, but they require the team to learn and maintain another configuration language. For < 20 services, copy-and-modify from a well-documented template is faster and more accessible. The generation pipeline can be introduced when the copy-paste pain actually materializes.

**5. The lifecycle question is the real hard problem — and Gemini underplays it.**
What happens when a service is decommissioned? When SLI metrics change names? When an SLO target needs to change mid-incident? Gemini's answer is "remove via PR" and "retain historical data." But the operational reality is messier: orphaned SLOs that fire alerts for services nobody owns, SLOs with targets that no longer reflect business reality, generated rules that diverge from the definitions they were generated from.

**Opus's counter-proposal:**
- **SLOs live in the service repo**, in a `slos/` directory next to the code
- **Convention over configuration:** Standard metric names → standard SLO templates → minimal customization points (target percentile, threshold, window)
- **Validation is schematic only** in CI; semantic validation happens at deploy time (the Prometheus Operator rejects invalid PrometheusRule CRDs naturally)
- **No generation pipeline initially.** Hand-write OpenSLO YAML from templates. Introduce generation only when you have 10+ services and the patterns are clear.
- **Ownership = code ownership.** CODEOWNERS in the service repo covers SLOs too. No separate governance process.

### SYNTHESIS

**Agreed direction: SLOs co-located with services, convention-driven, with a clear graduation path to platform tooling.**

Both positions agree on:
- Git version control for SLO definitions
- Validation in CI is necessary
- Service teams should own their SLOs
- Templates/conventions reduce inconsistency

The synthesis resolves *where SLOs live*, *how much tooling to build now*, and *when to graduate*:

**Concrete plan:**

**Now (PoC → Early Adoption):**
- SLO definitions live in each service's repo under `slos/` directory
- Provide a **starter template** (a well-commented OpenSLO YAML) that teams copy and customize
- Validation in CI: `yamllint` + OpenSLO JSON Schema validation + `promtool check rules` on generated output
- No Jsonnet/ytt — plain YAML from templates
- A simple Makefile target or shell script converts OpenSLO → PrometheusRule CRD (wrapping `sloctl` or equivalent)
- CODEOWNERS covers `slos/` directory

**Growth (5-15 services):**
- Extract common patterns into a **shared library** of OpenSLO snippets/templates in a central repo (consumed as a Git submodule or package)
- Add a **metric catalog** — a static YAML file listing standard metric names, types, and labels. Validate OpenSLO definitions against this catalog in CI.
- Introduce **SLO dashboard generation** from OpenSLO definitions (Grafana JSON models)

**Scale (15+ services):**
- Consider Jsonnet/ytt or a custom generator for teams that have highly repetitive SLOs
- Centralized SLO registry (read-only aggregation of all service-level SLOs for platform-wide visibility)
- ArgoCD ApplicationSets for automated deployment of PrometheusRule CRDs from service repos
- SLO lifecycle automation: detect orphaned SLOs when services are removed from the service catalog

**Key architectural decisions:**
- **Co-location over centralization.** SLOs live with the service. A central registry aggregates but doesn't own.
- **Convention before configuration.** Standard metric names + standard templates = minimal tooling needed
- **Graduation triggers are explicit:** "When you have N services doing X, introduce Y." Not "build Y now because you'll need it someday."
- **Schema validation in CI, semantic validation at deploy time.** Don't fight the chicken-and-egg problem with new services.

---

## Question 3: How Should This System Evolve from PoC to Production?

### THESIS (Gemini)

**Position: "Robust, deterministic foundation with LLM enrichment layered on top — Jarvis, not Skynet."**

Gemini proposes:

1. **Trust boundaries via GitOps:** No direct K8s API calls for automated actions. The AI agent creates PRs against service config repos; ArgoCD/Flux applies the changes. The PR is the air gap and audit trail.

2. **Multi-tenancy:** Move to Thanos/VictoriaMetrics for scalable multi-tenant TSDB. Tenant = service team. Config in tenant-specific Git repos. Agent API is tenant-aware with authentication.

3. **LLMs vs deterministic rules — false dichotomy:** Prometheus rules are the trigger (deterministic). LLM enrichment via RAG pipeline (LangChain/LlamaIndex) gathers logs, traces, deployment info, runbooks, and generates a contextual summary + recommendation.

4. **Feedback loops via Slack buttons:** "Helpful" / "Not Helpful" on every alert notification. Feedback stored in PostgreSQL. Dataset for future fine-tuning and accuracy reporting.

5. **Integration hub pattern:** `Alertmanager → AI Agent → PagerDuty + Slack + Jira`. Agent calls PagerDuty API, posts Slack Block Kit messages, pre-fills Jira tickets.

**Three milestones:**
- **M1:** Deploy to real K8s cluster, Thanos, formalize agent API, implement enrichment pipeline → Slack summaries
- **M2:** GitOps rollback proposals (PRs), PagerDuty integration, Slack feedback buttons, PostgreSQL feedback store
- **M3:** Multi-tenant refactor, tenant onboarding process, internal dashboard for health/feedback trends

### ANTITHESIS (Claude Opus)

**Position: "You're planning a production system without validating the core value proposition" — Prove the enrichment is useful before scaling anything.**

Gemini's milestones are infrastructure-heavy and value-light. Milestone 1 includes migrating to a real K8s cluster, deploying Thanos, and formalizing the agent API — but the actual user-facing output is still just "a Slack message." Before investing in production infrastructure, we need to prove that the enriched alert is actually better than a raw Alertmanager notification.

**1. The GitOps-for-remediation pattern is overkill for early milestones.**
Creating PRs for rollbacks is elegant, but it requires: a GitOps operator deployed and configured, service repos structured for GitOps, PR review workflows that work at incident speed, and an LLM reliable enough to generate correct config changes. This is a massive surface area. For early milestones, the agent should just tell humans what to do — a notification with the right context and a runbook link. Humans can run their own `kubectl` commands.

**2. Multi-tenancy is a milestone 5 problem, not milestone 3.**
Refactoring for multi-tenancy before you have a second tenant is speculative engineering. Build for a single team first. Get that team to actually use the system daily. Their feedback will shape the multi-tenancy requirements far more accurately than upfront design.

**3. Thanos/VictoriaMetrics migration is a distraction.**
The PoC runs on kube-prometheus-stack. A single Prometheus instance handles tens of thousands of time series without issue. Migrating to Thanos is an infrastructure project that delivers zero user-facing value. It's needed at scale, but scale is not the current bottleneck — usefulness is.

**4. The feedback mechanism is too abstract.**
"Helpful / Not Helpful" on a Slack message measures sentiment, not accuracy. What you actually need to know: Was the gathered context correct? Was the runbook link relevant? Did the summary miss critical information? This requires structured feedback, not binary voting. And it requires an actual incident to validate against.

**5. The real risk is not technical — it's adoption.**
The system could be perfectly architected and nobody uses it because: alerts are already going to PagerDuty and adding another notification channel creates confusion, on-call engineers don't trust AI summaries because they've been burned by hallucinations, or the enriched context doesn't actually contain information the engineer didn't already know. These are adoption risks, not architecture problems, and they need to be validated experimentally.

**Opus's counter-proposal for milestones:**

- **M1: Prove enrichment value with real incidents.** Deploy to a staging/dev K8s cluster (not production). Wire the agent to Alertmanager for a single real service. The agent posts enriched alerts to a Slack channel alongside the raw Alertmanager notification. Engineers compare side-by-side. Measure: does the enriched version contain information engineers actually find useful? No LLM required — just structured data gathering.

- **M2: Add LLM summarization, validate accuracy.** With 4-6 weeks of enriched alerts + engineer feedback, introduce LLM summarization. Run it in shadow mode first: generate summaries but don't send them to users. Have 2-3 engineers review a batch of summaries against actual incident outcomes. Measure accuracy. Only then ship LLM summaries to the channel.

- **M3: Integration and trust-building.** Once summarization is proven accurate, integrate with PagerDuty (enrich existing alerts, don't add a new notification channel). Add runbook linking. Add the Slack feedback mechanism — but structured: "Was the root cause suggestion correct? Yes/No/Partially." Build the feedback dataset that informs whether Phase 4 (diagnosis) is viable.

### SYNTHESIS

**Agreed direction: Validate value before scaling, but design the interfaces for future scale from the start.**

Both positions agree on:
- LLMs are enrichment, not decision-makers
- Feedback loops are non-negotiable
- PagerDuty/Slack/Jira integration is the right target
- Trust must be earned incrementally

The synthesis resolves *what to build when* and *how to validate before investing*:

**Concrete milestones:**

### Milestone 1: "Prove the Enrichment" (4-6 weeks)

**Goal:** Demonstrate that SLO-enriched alerts are measurably more useful than raw Alertmanager notifications.

| Component | Action | Notes |
|-----------|--------|-------|
| **Infrastructure** | Deploy to a shared dev/staging K8s cluster (not Thanos — keep kube-prometheus-stack) | Minimum viable infrastructure |
| **Agent** | On SLO breach: gather K8s events, error budget burn rate, recent deployments, pod resource stats | Deterministic data gathering, no LLM |
| **Notification** | Post enriched alert to Slack channel alongside raw alert | Side-by-side comparison for engineers |
| **Routing** | Deterministic severity + team routing from SLO metadata and service labels | Simple config map, not OPA yet |
| **Feedback** | Engineers note in a shared doc: "Was the extra context useful? What was missing?" | Lightweight, qualitative |
| **SLOs** | Co-located in service repo, template-based, schema-validated in CI | Per Question 2 synthesis |

**Exit criteria:** 3+ engineers confirm the enriched alert saved them time in 3+ real (or exerciser-simulated) incidents.

### Milestone 2: "Trust the Summaries" (4-6 weeks)

**Goal:** Add LLM summarization, validate accuracy before shipping to users.

| Component | Action | Notes |
|-----------|--------|-------|
| **LLM Pipeline** | LLM summarizes structured data from M1 into human-readable incident summary | Summarization only, not diagnosis |
| **Shadow Mode** | Generate summaries for all alerts, store but don't display | Accumulate evaluation dataset |
| **Accuracy Review** | 2-3 engineers review batch of summaries against actual outcomes | Binary + qualitative scoring |
| **Ship** | If accuracy > 80% on review, enable summaries in Slack notifications | Clearly labeled "AI Summary" |
| **Feedback** | Structured Slack feedback: "Summary accurate? Yes/Partial/No" + optional free text | Stored in PostgreSQL |
| **Integration** | PagerDuty enrichment (add context to existing PD alerts, don't create new notification channel) | Reduce noise, don't add to it |

**Exit criteria:** LLM summaries are ≥80% accurate on engineer review. PagerDuty integration is live for at least one service.

### Milestone 3: "Extend and Diagnose" (6-8 weeks)

**Goal:** Add root-cause diagnosis, runbook linking, and prepare interfaces for future scale.

| Component | Action | Notes |
|-----------|--------|-------|
| **Diagnosis** | LLM generates root-cause hypothesis from gathered data | Labeled as "Suggested cause" |
| **Runbook Linking** | Match SLO name → runbook URL via lookup table (ConfigMap) | Deterministic, no RAG yet |
| **Action Proposals** | For validated diagnosis patterns, suggest specific commands | Human approval required |
| **Policy** | Introduce OPA for routing policies and action allow-lists | Foundation for future autonomy |
| **Interfaces** | Design agent API with tenant-aware authentication (even if single tenant) | Build the interface now, multi-tenant later |
| **Feedback** | "Was the diagnosis correct?" structured feedback | Informs whether RAG/autonomy is viable |

**Exit criteria:** Diagnosis accuracy validated. API interfaces designed for multi-tenancy. Decision made on whether to proceed to automated action proposals.

---

## Cross-Cutting Architectural Principles

These emerged from the dialectic and apply across all three questions:

1. **Deterministic first, probabilistic second.** Every LLM-powered feature must have a deterministic fallback. If the LLM is unavailable, the system degrades to structured data + routing, not silence.

2. **Co-locate with services, aggregate for visibility.** SLO definitions live in service repos. Agent config lives with the agent. A central registry provides platform-wide views but doesn't own the data.

3. **Validate before scaling.** Every capability must prove its value with real users before infrastructure is built to scale it. The graduation triggers are explicit and measurable.

4. **Design interfaces for scale, implement for today.** API contracts and data formats should accommodate multi-tenancy and pluggable LLM providers. But the implementation behind those interfaces should be the simplest thing that works.

5. **Feedback is a first-class feature, not an afterthought.** Structured feedback collection starts at Milestone 1 (qualitative) and evolves to structured (M2-M3). This dataset is the strategic asset that makes future AI capabilities possible.

6. **Adopt, don't add.** Integrate with existing tools (PagerDuty, Slack, Jira) by enriching their existing workflows, not by creating parallel notification channels that compete for attention.
