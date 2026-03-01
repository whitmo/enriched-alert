# Security Assessment: Meridian Marketplace

## Executive Summary

The Meridian Marketplace architecture presents a **moderate overall risk posture** typical of an internal observability platform with multiple service boundaries. The most significant risks are: unauthenticated webhook endpoints accepting external alert data (HIGH), exposed monitoring endpoints without access controls (HIGH), and insufficient inter-service authentication within the Kubernetes cluster (MEDIUM). For a PoC, several of these are acceptable if the cluster is not internet-facing, but **three findings require immediate attention before any production deployment**: webhook authentication, secrets management, and network segmentation.

This assessment covers the full planned architecture: Next.js frontend → GraphQL API (Strawberry on Django) → Django (business models) + FastAPI (webhook receiver, metrics) → PostgreSQL, with Prometheus + Alertmanager monitoring, AI agent enrichment, browser notifications, and flat-file business goals/operational responses, deployed on Kubernetes.

---

## OWASP Top 10 (2021) Assessment

### A01: Broken Access Control

**Risk Level: HIGH**

| Attack Surface | Finding | Severity |
|---|---|---|
| FastAPI `/alert` endpoint | **No authentication.** Alertmanager's built-in webhook_configs do not support auth headers natively. Anyone with network access to the ai-agent Service can POST arbitrary alert payloads. | HIGH |
| GraphQL API | Architecture doc says "no auth/login, single-user dashboard." GraphQL queries expose business goals, SLO status, enriched alerts, team contacts, and escalation chains — all without authentication. | HIGH (prod) / LOW (PoC) |
| Prometheus `/metrics` | Exposed via NodePort 30090. No authentication. Leaks internal service names, request rates, error rates, and latency distributions. | HIGH |
| Alertmanager UI | Exposed via NodePort 30093. No authentication. An attacker can silence alerts, modify routing, or view all firing alerts. | HIGH |
| Django Admin | If enabled (likely for seed data management), default `/admin/` path with password auth. Brute-forceable if exposed. | MEDIUM |
| Next.js dashboard | No auth planned for PoC. Read-only data, but exposes business-sensitive SLO/revenue impact information. | MEDIUM (prod) / LOW (PoC) |
| GraphQL introspection | If left enabled in production, reveals full schema including all types, queries, mutations. | MEDIUM |

