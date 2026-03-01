# Data Model — Meridian Marketplace

Entity-relationship diagram for the core domain objects that connect business goals
to operational alerts through SLO definitions, services, and teams.

```mermaid
erDiagram
    BusinessGoal {
        uuid id PK
        string name
        string description
        string owner
        decimal target_value
        string metric_type
        timestamp created_at
    }

    SLODefinition {
        uuid id PK
        uuid business_goal_id FK
        uuid service_id FK
        string slo_name
        string sli_metric
        decimal target_threshold
        string window_duration
        decimal error_budget
        string openslo_yaml_ref
        timestamp created_at
    }

    OperationalResponse {
        uuid id PK
        uuid slo_definition_id FK
        string response_type
        string description
        string runbook_url
        string severity
        int priority
    }

    EnrichedAlert {
        uuid id PK
        uuid slo_definition_id FK
        string raw_alert_json
        string business_impact
        string suggested_actions
        decimal error_budget_remaining
        string enrichment_source
        timestamp received_at
        timestamp enriched_at
    }

    Service {
        uuid id PK
        uuid team_id FK
        string name
        string namespace
        string metrics_endpoint
        string repo_url
        string deploy_status
    }

    Team {
        uuid id PK
        string name
        string slack_channel
        string escalation_policy
        string on_call_schedule
    }

    BusinessGoal ||--o{ SLODefinition : "drives"
    SLODefinition ||--o{ OperationalResponse : "defines response"
    SLODefinition ||--o{ EnrichedAlert : "breach generates"
    Service ||--o{ SLODefinition : "measured by"
    Team ||--o{ Service : "owns"
```

## Legend

| Symbol | Meaning |
|--------|---------|
| `PK` | Primary key |
| `FK` | Foreign key |
| `\|\|--o{` | One-to-many relationship |
| Entity box | Database table / Django model |
