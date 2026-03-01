# Deployment Topology — Meridian Marketplace

Kubernetes deployment layout showing namespaces, workloads, services, and ConfigMaps
for the Meridian Marketplace platform running on a Kind cluster.

```mermaid
graph TD
    subgraph "Kind Cluster: podman-poc-cluster"

        subgraph "namespace: default"
            NextDeploy["Deployment:<br/>nextjs-frontend"]
            NextSvc["Service:<br/>nextjs-svc<br/>(ClusterIP :3000)"]
            NextDeploy --- NextSvc
        end

        subgraph "namespace: backend"
            DjangoDeploy["Deployment:<br/>django-api"]
            DjangoSvc["Service:<br/>django-svc<br/>(ClusterIP :8000)"]
            DjangoDeploy --- DjangoSvc

            FastAPIDeploy["Deployment:<br/>fastapi-webhook"]
            FastAPISvc["Service:<br/>fastapi-svc<br/>(ClusterIP :8080)"]
            FastAPIDeploy --- FastAPISvc

            PGStateful["StatefulSet:<br/>postgresql"]
            PGSvc["Service:<br/>postgres-svc<br/>(ClusterIP :5432)"]
            PGStateful --- PGSvc

            DBSecret["Secret:<br/>postgres-credentials"]
        end

        subgraph "namespace: monitoring"
            PromDeploy["StatefulSet:<br/>prometheus"]
            PromSvc["Service:<br/>prometheus-svc<br/>(ClusterIP :9090)"]
            PromDeploy --- PromSvc

            AMDeploy["Deployment:<br/>alertmanager"]
            AMSvc["Service:<br/>alertmanager-svc<br/>(ClusterIP :9093)"]
            AMDeploy --- AMSvc

            GrafanaDeploy["Deployment:<br/>grafana"]
            GrafanaSvc["Service:<br/>grafana-svc<br/>(ClusterIP :3000)"]
            GrafanaDeploy --- GrafanaSvc

            PromRules["ConfigMap:<br/>prometheus-rules<br/>(generated from OpenSLO)"]
            AMConfig["ConfigMap:<br/>alertmanager-config<br/>(webhook routes)"]
            SLODefs["ConfigMap:<br/>openslo-definitions"]
        end

        subgraph "namespace: enrichment"
            AgentDeploy["Deployment:<br/>ai-agent"]
            AgentSvc["Service:<br/>agent-svc<br/>(ClusterIP :8090)"]
            AgentDeploy --- AgentSvc

            AgentCM["ConfigMap:<br/>agent-config<br/>(LLM keys, DB conn)"]
            SLOMount["ConfigMap:<br/>openslo-definitions<br/>(mounted volume)"]
        end
    end

    PromRules -.->|loaded by| PromDeploy
    AMConfig -.->|configures| AMDeploy
    SLODefs -.->|mounted into| AgentDeploy
    AMSvc -->|webhook POST| FastAPISvc
    FastAPISvc -->|forward| AgentSvc
    AgentSvc -->|query| PGSvc
    PromSvc -->|scrape| DjangoSvc
    PromSvc -->|scrape| FastAPISvc
    NextSvc -->|proxy| DjangoSvc
```

## Legend

| Symbol | Meaning |
|--------|---------|
| Solid line (`---`) | Resource association within a namespace |
| Solid arrow (`-->`) | Network traffic between services |
| Dashed arrow (`-.->`) | Configuration mount / injection |
| Subgraph | Kubernetes namespace |
| Rounded box | Kubernetes workload or resource |
