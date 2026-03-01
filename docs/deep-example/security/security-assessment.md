# Security Assessment: Meridian Marketplace

## Executive Summary

The Meridian Marketplace architecture presents a **moderate-to-high risk posture** driven primarily by a large attack surface (four distinct service boundaries: Next.js, GraphQL/Django, FastAPI webhook, PostgreSQL) and an unauthenticated webhook endpoint that serves as the primary data ingestion path. The AI enrichment agent introduces a novel trust boundary — it consumes alert data, flat-file content, and database state, then produces outputs displayed to users, creating injection and data integrity risks that traditional web app assessments miss. **Priority mitigations**: authenticate the webhook endpoint, enforce GraphQL query limits, lock down Prometheus/metrics endpoints, and implement network policies in Kubernetes to segment trust zones.

---

## OWASP Top 10 (2021) Assessment

### A01: Broken Access Control

**Risk Level: HIGH**

| Attack Surface | Concern |
|---|---|
| GraphQL API (Strawberry/Django) | What authorization model governs queries and mutations? Strawberry permissions must be explicitly applied per resolver — default is open. Can any authenticated user query all alerts, goals, and SLO data? Are there object-level checks (e.g., tenant isolation)? |
| Django Admin | If enabled, `/admin/` exposes full model CRUD. Default Django admin uses session auth — are credentials rotated? Is it exposed outside the cluster? |
| FastAPI `/alert` endpoint | **Alertmanager does not natively support auth headers on webhook requests.** This endpoint is unauthenticated by design. Anyone with network access to the service can inject fabricated alerts. |
| Next.js dashboard | How is dashboard access controlled? NextAuth, session cookies, JWT? Is there CSRF protection on mutations triggered from the frontend? |
| Prometheus `/metrics` | Prometheus and Alertmanager web UIs and `/metrics` endpoints are unauthenticated by default. Exposing these leaks internal service names, error rates, and infrastructure topology. |

**Mitigations:**
- Webhook endpoint: Validate a shared secret via `Authorization` header or HMAC signature. Alertmanager supports `http_config` with `authorization` on webhook receivers — use it. Alternatively, restrict access via Kubernetes NetworkPolicy to only allow traffic from the Alertmanager pod.
- GraphQL: Implement field-level and object-level permission checks in Strawberry resolvers. Disable introspection in production.
- Django Admin: Disable in production or restrict to `kubectl port-forward` access only.
- Prometheus/Alertmanager UIs: Do not expose via Ingress; access through port-forward or behind an authenticating proxy (OAuth2 Proxy).

---

### A02: Cryptographic Failures

**Risk Level: MEDIUM**

| Concern | Detail |
|---|---|
| PostgreSQL connection | Is TLS enforced (`sslmode=require` or `verify-full`)? In-cluster connections often skip TLS — this exposes credentials and query data to network sniffing within the cluster. |
| Inter-service communication | Are calls between Next.js → GraphQL → Django → FastAPI encrypted? In Kubernetes, pod-to-pod traffic is plaintext by default unless mTLS is enforced (Istio, Linkerd, or cert-manager). |
| Secrets at rest | Are DB credentials, API keys, and webhook secrets stored in Kubernetes `Secrets` (base64-encoded, not encrypted by default) vs. an external vault (HashiCorp Vault, AWS Secrets Manager, `external-secrets-operator`)? |
| Browser notifications | Are notification payloads sent over HTTPS? Is the service worker registration on a secure origin? |

**Mitigations:**
- Enforce `sslmode=verify-full` on PostgreSQL connections with properly rotated certificates.
- Deploy a service mesh (Istio/Linkerd) or use cert-manager to issue per-pod TLS certificates for mTLS between services.
- Use `external-secrets-operator` or `sealed-secrets` to manage secrets. Never store secrets in ConfigMaps.
- Enable etcd encryption at rest for Kubernetes Secrets.

---

### A03: Injection

**Risk Level: MEDIUM**

