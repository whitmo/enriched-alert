# Enrichment Pipeline — Meridian Marketplace

Detailed flowchart of the alert enrichment pipeline: from raw Alertmanager webhook
through parsing, database lookups, AI enrichment, persistence, and notification.

```mermaid
graph TD
    Start(("Alertmanager<br/>fires webhook"))

    subgraph "FastAPI Webhook Receiver"
        Receive["POST /alert<br/>receive raw JSON"]
        Validate{"Valid<br/>payload?"}
        LogRaw["Log raw alert<br/>for audit"]
        ParseLabels["Extract labels:<br/>slo_name, severity,<br/>service, namespace"]
    end

    subgraph "Database Lookups"
        LookupSLO["Query SLODefinition<br/>by slo_name"]
        SLOFound{"SLO<br/>found?"}
        LookupGoal["Query BusinessGoal<br/>via SLODefinition.business_goal_id"]
        LookupService["Query Service<br/>+ Team ownership"]
        LookupResponse["Query OperationalResponse<br/>(runbook, severity)"]
        LookupDeploys["Query recent deployments<br/>for affected service"]
    end

    subgraph "Enrichment Logic"
        CalcBudget["Calculate remaining<br/>error budget"]
        AssessImpact["Assess business impact<br/>(goal, revenue, users)"]
        SuggestActions["Generate suggested<br/>actions from runbook +<br/>deployment history"]
        BuildPayload["Build EnrichedAlert<br/>payload"]
    end

    subgraph "Persist &amp; Notify"
        StoreAlert["INSERT EnrichedAlert<br/>into PostgreSQL"]
        NotifyDash["Push to Dashboard<br/>(Grafana annotation)"]
        NotifySlack["Send to Slack /<br/>PagerDuty"]
        NotifyLog["Structured log<br/>output"]
    end

    Reject["Return 400 /<br/>log warning"]
    Fallback["Create alert with<br/>minimal context<br/>(unknown SLO)"]

    Start --> Receive
    Receive --> Validate
    Validate -->|No| Reject
    Validate -->|Yes| LogRaw
    LogRaw --> ParseLabels

    ParseLabels --> LookupSLO
    LookupSLO --> SLOFound
    SLOFound -->|No| Fallback
    SLOFound -->|Yes| LookupGoal
    LookupGoal --> LookupService
    LookupService --> LookupResponse
    LookupResponse --> LookupDeploys

    LookupDeploys --> CalcBudget
    CalcBudget --> AssessImpact
    AssessImpact --> SuggestActions
    SuggestActions --> BuildPayload
    Fallback --> BuildPayload

    BuildPayload --> StoreAlert
    StoreAlert --> NotifyDash
    StoreAlert --> NotifySlack
    StoreAlert --> NotifyLog
```

## Legend

| Symbol | Meaning |
|--------|---------|
| Double circle | External trigger (entry point) |
| Rectangle | Processing step |
| Diamond | Decision / branch |
| Subgraph | Pipeline stage |
| Solid arrow | Control flow |
