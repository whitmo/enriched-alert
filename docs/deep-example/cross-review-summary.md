# Cross-Review Summary: Deep Example PRs #20–26

**Date:** 2026-02-28
**Reviewers:** Claude (Opus 4.6) + Gemini CLI (0.27.2)
**Method:** `gh pr diff <N> | gemini -p '...'` for Gemini; direct diff analysis for Claude

---

## Overview

| PR | Title | Blocking | NITs | Key Finding |
|----|-------|----------|------|-------------|
| #20 | Add deep-example directory structure and design docs | 0 (Gemini: 1*) | 3 | *Gemini flags missing source doc as blocking; Claude considers it acceptable for PoC |
| #21 | Security assessment: OWASP Top 10 + MITRE ATT&CK | 0 | 2 | Excellent, thorough assessment. **Conflicts with #23 and #25** |
| #22 | Add Meridian Marketplace deep example task documents | 0 | 1 | Well-structured task breakdown, clear dependencies |
| #23 | Security assessment: OWASP Top 10 + MITRE ATT&CK for Meridian Marketplace | 0 | 3 | More detailed than #21, includes resolved items. **Conflicts with #21 and #25** |
| #24 | Add Marp presentation for Meridian Marketplace deep example | 0 | 2 | Professional presentation with good Mermaid diagrams |
| #25 | Add security assessment for Meridian Marketplace | 0 | 3 | Most pragmatic of the 3 security PRs. **Conflicts with #21 and #23** |
| #26 | Add Mermaid architecture diagrams for Meridian Marketplace | 0 | 4 | Comprehensive diagram set, consistent formatting |

**Total: 0 blocking issues across 7 PRs. 18 NITs total.**

---

## Critical Finding: Triple Security Assessment Conflict

PRs **#21, #23, and #25** all create `docs/deep-example/security/security-assessment.md`. They will conflict on merge. Recommendation:

1. **Pick one** (suggest #25 — most pragmatic, best PoC vs Production separation) OR
2. **Merge best content** from all three into a single definitive assessment

### Comparison of the three security assessments:

| Aspect | #21 (zealous-otter) | #23 (witty-deer) | #25 (jolly-badger) |
|--------|---------------------|-------------------|--------------------|
| Length | ~370 lines | ~480 lines | ~400 lines |
| Resolved items tracked | No | Yes (PR c828b31) | Yes (PR c828b31) |
| Concrete K8s YAML examples | No | Yes | Yes |
| PoC vs Prod separation | Checklist table | Inline per section | Both (inline + appendix) |
| Alertmanager config example | No | Yes (NetworkPolicy) | Yes (bearer token) |
| Container hardening specifics | Basic | Detailed | Most detailed |
| Rate limiting recommendation | No | No | Yes (100 req/min) |

---

## Per-PR Details

### PR #20: Deep-example directory structure and design docs
**Branch:** `work/bold-eagle`

**Claude:** No blocking issues. Good scaffolding PR establishing `docs/deep-example/` with README, design.md, and placeholder directories. The `design.md` provenance note about missing `docs/research/rich-example-app.md` is honest and appropriate.

**Gemini:** Flags the missing source document as potentially blocking — recommends either locating `docs/research/rich-example-app.md` or explicitly promoting `design.md` as the new canonical source.

**Shared NITs:** Grafana listed under "Anomaly detection" is slightly misleading (visualization vs detection). README links to directory rather than specific files.

---

### PR #21: Security assessment (OWASP + MITRE ATT&CK)
**Branch:** `work/zealous-otter`

**Claude:** Comprehensive assessment correctly identifying unauthenticated webhook as highest risk. Self-monitoring paradox observation is insightful. Threat model summary table is actionable.

**Gemini:** Technically sound, no blocking issues. Minor cross-referencing and phrasing suggestions.

**Shared NITs:** Minor stylistic improvements only.

---

### PR #22: Meridian Marketplace task documents
**Branch:** `work/fancy-platypus`

**Claude:** Well-structured decomposition of 10 tasks with clear dependency DAG and testable acceptance criteria. Complexity estimates are reasonable.

**Gemini:** Clean PR, only minor clarification about ServiceMonitor CRD context.

**Shared NITs:** ServiceMonitor CRDs in TASK-05 vs TASK-08 functional context.

---

### PR #23: Security assessment (detailed, with resolved items)
**Branch:** `work/witty-deer`

**Claude:** Most detailed of the three security assessments. Includes concrete Alertmanager config examples and K8s NetworkPolicy YAML. Tracks resolved items (path traversal, yaml.safe_load).

**Gemini:** No blocking issues. Slightly inaccurate claim about Alertmanager not supporting auth headers.

**Shared NITs:** Alertmanager auth header phrasing (it *can* send auth, the endpoint doesn't validate). Formatting consistency.

---

### PR #24: Marp presentation
**Branch:** `work/kind-lion`

**Claude:** Professional dark-themed presentation with good narrative arc. Mermaid diagrams well-integrated. ASCII dashboard mockup is effective.

**Gemini:** Well-structured, no blocking issues. SLI/SLO table could be clearer on percentile-target relationships.

**Shared NITs:** Business Goals table could better explain SLI percentile vs SLO target relationship.

---

### PR #25: Security assessment (pragmatic, PoC-focused)
**Branch:** `work/jolly-badger`

**Claude:** Most pragmatic of the three security assessments. Best PoC vs Production separation. Includes low-effort/high-value PoC recommendations (pin deps, add USER, securityContext).

**Gemini:** No blocking issues. Minor phrasing and reference stability suggestions.

**Shared NITs:** Alertmanager auth phrasing (same as #23). PR c828b31 reference longevity.

---

### PR #26: Mermaid architecture diagrams
**Branch:** `work/calm-owl`

**Claude:** Five well-structured diagrams with consistent legend tables. ER diagram correctly models all 6 core entities. Deployment topology shows clear namespace separation.

**Gemini:** Comprehensive diagram set, no blocking issues. Minor naming consistency suggestions across diagrams.

**Shared NITs:** FastAPI dual role clarity, "Kind Cluster: podman-poc-cluster" specificity, cross-diagram naming consistency.

---

## Recommendations

1. **Resolve security assessment conflict** — PRs #21, #23, #25 target the same file. Merge one, close the other two.
2. **Resolve design.md provenance** — PR #20 should confirm whether `design.md` is the canonical source or a placeholder.
3. **All other PRs (#22, #24, #26) are clean** and can merge independently without conflicts.
4. **Merge order suggestion:** #20 first (scaffolding), then #22 (tasks), then #24 + #26 (presentation + diagrams), then one of #21/#23/#25 (security).