| Vector | Detail |
|---|---|
| GraphQL query injection | Strawberry on Django uses the Django ORM, which parameterizes queries — **low risk** for SQL injection if the ORM is used correctly. However, any raw SQL usage (`connection.cursor()`, `extra()`, `RawSQL`) is a direct risk. |
| GraphQL query abuse | Without depth limiting and complexity analysis, attackers can craft deeply nested or aliased queries that cause excessive DB load (query-of-death). |
| OpenSLO YAML parsing | **Critical**: Does the YAML parser use `yaml.safe_load()` or `yaml.load()`? The latter allows arbitrary Python object instantiation (RCE). |
| `slo_name` in file paths | If `slo_name` from an alert label is used to construct a file path for loading OpenSLO definitions, path traversal is possible (e.g., `slo_name=../../etc/passwd`). This was identified in PR #3 — verify the fix uses allowlisting or `os.path.basename()` stripping. |
| AI agent prompt injection | If the enrichment agent passes alert labels or descriptions into an LLM prompt, attacker-controlled alert content could manipulate agent behavior (indirect prompt injection). |

**Mitigations:**
- Enforce `yaml.safe_load()` everywhere. Grep the codebase: `grep -r "yaml.load" --include="*.py"`.
- Validate and sanitize `slo_name` — allowlist pattern `^[a-zA-Z0-9_-]+$`, reject anything else.
- Add GraphQL query depth limiting (max depth 10) and complexity analysis via Strawberry extensions.
- If using LLM-based enrichment, sanitize alert label values before including in prompts.

---

### A04: Insecure Design

**Risk Level: MEDIUM**

| Concern | Detail |
|---|---|
| Trust boundary: enrichment pipeline | The AI agent trusts data from three sources: Alertmanager payloads, PostgreSQL, and flat files (OpenSLO YAML, business goals). If any source is compromised, the agent's output is tainted — and that output is displayed to users and potentially drives automated responses. There is no integrity verification of flat-file content. |
| GraphQL subscriptions | If WebSocket subscriptions are used for real-time alert updates, each subscription holds an open connection. Without connection limits, an attacker can exhaust server resources (connection-level DoS). |
| Browser notifications | Web Push notifications rely on service worker registration and VAPID keys. Can a compromised or spoofed notification trick an operator into taking action? Notification content should be minimal — link to the dashboard for details, don't include actionable data in the notification itself. |
| Automated remediation | If the agent ever executes remediation actions (restart pods, scale deployments), the design must enforce approval gates. An attacker who can inject alerts could trigger arbitrary remediation. |

**Mitigations:**
- Treat the enrichment pipeline as a trust boundary. Validate and sign flat-file content (e.g., checksum verification). Log all agent decisions for audit.
- Limit concurrent WebSocket connections per client (e.g., 5) and globally (e.g., 1000).
- Implement human-in-the-loop approval for any automated remediation beyond informational enrichment.
- Notification payloads should contain only alert IDs and severity, not full context.

---

### A05: Security Misconfiguration

**Risk Level: HIGH**

| Misconfiguration | Impact |
|---|---|
| Django `DEBUG=True` | Leaks full stack traces, settings, SQL queries, and installed apps to any user who triggers an error. |
| Django `ALLOWED_HOSTS` | If set to `['*']`, enables host-header attacks. |
| GraphQL introspection enabled | Exposes the full schema — every type, field, and mutation — to attackers. Essential for development, dangerous in production. |
| Prometheus `/metrics` exposed | Leaks internal metrics, service names, error rates, pod names, and infrastructure topology. |
| Kubernetes RBAC | Default service accounts in `default` namespace have broad permissions. The AI agent service account should have minimal RBAC (read-only access to ConfigMaps for OpenSLO definitions, nothing else). |
| CORS misconfiguration | If the GraphQL API allows `Access-Control-Allow-Origin: *`, any site can make authenticated requests on behalf of a logged-in user. |
| Helm default values | `kube-prometheus-stack` Helm chart installs Grafana with default admin credentials (`admin/prom-operator`). |

