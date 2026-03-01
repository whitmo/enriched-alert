# System Architecture — Meridian Marketplace

Full-stack overview of the Meridian Marketplace platform showing user-facing services,
backend APIs, data stores, monitoring infrastructure, and the AI enrichment agent.

```mermaid
graph TD
    subgraph "Client Tier"
        Browser["Browser"]
    end

    subgraph "Frontend"
        NextJS["Next.js<br/>(SSR + React)"]
    end

    subgraph "API Gateway"
        GraphQL["GraphQL API<br/>(Strawberry / Python)"]
    end

    subgraph "Django Backend"
        Catalog["Catalog Service<br/>(Django app)"]
        Orders["Orders Service<br/>(Django app)"]
        Sellers["Sellers Service<br/>(Django app)"]
    end

    subgraph "Webhook &amp; Metrics"
        FastAPI["FastAPI<br/>Webhook Receiver +<br/>/metrics endpoint"]
    end

    subgraph "Data Store"
        Postgres[("PostgreSQL")]
    end

    subgraph "Monitoring Stack"
        Prom["Prometheus"]
        AM["Alertmanager"]
        OpenSLO["OpenSLO<br/>(rule generation)"]
    end

    subgraph "AI Enrichment"
        Agent["AI Agent<br/>(enriches alerts with<br/>business context)"]
    end

    subgraph "Notification Targets"
        Dashboard["Dashboard /<br/>Grafana"]
        Slack["Slack / PagerDuty"]
    end

    Browser -->|HTTPS| NextJS
    NextJS -->|GraphQL queries| GraphQL
    GraphQL --> Catalog
    GraphQL --> Orders
    GraphQL --> Sellers
    Catalog --> Postgres
    Orders --> Postgres
    Sellers --> Postgres

    Prom -->|scrape /metrics| FastAPI
    Prom -->|scrape /metrics| Catalog
    Prom -->|scrape /metrics| Orders
    Prom -->|scrape /metrics| Sellers
    OpenSLO -->|recording &amp; alerting rules| Prom
    Prom -->|fire alerts| AM
    AM -->|webhook POST| FastAPI
    FastAPI -->|forward alert| Agent
    Agent -->|query context| Postgres
    Agent -->|enriched alert| Dashboard
    Agent -->|enriched alert| Slack
```

## Legend

| Symbol | Meaning |
|--------|---------|
| Rounded box | Application service |
| Cylinder | Database |
| Solid arrow | Data / request flow |
| Subgraph | Deployment boundary or logical grouping |
| `/metrics` | Prometheus-compatible scrape endpoint |
