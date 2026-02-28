# Deployment Topology

Kubernetes deployment topology for the AI-driven SLO response PoC running on a local Kind cluster (`podman-poc-cluster`) with Podman as the container runtime. The cluster is split into two namespaces: `monitoring` for the observability stack and `default` for application workloads. NodePort services expose Prometheus and Alertmanager to the host machine for local development access.

```mermaid
flowchart TB
    title["<b>Deployment Topology — Kind Cluster</b>"]
    style title fill:none,stroke:none,color:#333

    subgraph host["Host Machine (localhost)"]
        direction TB
        port_prom["localhost:30090"]
        port_am["localhost:30093"]
    end

    subgraph kind["Kind Cluster: podman-poc-cluster"]
        direction TB

        subgraph monitoring["Namespace: monitoring"]
            direction TB

            prom_deploy["Prometheus<br/><i>Deployment</i>"]
            prom_svc["prometheus-svc<br/><i>Service: NodePort 30090</i>"]
            prom_deploy --- prom_svc

            am_deploy["Alertmanager<br/><i>Deployment</i>"]
            am_svc["alertmanager-svc<br/><i>Service: NodePort 30093</i>"]
            am_deploy --- am_svc

            sm["ServiceMonitor<br/><i>monitors default ns</i>"]
        end

        subgraph default["Namespace: default"]
            direction TB

            agent_deploy["AI Agent<br/><i>Deployment</i>"]
            agent_svc["ai-agent-svc<br/><i>Service: ClusterIP</i>"]
            agent_deploy --- agent_svc

            svc_deploy["Example Service<br/><i>Deployment</i>"]
            svc_svc["example-service-svc<br/><i>Service: ClusterIP</i>"]
            svc_deploy --- svc_svc

            openslo_cm["openslo-definitions<br/><i>ConfigMap</i>"]
        end
    end

    %% Host port mappings
    port_prom -.->|"NodePort"| prom_svc
    port_am -.->|"NodePort"| am_svc

    %% ServiceMonitor scrapes default namespace services
    sm -->|"scrapes metrics"| svc_svc
    sm -->|"scrapes metrics"| agent_svc

    %% Prometheus pulls from ServiceMonitor targets
    prom_deploy -->|"evaluates rules"| prom_deploy

    %% Alert flow
    prom_deploy -->|"fires alerts"| am_deploy
    am_deploy -->|"webhook POST /alert"| agent_svc

    %% ConfigMap mount
    openslo_cm -.->|"mounted into"| agent_deploy

    %% Styles
    style host fill:#e8f4f8,stroke:#2196F3,stroke-width:2px
    style kind fill:#f5f5f5,stroke:#333,stroke-width:2px
    style monitoring fill:#fff3e0,stroke:#FF9800,stroke-width:2px
    style default fill:#e8f5e9,stroke:#4CAF50,stroke-width:2px

    style prom_deploy fill:#FF9800,color:#fff,stroke:#E65100
    style prom_svc fill:#FFE0B2,stroke:#FF9800
    style am_deploy fill:#FF5722,color:#fff,stroke:#BF360C
    style am_svc fill:#FFCCBC,stroke:#FF5722
    style sm fill:#FFF9C4,stroke:#F9A825

    style agent_deploy fill:#2196F3,color:#fff,stroke:#0D47A1
    style agent_svc fill:#BBDEFB,stroke:#2196F3
    style svc_deploy fill:#4CAF50,color:#fff,stroke:#1B5E20
    style svc_svc fill:#C8E6C9,stroke:#4CAF50
    style openslo_cm fill:#E1BEE7,stroke:#7B1FA2

    style port_prom fill:#B3E5FC,stroke:#0288D1
    style port_am fill:#FFCDD2,stroke:#C62828
```

## Legend

| Symbol | Meaning |
|--------|---------|
| Solid line (`---`) | Resource association (Deployment owns its Service) |
| Solid arrow (`-->`) | Data/control flow (scraping, alerting, webhooks) |
| Dashed arrow (`-.->`) | Configuration or network mapping (NodePort exposure, ConfigMap mount) |
| Orange subgraph | `monitoring` namespace — observability stack |
| Green subgraph | `default` namespace — application workloads |
| Blue outer box | Host machine with port mappings |

### Key Relationships

- **ServiceMonitor** lives in `monitoring` but reaches across namespaces to scrape metrics from services in `default`
- **Prometheus** evaluates recording/alerting rules generated from OpenSLO definitions and fires alerts to **Alertmanager**
- **Alertmanager** routes SLO breach alerts via webhook to the **AI Agent** service
- **openslo-definitions ConfigMap** is mounted into the AI Agent pod so it can look up SLO context when processing alerts
- **NodePort** services expose Prometheus (30090) and Alertmanager (30093) to `localhost` for development access
