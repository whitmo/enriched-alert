# SLO Breach Alert Flow

Full lifecycle of an SLO breach — from bad traffic through detection, alerting, and AI-driven enrichment.

## Sequence Diagram

```mermaid
sequenceDiagram
    title SLO Breach Alert Lifecycle

    participant Ex as Exerciser
    participant Svc as Example Service<br/>(FastAPI :8080)
    participant Prom as Prometheus<br/>(monitoring ns)
    participant AM as Alertmanager<br/>(monitoring ns)
    participant Agent as AI Agent<br/>(default ns, :8080)
    participant CM as ConfigMap<br/>(openslo-definitions)

    Note over Ex,Svc: Phase 1 — Bad Traffic Generation

    Ex->>Svc: GET /latency?delay_ms=2000
    Svc-->>Ex: 200 OK (after 2s delay)
    Ex->>Svc: GET /error?code=500
    Svc-->>Ex: 500 Internal Server Error
    Note right of Svc: Middleware records metrics:<br/>http_request_duration_seconds (histogram)<br/>http_requests_total (counter)

    Note over Svc,Prom: Phase 2 — Metrics Scraping

    loop Every 15s (ServiceMonitor)
        Prom->>Svc: GET /metrics
        Svc-->>Prom: Prometheus text exposition format
    end

    Note over Prom: Phase 3 — Recording Rule Evaluation

    Note right of Prom: slo:example_service_latency:ratio_rate5m<br/>= rate(duration_bucket{le="0.5"}[5m])<br/>  / rate(duration_count[5m])<br/><br/>Ratio drops below 0.99 target

    Note over Prom: Phase 4 — Alert Rule Evaluation

    Note right of Prom: SLOLatencyBreach fires when:<br/>  ratio_rate5m < 0.99<br/>  for: 2m<br/><br/>Labels attached:<br/>  severity: warning<br/>  alerttype: slo<br/>  slo_name: example-service-latency

    Prom->>Prom: Condition true for 2m → FIRING

    Note over Prom,AM: Phase 5 — Alert Routing

    Prom->>AM: POST alert (status=firing)
    Note right of AM: Route matching:<br/>  matchers: alerttype = slo<br/>  receiver: ai-agent

    AM->>AM: Group alerts by alerttype

    Note over AM,Agent: Phase 6 — Webhook Delivery

    AM->>Agent: POST /alert<br/>{status, commonLabels: {slo_name: ...}, alerts: [...]}

    Note over Agent,CM: Phase 7 — SLO Enrichment

    Agent->>Agent: Extract slo_name from<br/>commonLabels.slo_name
    Agent->>Agent: Validate slo_name<br/>(reject / and .. for path safety)
    Agent->>CM: Read /openslo/example-service-latency.yaml
    CM-->>Agent: OpenSLO YAML definition<br/>(target: 99%, window: 5m, ratio metrics)
    Agent->>Agent: yaml.safe_load() + merge<br/>alert context with SLO definition
    Agent->>Agent: Log enriched context:<br/>alert + full SLO spec

    Agent-->>AM: 200 OK {enriched: true,<br/>slo_name: "example-service-latency",<br/>slo_definition: {...}}
```

## Notes

- **Timing**: The full cycle from first bad request to enriched log takes roughly **5–7 minutes** in practice — dominated by the 5-minute rate window filling plus the 2-minute `for:` duration on the alert rule.
- **Two alert types**: The same flow applies to both `SLOLatencyBreach` (latency > 500ms) and `SLOErrorRateBreach` (error rate > 1%). Each carries its own `slo_name` label pointing to a different OpenSLO YAML file.
- **ConfigMap mount**: The `openslo-definitions` ConfigMap is created from the `openslo/` directory and mounted at `/openslo` in the AI Agent pod. The agent resolves `{OPENSLO_DIR}/{slo_name}.yaml`.
- **Security**: The agent rejects `slo_name` values containing `/` or `..` to prevent path traversal, and uses `yaml.safe_load()` instead of `yaml.load()`.
- **Alertmanager grouping**: Alerts with `alerttype=slo` are routed to the `ai-agent` receiver. All other alerts fall through to the `default` receiver.
- **send_resolved**: Alertmanager is configured with `send_resolved: true`, so the agent also receives a notification when the SLO recovers.
- **Namespace boundaries**: Prometheus and Alertmanager run in the `monitoring` namespace; Example Service and AI Agent run in `default`. The webhook URL crosses namespaces via `ai-agent.default.svc.cluster.local`.