**Mitigations:**
- **PoC**: Acceptable to have introspection and debug enabled. Document what must change for production.
- **Production checklist**: `DEBUG=False`, explicit `ALLOWED_HOSTS`, introspection disabled, CORS restricted to dashboard origin, Grafana credentials rotated, NetworkPolicies restricting `/metrics` access to Prometheus pods only.
- Review and tighten Kubernetes RBAC for every service account. Apply Pod Security Standards (`restricted` profile).

---

### A06: Vulnerable and Outdated Components

**Risk Level: MEDIUM**

| Concern | Detail |
|---|---|
| Python dependencies | FastAPI, Django, Strawberry, PyYAML, Pydantic, uvicorn — all must be scanned. Use `pip-audit` in CI. |
| Node.js dependencies | Next.js and npm ecosystem — use `npm audit` in CI. |
| Container base images | `python:3.12-slim` — track CVEs via `trivy image python:3.12-slim`. Alpine-based images have fewer CVEs but can cause compatibility issues with compiled dependencies. |
| Helm chart versions | `kube-prometheus-stack` — pin to a specific chart version. Unpinned `helm upgrade` can introduce breaking changes or vulnerable components. |
| Kubernetes version | Kind uses the Kubernetes version from its node image — ensure it's within the supported window. |

**Mitigations:**
- Add `pip-audit`, `npm audit`, and `trivy` scans to CI pipeline.
- Pin all dependency versions (use lock files: `poetry.lock`, `package-lock.json`).
- Pin Helm chart versions in Makefile.
- Set up Dependabot or Renovate for automated dependency update PRs.

---

### A07: Identification and Authentication Failures

**Risk Level: HIGH**

| Surface | Concern |
|---|---|
| FastAPI webhook `/alert` | **Unauthenticated by design.** This is the highest-priority authentication gap. Any pod in the cluster (or anyone with network access) can POST fabricated alerts. |
| GraphQL API | What auth mechanism? JWT tokens (stateless, need revocation strategy), session cookies (need CSRF protection), API keys (need rotation)? Is there rate limiting to prevent credential stuffing? |
| Next.js dashboard | Is there authentication? If using NextAuth, which provider? Are sessions properly invalidated on logout? |
| Django Admin | Session-based auth with CSRF tokens (good default). But is 2FA enforced? Are admin credentials in source control? |
| Prometheus/Alertmanager/Grafana | All expose web UIs. Default Grafana credentials are well-known. Prometheus and Alertmanager have no built-in auth. |

**Mitigations:**
- Webhook: Implement HMAC signature validation or shared-secret `Authorization` header. Configure Alertmanager's `http_config.authorization` to send the secret.
- GraphQL: Implement JWT with short expiry (15 min access, 7 day refresh) and token revocation. Add rate limiting (e.g., 100 req/min per IP).
- All monitoring UIs: Access only through `kubectl port-forward` or behind an authenticating reverse proxy.

---

### A08: Software and Data Integrity Failures

**Risk Level: MEDIUM**

| Concern | Detail |
|---|---|
| Container image integrity | Are images signed (cosign/Notary)? Without signature verification, a compromised registry or MITM could inject malicious images. |
| Helm chart integrity | Is the Helm chart provenance verified? `helm install` from a public repo without `--verify` trusts the repo. |
| CI/CD pipeline | GitHub Actions secrets: are they scoped to specific environments? Is OIDC used instead of long-lived tokens? Are workflow files protected from unauthorized modification (branch protection, CODEOWNERS)? |
| Flat-file integrity | OpenSLO YAML and business goal files are loaded at runtime. If an attacker modifies these files (via compromised ConfigMap, volume mount, or container escape), the agent operates on poisoned data with no integrity check. |
| Dependency supply chain | Are lock files committed? Is `pip install --require-hashes` used? |

