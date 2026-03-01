# SLO Business Flow — Meridian Marketplace

Sequence diagram showing the full lifecycle: a business goal drives an SLO definition,
Prometheus detects a breach, the AI agent enriches the alert with business context,
and operators receive an actionable notification.

```mermaid
sequenceDiagram
    participant PO as Product Owner
    participant SLO as OpenSLO Definitions
    participant Prom as Prometheus
    participant AM as Alertmanager
    participant WH as FastAPI Webhook
    participant Agent as AI Agent
    participant DB as PostgreSQL
    participant Dash as Dashboard / Notify

    PO->>SLO: Define business goal<br/>("checkout p99 < 500ms")
    SLO->>Prom: Generate recording &<br/>alerting rules

    Note over Prom: Continuous metric evaluation

    Prom->>Prom: SLO breach detected<br/>(error budget burn)
    Prom->>AM: Fire alert<br/>(labels: slo_name, severity)
    AM->>AM: Deduplicate & group
    AM->>WH: POST /alert webhook
    WH->>Agent: Forward parsed alert

    Agent->>DB: Query SLO definition &<br/>business goal metadata
    DB-->>Agent: Return context<br/>(goal, owner, team, impact)

    Agent->>DB: Query recent deployments &<br/>service dependencies
    DB-->>Agent: Return operational context

    Agent->>Agent: Enrich alert with<br/>business impact summary

    Agent->>DB: Store EnrichedAlert record
    Agent->>Dash: Push enriched notification<br/>(business context + suggested actions)

    Note over Dash: Operator sees:<br/>- Which business goal is at risk<br/>- Error budget remaining<br/>- Suggested response
```

## Legend

| Symbol | Meaning |
|--------|---------|
| Solid arrow (`->>`) | Synchronous request / action |
| Dashed arrow (`-->>`) | Response / return data |
| Note | Contextual annotation |
| Participant | System component or role |