**Mitigations:**
- **PoC (minimum):** Ensure Kind cluster NodePorts are only bound to localhost (already the case with Kind's default config). Don't expose the cluster externally.
- **Production:** Add authentication to the webhook endpoint (mutual TLS, shared secret via `Authorization` header with Alertmanager's `http_config`, or network policy restricting source to Alertmanager pods only). Add auth middleware to GraphQL (JWT or session-based). Put Prometheus/Alertmanager behind an authenticating reverse proxy (oauth2-proxy). Disable GraphQL introspection.

### A02: Cryptographic Failures

**Risk Level: MEDIUM**

| Component | Finding | Severity |
|---|---|---|
| PostgreSQL connection | No TLS configuration visible in current architecture. Django's `DATABASES` config likely uses plaintext connection within the cluster. | MEDIUM |
| Inter-service communication | No mTLS between services. All HTTP traffic within the K8s cluster is plaintext. Webhook payloads (containing alert data, SLO names) traverse the network unencrypted. | MEDIUM |
| Secrets in K8s manifests | No secrets management strategy visible. DB credentials, any future API keys will need secure storage. Current ConfigMap usage for OpenSLO YAML is fine (not secret), but DB credentials in ConfigMaps would be a vulnerability. | MEDIUM |
| NodePort exposure | Prometheus (30090) and Alertmanager (30093) exposed on host ports without TLS. | LOW (Kind) / HIGH (prod) |

**Mitigations:**
- **PoC:** Acceptable within Kind cluster (single-node, loopback only). Document that this is not production-ready.
- **Production:** Enable TLS on PostgreSQL connections (`sslmode=require` in Django settings). Deploy a service mesh (Istio/Linkerd) for mTLS between all services, or use cert-manager for per-service TLS. Use Kubernetes Secrets (not ConfigMaps) for credentials, or better: external-secrets-operator with a vault backend.

### A03: Injection

**Risk Level: LOW–MEDIUM**

| Vector | Finding | Severity |
|---|---|---|
| Path traversal via `slo_name` | **Already mitigated** in PR c828b31. The ai-agent rejects `slo_name` values containing `/` or `..` and verifies resolved paths stay within `OPENSLO_DIR`. Good defense-in-depth with both input validation and path canonicalization. | RESOLVED |
| YAML parsing | **Already mitigated.** Uses `yaml.safe_load()` (not `yaml.load()`) with try/except for malformed YAML. Safe against YAML deserialization attacks. | RESOLVED |
| GraphQL injection | Strawberry uses typed resolvers, which makes traditional injection unlikely. However, **query depth and complexity are not limited** — a malicious query could request deeply nested relationships (`businessGoal → slos → alerts → slo → alerts → ...`) causing excessive DB load. | MEDIUM |
| Django ORM | Uses parameterized queries by default. Low risk if using ORM properly and not constructing raw SQL. | LOW |
| Log injection | `slo_name` is logged directly: `logger.info("Loaded SLO definition for '%s'", slo_name)`. While the path traversal characters are blocked, other control characters in `slo_name` could inject into log output (newline injection for log forging). | LOW |

**Mitigations:**
- Add GraphQL query depth limiting and complexity analysis to Strawberry (e.g., `strawberry.extensions.QueryDepthLimiter`).
- Sanitize `slo_name` for log injection (strip control characters, or use structured/JSON logging).
- Continue using Django ORM for all database access; audit any future raw SQL.

### A04: Insecure Design

**Risk Level: MEDIUM**

| Design Issue | Finding | Severity |
|---|---|---|
| Trust boundary: enrichment pipeline | The AI agent trusts DB content and flat files implicitly. If an attacker can modify OpenSLO YAML files (via ConfigMap access or K8s API), the enrichment pipeline will serve attacker-controlled content through to the dashboard and browser notifications. | MEDIUM |
| GraphQL subscriptions DoS | WebSocket-based subscriptions (Django Channels + Redis) allow many open connections. No connection limits are defined. An attacker could open thousands of subscription connections, exhausting server resources. | MEDIUM |
| Browser notifications | The Notification API is origin-bound, so spoofing requires XSS on the dashboard origin. However, if an attacker can inject fake alerts via the unauthenticated webhook, they can generate arbitrary browser notifications with false business impact data ("$50k/hr revenue loss" for a non-event). | MEDIUM |
| Single point of failure | The ai-agent is a single-replica deployment. If it goes down, all alert enrichment stops silently. There's no health monitoring of the monitoring system itself. | MEDIUM |
| Alert flood/storm | No rate limiting on the `/alert` endpoint. An attacker (or misconfigured Alertmanager) could flood the webhook, filling PostgreSQL with junk EnrichedAlert records and overwhelming the subscription pipeline. | MEDIUM |

**Mitigations:**
- Add rate limiting to the `/alert` endpoint (e.g., slowapi or a simple token bucket).
- Limit WebSocket connections per client IP.
- Add integrity checks or RBAC on ConfigMaps containing OpenSLO definitions.
- Deploy ai-agent with `replicas: 2` and a PodDisruptionBudget.
- Add a "canary" alert that the system sends to itself to verify the pipeline is working end-to-end.

### A05: Security Misconfiguration

**Risk Level: HIGH**

| Misconfiguration | Finding | Severity |
|---|---|---|
| Django `DEBUG` | Not yet configured (architecture phase), but high risk if set to `True` in production. Debug mode exposes stack traces, SQL queries, and settings. | HIGH (potential) |
| GraphQL introspection | Strawberry enables introspection by default. Must be explicitly disabled for production. | MEDIUM |
| Prometheus `/metrics` exposed | The example-service exposes `/metrics` without auth. In Kubernetes, this is typically acceptable (internal), but if services are exposed externally, metrics become an information leak. | MEDIUM |
| Kubernetes RBAC | No service account configuration in deployment manifests. Pods use the `default` service account, which may have excessive permissions depending on the cluster's RBAC config. | MEDIUM |
| Container runs as root | Neither Dockerfile specifies a non-root user. Both `python:3.12-slim` containers run as root by default. | MEDIUM |
| No `securityContext` on pods | No `readOnlyRootFilesystem`, no `runAsNonRoot`, no `allowPrivilegeEscalation: false` in deployment manifests. | MEDIUM |
| Kind NodePort exposure | Ports 30080, 30090, 30093 mapped to host. On a shared machine, other users could access monitoring stack. | LOW (dev) |

**Mitigations:**
- Add `USER nonroot` to Dockerfiles (or use distroless base images).
- Add `securityContext` to all pod specs: `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`.
- Create dedicated service accounts with minimal RBAC for each workload.
- Set Django `DEBUG=False` and `ALLOWED_HOSTS` in production.
- Disable GraphQL introspection in production: `strawberry.Schema(query=Query, extensions=[DisableIntrospection()])`.

### A06: Vulnerable and Outdated Components

**Risk Level: MEDIUM**

| Component | Finding | Severity |
|---|---|---|
| `python:3.12-slim` base image | May contain known CVEs in system libraries. Debian-based slim images have a broader attack surface than distroless or Alpine alternatives. | MEDIUM |
| Unpinned dependencies | `requirements.txt` files do not pin versions: `fastapi`, `uvicorn[standard]`, `pyyaml`, `prometheus_client`. Builds are not reproducible and may pull in vulnerable versions. | MEDIUM |
| uv installer from `ghcr.io` | `COPY --from=ghcr.io/astral-sh/uv:latest` in Dockerfile — `latest` tag is mutable. A supply chain attack on the uv image would compromise all builds. | MEDIUM |
| Helm chart versions | `helm upgrade --install prometheus prometheus-community/kube-prometheus-stack` with no `--version` flag. Pulls latest chart version, which may introduce breaking changes or vulnerabilities. | LOW |
| No dependency scanning | No `pip-audit`, `npm audit`, or Trivy scanning in the workflow. | MEDIUM |

**Mitigations:**
- Pin all Python dependencies to specific versions with hashes (`pip-compile --generate-hashes`).
- Pin the uv image to a specific digest: `COPY --from=ghcr.io/astral-sh/uv:0.x.y@sha256:...`.
- Pin the Helm chart version: `--version 65.x.y`.
- Add `pip-audit` to CI. Add Trivy container scanning.
- Consider switching to `python:3.12-slim-bookworm` (specific Debian release) or `gcr.io/distroless/python3`.

### A07: Identification and Authentication Failures

**Risk Level: HIGH**

| Component | Finding | Severity |
|---|---|---|
| Webhook endpoint | **No authentication by design.** Alertmanager's `webhook_configs` supports `http_config` with `basic_auth`, `bearer_token`, or `tls_config`. The current config uses none of these. | HIGH |
| GraphQL API | No auth planned for PoC. For production, needs JWT, session, or API key authentication. | HIGH (prod) |
| Next.js dashboard | No authentication. Anyone with network access sees business-sensitive data. | HIGH (prod) / LOW (PoC) |
| Django admin | Password-based auth. No MFA. No account lockout policy by default. | MEDIUM |
| K8s service accounts | Default service account tokens auto-mounted to pods. Not needed for these workloads. | LOW |

**Mitigations:**
- **Minimum viable auth for webhook:** Use Alertmanager's `http_config.bearer_token` with a shared secret stored in a K8s Secret, and validate it in FastAPI middleware.
- Add JWT-based auth to the GraphQL API (django-graphql-jwt or custom middleware).
- Add NextAuth.js or similar for dashboard authentication.
- Set `automountServiceAccountToken: false` on pods that don't need K8s API access.

### A08: Software and Data Integrity Failures

**Risk Level: MEDIUM**

| Component | Finding | Severity |
|---|---|---|
| Container images | No image signing (cosign/Notary). Images built locally and loaded to Kind via `kind load docker-image`. No provenance verification. | MEDIUM (prod) |
| Helm charts | Charts pulled from public repos without integrity verification. | LOW |
| CI/CD pipeline | Not yet implemented. When added: GitHub Actions secrets, OIDC for cloud providers, and artifact signing should be considered. | MEDIUM (future) |
| OpenSLO ConfigMap | ConfigMap contents are not integrity-checked. A compromised K8s credential could modify SLO definitions, changing what the agent reports. | MEDIUM |
| Dependency supply chain | No `requirements.txt` hash pinning. Vulnerable to dependency confusion or typosquatting. | MEDIUM |

**Mitigations:**
- Pin dependencies with hashes.
- Sign container images with cosign in CI/CD.
- Use OIDC for GitHub Actions (avoid long-lived secrets).
- Consider read-only ConfigMaps with RBAC restricting who can modify them.

### A09: Security Logging and Monitoring Failures

**Risk Level: MEDIUM**

| Component | Finding | Severity |
|---|---|---|
| Self-monitoring | **Ironic:** This IS a monitoring system, but there's no monitoring of the monitoring system itself. If the ai-agent crashes, alerts stop being enriched — and nobody would know. | MEDIUM |
| Audit logging | No audit logging for GraphQL queries/mutations. In the planned architecture with mutations, this matters — who acknowledged an alert? Who changed an SLO status? | MEDIUM |
| Security event alerting | No alerting on security-relevant events: failed auth attempts (future), unusual webhook payload patterns, excessive error rates on the agent itself. | MEDIUM |
| Log aggregation | No centralized logging. Logs are per-pod stdout/stderr only. In a multi-service architecture, correlating events across services requires aggregation. | LOW (PoC) |
| Alert payload logging | The ai-agent logs full `payload` on every alert: `logger.info("Received alert payload: %s", payload)`. Good for debugging but may log sensitive data at scale. | LOW |

**Mitigations:**
- Add a "watchdog" alert: a synthetic alert that fires periodically to verify the enrichment pipeline is alive. If the pipeline doesn't process it within N minutes, alert via a separate channel.
- Add structured logging (JSON) for easier aggregation and querying.
- Add audit fields to EnrichedAlert model: `acknowledged_by`, `acknowledged_at`.
- Consider log level configuration: DEBUG in dev, WARNING in prod.

### A10: Server-Side Request Forgery (SSRF)

**Risk Level: LOW**

| Vector | Finding | Severity |
|---|---|---|
| AI agent | Current implementation only reads local flat files (OpenSLO YAML from mounted ConfigMap) and logs output. No outbound HTTP requests. | LOW |
| GraphQL resolvers | Planned resolvers read from PostgreSQL via Django ORM. No URL-fetching resolvers in the schema. | LOW |
| Future risk: AI enrichment | If the agent evolves to call external LLM APIs or fetch runbook URLs, SSRF becomes a concern. Any URL in alert labels or annotations that gets fetched would be an SSRF vector. | MEDIUM (future) |

**Mitigations:**
- Maintain the current design of local-only data access for the agent.
- If external API calls are added later, use an allowlist of permitted hosts and do not construct URLs from alert payload data.
- Apply egress network policies to restrict what pods can reach.

---

## MITRE ATT&CK Assessment

### Initial Access

| Technique | Relevance | Notes |
|---|---|---|
| **T1190: Exploit Public-Facing Application** | HIGH | Three attack surfaces: unauthenticated webhook (`/alert`), GraphQL API, Next.js dashboard. The webhook is the most concerning — it accepts arbitrary JSON and processes it. If exposed beyond the cluster, an attacker can inject fake alerts into the pipeline. |
| **T1078: Valid Accounts** | MEDIUM | Django admin credentials, future dashboard auth credentials. If K8s service account tokens are leaked (via SSRF, log exposure, or container escape), attacker gains cluster access. |
| **T1133: External Remote Services** | LOW | Kind NodePorts (30080, 30090, 30093) bound to host. Not externally routable by default but could be if firewall rules change. |

### Execution

| Technique | Relevance | Notes |
|---|---|---|
| **T1059: Command and Scripting Interpreter** | MEDIUM (future) | Current agent only logs. Architecture doc mentions future "automated remediation" (scaling, restarts). If the agent ever executes shell commands or K8s API calls based on alert content, this becomes HIGH. The exerciser script (`exerciser.py`) can already induce arbitrary latency and error conditions via HTTP parameters. |
| **T1203: Exploitation for Client Execution** | MEDIUM | XSS via Next.js dashboard. If enriched alert content (e.g., `summary`, `business_impact`) contains unsanitized HTML and is rendered in React without proper escaping, XSS is possible. React escapes by default, but `dangerouslySetInnerHTML` would break this. |
| **T1609: Container Administration Command** | LOW | If K8s API access is gained via service account token, attacker could exec into containers. Mitigated by RBAC and disabling service account auto-mount. |

### Persistence

| Technique | Relevance | Notes |
|---|---|---|
| **T1053: Scheduled Task/Job** | LOW | No CronJobs in current architecture. The exerciser could be deployed as a Job, but it's manual. If attacker gains K8s access, they could create CronJobs. |
| **T1098: Account Manipulation** | MEDIUM | Django admin allows creating superusers. If admin credentials are compromised, attacker can create additional admin accounts and persist access. |
| **T1505: Server Software Component** | LOW | An attacker with write access to the ConfigMap could inject a malicious OpenSLO YAML that causes the agent to behave differently — a form of configuration-based persistence. |

### Privilege Escalation

| Technique | Relevance | Notes |
|---|---|---|
| **T1078.001: Valid Accounts - Default Accounts** | MEDIUM | Default K8s service account in each namespace. Pods don't specify custom service accounts. |
| **T1611: Escape to Host** | LOW–MEDIUM | Containers run as root with no securityContext restrictions. Container escape is possible via kernel exploits if the container runtime has vulnerabilities. Kind uses containerd. |
| **T1068: Exploitation for Privilege Escalation** | LOW | python:3.12-slim may contain SUID binaries or writable system directories exploitable for local privilege escalation within the container. |

### Defense Evasion

| Technique | Relevance | Notes |
|---|---|---|
| **T1070: Indicator Removal** | MEDIUM | **Particularly relevant:** This IS the logging/alerting system. An attacker who compromises the ai-agent could suppress or modify alerts before they reach the dashboard. They could also delete EnrichedAlert records from PostgreSQL, erasing evidence. Alertmanager's silence API (unauthenticated) allows suppressing specific alerts. |
| **T1070.003: Clear Command History** | LOW | Container restart clears in-memory state. No persistent shell history. |
| **T1562: Impair Defenses** | HIGH | An attacker could: (1) POST to Alertmanager's API to silence all alerts, (2) modify Prometheus rules via K8s API to disable alerting, (3) crash the ai-agent to stop enrichment. All without authentication in current design. |

### Lateral Movement

| Technique | Relevance | Notes |
|---|---|---|
| **T1210: Exploitation of Remote Services** | MEDIUM | Once inside the cluster (e.g., via compromised webhook handler), attacker can reach all ClusterIP services: PostgreSQL, Prometheus, Alertmanager, example-service. No network policies restrict pod-to-pod traffic. |
| **T1552: Unsecured Credentials** | MEDIUM | Database credentials will need to be stored somewhere. If in environment variables or ConfigMaps (not Secrets), they're visible to anyone with pod access. K8s Secrets are base64-encoded, not encrypted at rest by default. |

### Collection

| Technique | Relevance | Notes |
|---|---|---|
| **T1005: Data from Local System** | MEDIUM | PostgreSQL contains: business goals, SLO definitions, team contact information (names, emails, Slack handles), enriched alert history with revenue impact estimates, and operational response procedures. This is business-sensitive competitive intelligence. |
| **T1530: Data from Cloud Storage** | LOW | No cloud storage in current architecture. ConfigMaps are the "storage" for OpenSLO definitions. |

### Impact

| Technique | Relevance | Notes |
|---|---|---|
| **T1485: Data Destruction** | MEDIUM | Deleting enriched alert history from PostgreSQL destroys the operational record. Deleting OpenSLO definitions from ConfigMaps breaks the enrichment pipeline. |
| **T1489: Service Stop** | HIGH | **Critical risk:** DoS on Alertmanager or the webhook endpoint means alerts don't flow. For a system whose entire purpose is alert visibility, this is the highest-impact attack. An attacker could: crash the ai-agent, flood it with junk alerts, silence Alertmanager, or delete Prometheus rules. The business loses its early warning system. |
| **T1491: Defacement** | MEDIUM | Injecting false alerts with fabricated business impact data ("$1M/hr loss") into the dashboard could cause panic, unnecessary escalations, and erode trust in the monitoring system. |
| **T1498: Network Denial of Service** | LOW | Within Kind/K8s, bandwidth is shared. A flood of GraphQL subscription connections or webhook POST requests could degrade all services on the cluster. |

---

## Threat Model Summary

| # | Threat | Likelihood | Impact | Risk | Mitigation Status |
|---|--------|-----------|--------|------|-------------------|
| 1 | Fake alert injection via unauthenticated webhook | HIGH | HIGH | **CRITICAL** | Not mitigated |
| 2 | Alert suppression via Alertmanager silence API | HIGH | HIGH | **CRITICAL** | Not mitigated |
| 3 | Information disclosure via exposed Prometheus/Alertmanager | MEDIUM | MEDIUM | **HIGH** | Partially mitigated (Kind localhost only) |
| 4 | GraphQL resource exhaustion (deep queries, subscription flood) | MEDIUM | MEDIUM | **HIGH** | Not mitigated |
| 5 | Container escape due to root user + no securityContext | LOW | HIGH | **HIGH** | Not mitigated |
| 6 | Business data exfiltration via unauthenticated GraphQL | MEDIUM | MEDIUM | **HIGH** | Not mitigated (by design for PoC) |
| 7 | Path traversal via slo_name in webhook payload | MEDIUM | HIGH | ~~HIGH~~ | **Mitigated** (PR c828b31) |
| 8 | YAML deserialization attack | LOW | HIGH | ~~MEDIUM~~ | **Mitigated** (yaml.safe_load) |
| 9 | Dependency supply chain compromise (unpinned versions) | LOW | HIGH | **MEDIUM** | Not mitigated |
| 10 | Django debug mode / misconfiguration in production | MEDIUM | MEDIUM | **MEDIUM** | Not yet relevant (architecture phase) |
| 11 | Lateral movement within cluster (no network policies) | LOW | HIGH | **MEDIUM** | Not mitigated |
| 12 | Credential exposure (DB password, API keys) | MEDIUM | HIGH | **MEDIUM** | No secrets exist yet |
| 13 | SSRF via future AI agent external calls | LOW | MEDIUM | **LOW** | Not yet relevant |

---

## Recommendations (Prioritized)

### 1. [CRITICAL] Authenticate the webhook endpoint

Alertmanager supports `http_config` with `bearer_token`, `basic_auth`, or `tls_config`. Add a shared bearer token:

```yaml
# Alertmanager config
receivers:
  - name: ai-agent
    webhook_configs:
      - url: http://ai-agent.default.svc.cluster.local/alert
        http_config:
          bearer_token: <from-k8s-secret>
```

Validate the token in FastAPI middleware. Store the secret in a K8s Secret, not a ConfigMap.

### 2. [CRITICAL] Restrict Alertmanager API access

Either deploy a network policy limiting access to Alertmanager pods, or put Alertmanager behind an authenticating proxy. The silence/inhibition APIs are as dangerous as the alert pipeline itself.

### 3. [HIGH] Add network policies for namespace isolation

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ai-agent-ingress
spec:
  podSelector:
    matchLabels:
      app: ai-agent
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: monitoring
          podSelector:
            matchLabels:
              app: alertmanager
      ports:
        - port: 8080
```

This ensures only Alertmanager pods can reach the webhook endpoint.

### 4. [HIGH] Harden container security

Add to all Deployments:

```yaml
securityContext:
  runAsNonRoot: true
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
```

Add `USER 65534` (nobody) to Dockerfiles. Use `python:3.12-slim-bookworm` pinned to a specific digest.

### 5. [HIGH] Add GraphQL query depth and complexity limits

Use Strawberry's built-in extensions or a custom validator to limit query depth (e.g., max 5 levels) and query complexity. Add WebSocket connection limits for subscriptions.

### 6. [MEDIUM] Pin all dependencies

Pin Python packages with version + hash. Pin the uv Docker image to a specific digest. Pin the Helm chart version. Add `pip-audit` and Trivy to CI.

### 7. [MEDIUM] Add rate limiting to webhook endpoint

Use `slowapi` or a custom token-bucket middleware to limit `/alert` to a reasonable rate (e.g., 100 requests/minute). This prevents both intentional DoS and accidental alert storms.

### 8. [MEDIUM] Implement secrets management

Use K8s Secrets (minimum) or external-secrets-operator (recommended) for database credentials and API tokens. Never store secrets in ConfigMaps, environment variable literals in manifests, or source code.

### 9. [MEDIUM] Self-monitoring ("watchdog" pattern)

Add a synthetic alert that fires every 5 minutes. If the ai-agent doesn't process it, alert via a completely separate channel (e.g., a simple cron + healthcheck on a different service). The monitoring system must monitor itself.

### 10. [LOW] Structured logging and audit trail

Switch to JSON-structured logging. Add audit fields to the EnrichedAlert model. Log security-relevant events (rejected payloads, auth failures) at a higher level.

---

## Security Architecture Recommendations

### For PoC (do now)

These are low-effort changes that significantly improve the security posture without slowing development:

- **Pin dependency versions** in `requirements.txt` — prevents reproducibility issues and accidental vulnerability introduction
- **Add `USER` directive to Dockerfiles** — one line, eliminates root-in-container risk
- **Add `securityContext` to pod specs** — copy-paste YAML, significant hardening
- **Set `automountServiceAccountToken: false`** on pods that don't need K8s API access
- **Document** that NodePorts are dev-only and must not be exposed externally

### For Production

- **Service mesh (Istio or Linkerd):** Provides mTLS between all services, eliminating the need to add TLS individually. Also provides observability, traffic management, and access policies.
- **Network policies:** Namespace isolation at minimum. Per-pod ingress/egress policies for defense in depth.
- **Secrets management:** external-secrets-operator pulling from HashiCorp Vault, AWS Secrets Manager, or similar. Avoid sealed-secrets for anything that needs rotation.
- **RBAC least privilege:** Dedicated service accounts per workload. No cluster-admin for any application pod. Audit RBAC bindings regularly.
- **Pod Security Standards:** Enforce `restricted` pod security standard at the namespace level via Pod Security Admission.
- **Container image signing:** cosign in CI/CD pipeline. Admission controller (Kyverno or OPA Gatekeeper) to reject unsigned images.
- **Ingress controller with TLS termination:** Replace NodePorts with an Ingress controller (nginx, Traefik, or cloud LB) with TLS certificates from cert-manager + Let's Encrypt.
- **Backup and disaster recovery:** Regular PostgreSQL backups. Configuration-as-code for all K8s resources (already in manifests, just needs GitOps enforcement).

---

## Appendix: PoC vs Production Risk Acceptance

| Risk | PoC Acceptable? | Production Acceptable? | Notes |
|------|-----------------|----------------------|-------|
| No webhook auth | Yes (localhost only) | **No** | Must add before any external exposure |
| No dashboard auth | Yes (single user) | **No** | Business-sensitive data requires auth |
| Root containers | Yes (dev speed) | **No** | One-line Dockerfile fix |
| No network policies | Yes (Kind cluster) | **No** | Must add before multi-tenant or external |
| Unpinned deps | Marginal | **No** | Low effort to fix now |
| No mTLS | Yes (single node) | **No** | Service mesh or cert-manager required |
| Exposed Prometheus | Yes (localhost) | **No** | Auth proxy or network policy required |
| No secrets management | Yes (no real secrets yet) | **No** | Must be in place before real credentials |