**Mitigations:**
- Sign container images with `cosign` and enforce signature verification in the cluster (e.g., Kyverno or OPA Gatekeeper policy).
- Use OIDC for CI/CD authentication to cloud providers; avoid long-lived secrets.
- Commit lock files. Consider using `pip install --require-hashes` for Python.
- Add checksums to flat-file ConfigMaps and validate at load time.

---

### A09: Security Logging and Monitoring Failures

**Risk Level: MEDIUM (ironic)**

This system **is** a monitoring system — but is it monitoring itself?

| Concern | Detail |
|---|---|
| Self-monitoring | If the alert pipeline (Prometheus → Alertmanager → webhook → agent) fails silently, no one gets notified. Quis custodiet ipsos custodes? |
| Audit logging | Are GraphQL mutations logged (who changed what, when)? Are webhook invocations logged with source IP and payload hash? |
| Security events | Are failed authentication attempts, authorization failures, and anomalous query patterns logged and alerted on? |
| Log integrity | If an attacker compromises the system, can they tamper with logs? Are logs shipped to an external, append-only store? |
| Alert fatigue | If the agent generates too many enriched alerts, operators may ignore them — including genuine security alerts. |

**Mitigations:**
- Implement a "dead man's switch" — a synthetic alert that must fire regularly; if it stops, something is wrong with the pipeline.
- Log all GraphQL mutations and webhook invocations to a structured logging system (e.g., Loki, ELK, CloudWatch).
- Ship logs to an external store that the application service accounts cannot modify.
- Separate security alerts from operational alerts in Alertmanager routing.

---

### A10: Server-Side Request Forgery (SSRF)

**Risk Level: LOW-MEDIUM**

| Vector | Detail |
|---|---|
| AI agent outbound requests | The enrichment agent reads from PostgreSQL and flat files. If it ever fetches external URLs (e.g., documentation links, runbook URLs from alert annotations), those URLs could be attacker-controlled, enabling SSRF. |
| GraphQL resolvers | Do any resolvers fetch data from URLs provided in user input? If so, validate against an allowlist of permitted hosts. |
| Next.js server-side rendering | Next.js `getServerSideProps` or API routes that fetch external data based on user input can be SSRF vectors. |

**Mitigations:**
- The AI agent should never fetch arbitrary URLs. If external data is needed, use an allowlist of permitted endpoints.
- Egress network policies in Kubernetes: restrict outbound traffic from agent pods to only PostgreSQL and the internal Kubernetes DNS.
- Validate and sanitize any URLs in GraphQL inputs or Next.js API routes.

---

## MITRE ATT&CK Assessment

### Initial Access

| Technique | Relevance | Detail |
|---|---|---|
| **T1190: Exploit Public-Facing Application** | HIGH | Three public-facing surfaces: Next.js dashboard, GraphQL API, FastAPI webhook endpoint. The webhook endpoint is unauthenticated — lowest-hanging fruit. GraphQL introspection (if enabled) gives attackers a full API map. |
| **T1078: Valid Accounts** | MEDIUM | Stolen credentials for dashboard/admin access. Default Grafana credentials (`admin/prom-operator`). Kubernetes service account tokens if pods are compromised. |
| **T1195: Supply Chain Compromise** | LOW-MEDIUM | Compromised PyPI/npm packages, malicious container base images, or tampered Helm charts. |

### Execution

| Technique | Relevance | Detail |
|---|---|---|
| **T1059: Command and Scripting Interpreter** | MEDIUM-HIGH | If the AI agent ever executes remediation commands (restart pods, run scripts), an attacker who can inject alerts could trigger arbitrary command execution. Even without execution, `yaml.load()` (unsafe) enables arbitrary Python code execution via deserialization. |
| **T1203: Exploitation for Client Execution** | MEDIUM | XSS via the Next.js dashboard — if enriched alert content (which includes attacker-controllable alert labels) is rendered without sanitization, stored XSS is possible. An operator viewing a malicious alert in the dashboard could have their session hijacked. |

### Persistence

| Technique | Relevance | Detail |
|---|---|---|
| **T1053: Scheduled Task/Job** | LOW | Kubernetes CronJobs (if used for exerciser scripts or cleanup tasks) could be modified to maintain persistence. |
| **T1098: Account Manipulation** | MEDIUM | Django admin account creation. If an attacker gains admin access, they can create backdoor accounts. Kubernetes RBAC — a compromised service account could create new RoleBindings. |
| **T1505: Server Software Component** | MEDIUM | Injecting a malicious GraphQL resolver or Django middleware provides persistent code execution within the application. |

### Privilege Escalation

| Technique | Relevance | Detail |
|---|---|---|
| **T1078: Valid Accounts** | HIGH | Kubernetes service account tokens mounted in pods by default. If a pod is compromised, the attacker gets the service account's RBAC permissions. Overly permissive service accounts are common in PoC deployments. |
| **T1611: Escape to Host** | MEDIUM | Container escape from a compromised pod to the Kubernetes node. Mitigated by Pod Security Standards (`restricted` profile), seccomp profiles, and avoiding privileged containers. |

### Defense Evasion

| Technique | Relevance | Detail |
|---|---|---|
| **T1070: Indicator Removal** | HIGH | **This is the monitoring system.** If an attacker compromises the alert pipeline, they can suppress alerts, modify enriched alert data, or delete alert history from PostgreSQL — effectively blinding the operators. |
| **T1036: Masquerading** | MEDIUM | Injecting fake alerts that look legitimate to cause alert fatigue, masking real attacks behind noise. |

### Collection

| Technique | Relevance | Detail |
|---|---|---|
| **T1005: Data from Local System** | MEDIUM | PostgreSQL contains business-sensitive data: SLO definitions, business goals, alert history, enrichment data. Flat files contain operational response procedures. |
| **T1530: Data from Cloud Storage** | LOW | If business goal files or OpenSLO definitions are sourced from cloud storage (S3, GCS), credentials for those stores become targets. |

### Impact

| Technique | Relevance | Detail |
|---|---|---|
| **T1485: Data Destruction** | HIGH | Deleting enriched alert history from PostgreSQL erases the operational record. Deleting OpenSLO definitions or business goal files disables the enrichment pipeline. |
| **T1489: Service Stop** | HIGH | DoS on Alertmanager or the webhook endpoint = **alerts stop flowing**. The monitoring system goes silent. This is the most dangerous impact — operators lose visibility during an incident. |
| **T1565: Data Manipulation** | HIGH | Modifying enriched alert data or business goals to cause incorrect operational responses. More subtle and dangerous than destruction. |

---

## Threat Model Summary

| # | Threat | Likelihood | Impact | Risk | Mitigation Status |
|---|---|---|---|---|---|
| 1 | Unauthenticated alert injection via webhook | HIGH | HIGH | **CRITICAL** | Not mitigated — endpoint open by design |
| 2 | Alert pipeline DoS (T1489) — operators lose visibility | MEDIUM | CRITICAL | **CRITICAL** | Not mitigated — no redundancy or dead-man's-switch |
| 3 | GraphQL query-of-death (deeply nested/aliased queries) | MEDIUM | HIGH | **HIGH** | Not mitigated — no depth/complexity limiting |
| 4 | Stored XSS via alert labels rendered in dashboard | MEDIUM | HIGH | **HIGH** | Unknown — depends on Next.js output encoding |
| 5 | YAML deserialization RCE (`yaml.load` vs `safe_load`) | LOW | CRITICAL | **HIGH** | Partially mitigated (flagged in PR #3) |
| 6 | Path traversal via `slo_name` in file lookups | LOW | HIGH | **MEDIUM** | Partially mitigated (flagged in PR #3) |
| 7 | Default Grafana credentials in production | HIGH | MEDIUM | **MEDIUM** | Not mitigated — Helm default |
| 8 | Exposed Prometheus/Alertmanager endpoints | MEDIUM | MEDIUM | **MEDIUM** | Not mitigated — default Helm config |
| 9 | Container escape / K8s privilege escalation | LOW | CRITICAL | **MEDIUM** | Not mitigated — no Pod Security Standards |
| 10 | Flat-file tampering (OpenSLO/business goals) | LOW | HIGH | **MEDIUM** | Not mitigated — no integrity verification |
| 11 | Log/alert tampering by compromised agent | LOW | HIGH | **MEDIUM** | Not mitigated — no external log shipping |
| 12 | AI prompt injection via alert content | LOW | MEDIUM | **LOW** | Not mitigated — depends on LLM usage |
| 13 | Supply chain compromise (dependencies) | LOW | HIGH | **MEDIUM** | Not mitigated — no scanning in CI |

---

## Recommendations (Prioritized)

### 1. [CRITICAL] Authenticate the webhook endpoint

Alertmanager supports `http_config.authorization` on webhook receivers. Implement shared-secret or HMAC validation on the `/alert` endpoint. As a defense-in-depth measure, add a Kubernetes NetworkPolicy restricting ingress to the webhook pod to only the Alertmanager pod IP/label.

```yaml
# Alertmanager config
receivers:
  - name: 'ai-agent'
    webhook_configs:
      - url: 'http://ai-agent:8000/alert'
        http_config:
          authorization:
            credentials: '<shared-secret>'
```

### 2. [CRITICAL] Implement alert pipeline self-monitoring

Deploy a "dead man's switch" — a synthetic alert that fires on a schedule. If the enrichment pipeline doesn't process it within the expected window, a separate monitoring path (e.g., external health check, PagerDuty heartbeat) alerts operators that the pipeline is down.

### 3. [HIGH] Add GraphQL query depth and complexity limiting

Use Strawberry's extension system to enforce maximum query depth (10), maximum query complexity, and field-level rate limiting. Disable introspection in production.

```python
# Strawberry example
from strawberry.extensions import QueryDepthLimiter
schema = strawberry.Schema(
    query=Query,
    extensions=[QueryDepthLimiter(max_depth=10)],
)
```

### 4. [HIGH] Sanitize alert content before rendering in Next.js

Alert labels and annotations are attacker-controlled (especially if the webhook is unauthenticated). Ensure all alert content rendered in the dashboard is properly escaped. React's JSX escaping handles most cases, but `dangerouslySetInnerHTML` or markdown rendering can bypass it. Audit all rendering paths.

### 5. [HIGH] Enforce `yaml.safe_load()` everywhere

Grep the entire codebase for `yaml.load(` and replace with `yaml.safe_load(`. Add a pre-commit hook or CI check to prevent `yaml.load` from being reintroduced.

### 6. [HIGH] Lock down Kubernetes RBAC and apply Pod Security Standards

- Apply `restricted` Pod Security Standard to all namespaces.
- Create dedicated service accounts for each workload with minimal RBAC.
- The AI agent service account needs only: read ConfigMaps (for OpenSLO files), connect to PostgreSQL (network-level, not RBAC).
- Disable automounting of service account tokens where not needed.

### 7. [MEDIUM] Deploy Kubernetes NetworkPolicies

```yaml
# Example: restrict webhook pod ingress
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: webhook-ingress
spec:
  podSelector:
    matchLabels:
      app: ai-agent
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: alertmanager
      ports:
        - port: 8000
```

Segment the cluster into trust zones: monitoring namespace (Prometheus, Alertmanager), application namespace (Django, FastAPI, Next.js), and data namespace (PostgreSQL).

### 8. [MEDIUM] Implement secrets management

Move from Kubernetes Secrets (base64-encoded) to `external-secrets-operator` with a backing store (AWS Secrets Manager, HashiCorp Vault, or even `sealed-secrets` for a PoC). Never store secrets in ConfigMaps or environment variables visible in pod specs.

### 9. [MEDIUM] Add dependency scanning to CI

```yaml
# GitHub Actions example
- name: Python security scan
  run: pip-audit --require-hashes -r requirements.txt
- name: Node security scan
  run: npm audit --audit-level=high
- name: Container scan
  run: trivy image ai-agent:latest --severity HIGH,CRITICAL
```

### 10. [MEDIUM] Enforce PostgreSQL TLS

Configure Django and FastAPI database connections with `sslmode=verify-full`. Issue TLS certificates via cert-manager for the PostgreSQL server.

### 11. [LOW] Sign container images

Use `cosign` to sign images in CI and enforce signature verification in the cluster via a policy engine (Kyverno or OPA Gatekeeper).

### 12. [LOW] Implement audit logging for GraphQL mutations

Log all mutations with: timestamp, authenticated user, mutation name, input variables (redacting sensitive fields), source IP. Ship to an external logging system.

---

## Security Architecture Recommendations

### Network Segmentation (Kubernetes NetworkPolicies)

```
┌─────────────────────────────────────────────────┐
│  Ingress Namespace                              │
│  ┌─────────────┐                                │
│  │ Ingress     │ ← external traffic             │
│  │ Controller  │                                │
│  └──────┬──────┘                                │
└─────────┼───────────────────────────────────────┘
          │ only ports 80/443
┌─────────┼───────────────────────────────────────┐
│  App Namespace                                  │
│  ┌──────▼──────┐    ┌──────────────┐            │
│  │  Next.js    │───▶│  GraphQL/    │            │
│  │  Frontend   │    │  Django      │            │
│  └─────────────┘    └──────┬───────┘            │
│                            │                    │
│                     ┌──────▼───────┐            │
│                     │  FastAPI     │◀── AM only  │
│                     │  Webhook     │            │
│                     └──────────────┘            │
└────────────────────────┼────────────────────────┘
                         │ port 5432 only
┌────────────────────────┼────────────────────────┐
│  Data Namespace        │                        │
│  ┌─────────────────────▼──┐                     │
│  │     PostgreSQL         │                     │
│  └────────────────────────┘                     │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Monitoring Namespace                           │
│  ┌────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │ Prometheus │  │ Alertmanager │  │ Grafana │ │
│  └────────────┘  └──────────────┘  └─────────┘ │
│  No external ingress — port-forward only        │
└─────────────────────────────────────────────────┘
```

### Service Mesh (mTLS)

For production, deploy Linkerd (lighter weight) or Istio to enforce mTLS between all services. This eliminates the need for application-level TLS configuration between internal services and provides observability (golden metrics per service pair) as a bonus.

### Secrets Management

```
external-secrets-operator
         │
         ▼
  ┌──────────────┐
  │ Vault / AWS  │  ← source of truth
  │ Secrets Mgr  │
  └──────┬───────┘
         │ syncs to
         ▼
  Kubernetes Secrets ← consumed by pods
```

### Pod Security Standards

Apply the `restricted` profile at the namespace level:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: app
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
```

This enforces: non-root containers, read-only root filesystem, no privilege escalation, dropped capabilities, seccomp profiles.

---

## PoC vs. Production Checklist

| Item | PoC (acceptable) | Production (required) |
|---|---|---|
| Webhook auth | NetworkPolicy only | HMAC + NetworkPolicy |
| GraphQL introspection | Enabled | Disabled |
| Django DEBUG | True | False |
| Grafana credentials | Default | Rotated + SSO |
| Prometheus UI | Port-forward | Auth proxy or disabled |
| Container scanning | Manual | CI/CD gate |
| Image signing | Skip | Enforced |
| Pod Security Standards | Warn | Enforce (restricted) |
| Network Policies | Basic | Full segmentation |
| Secrets management | K8s Secrets | External vault |
| mTLS | Skip | Service mesh |
| Audit logging | Application logs | External SIEM |
| Dependency scanning | Manual | CI/CD gate |
| Dead man's switch | Skip | Required |
