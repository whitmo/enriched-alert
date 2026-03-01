# Security Assessment: Meridian Marketplace

## Executive Summary

The Meridian Marketplace architecture presents a **moderate-to-high risk posture** typical of a multi-service Kubernetes deployment with several unauthenticated internal endpoints. The most critical finding is the unauthenticated FastAPI webhook endpoint (`/alert`), which is Internet-reachable in non-isolated deployments and serves as the primary ingestion point for the entire alert pipeline. Secondary concerns include GraphQL introspection/complexity abuse, flat-file path traversal via `slo_name`, and the recursive trust problem of a monitoring system that cannot reliably monitor itself. For a PoC these are acceptable with documented risk; for production, the top 5 recommendations below should be addressed before deployment.

---

## OWASP Top 10 (2021) Assessment

### A01: Broken Access Control

**Risk Level: HIGH**

| Surface | Finding |
|---|---|
| GraphQL API (Strawberry/Django) | Authentication mechanism unspecified. If JWT or session-based, token scope and expiry must be enforced. If no auth, any client can query/mutate business data. |
| FastAPI webhook `/alert` | **Unauthenticated by design.** Alertmanager's webhook integration does not natively support auth headers. Any party able to reach this endpoint can inject fabricated alerts into the enrichment pipeline. |
| Next.js dashboard | Authentication for dashboard access is unspecified. If publicly accessible, all SLO/alert data is exposed. |
| Prometheus `/metrics` | Typically exposed without auth. Leaks service names, error rates, latency distributions — useful for attacker reconnaissance. |
| Django admin | If enabled (`/admin/`), default credentials or weak passwords grant full ORM access. |

**Mitigations:**
- **PoC:** Accept risk, document that `/alert` is unauthenticated. Restrict via Kubernetes NetworkPolicy to Alertmanager pods only.
- **Production:** Add HMAC signature verification on webhook payloads (custom Alertmanager template + FastAPI middleware). Require auth on GraphQL. Disable Django admin or restrict to internal network. Put Prometheus behind an auth proxy (oauth2-proxy).

---

### A02: Cryptographic Failures

**Risk Level: MEDIUM**

| Surface | Finding |
|---|---|
| PostgreSQL connection | TLS between Django/FastAPI and PostgreSQL is often disabled in local/Kind clusters. Credentials traverse the pod network in cleartext. |
| Inter-service communication | No mTLS by default in Kind. GraphQL ↔ Django, FastAPI ↔ PostgreSQL, Alertmanager → FastAPI all use plain HTTP within the cluster. |
| Secrets management | DB credentials, API keys likely stored in Kubernetes Secrets (base64-encoded, not encrypted at rest by default in etcd). |
| Browser notifications | If using Web Push, VAPID keys must be protected. If using plain WebSocket, subscription tokens could be intercepted. |

**Mitigations:**
- **PoC:** Accept risk for local Kind cluster. Document that mTLS is deferred.
- **Production:** Enable PostgreSQL `sslmode=require`. Deploy a service mesh (Istio/Linkerd) for mTLS. Use external-secrets-operator or sealed-secrets for secret management. Enable etcd encryption at rest.

---

### A03: Injection

**Risk Level: MEDIUM**

| Surface | Finding |
|---|---|
| GraphQL queries | No query depth limiting or complexity analysis mentioned. Deeply nested queries can cause ORM N+1 storms or DoS. Strawberry supports extensions for this but they must be explicitly enabled. |
| Django ORM | Low risk if using ORM exclusively (parameterized queries). Risk increases if any `raw()` or `extra()` calls exist. |
| OpenSLO YAML parsing | If using `yaml.load()` instead of `yaml.safe_load()`, arbitrary Python object instantiation is possible via crafted YAML. |
| `slo_name` in file paths | **Path traversal confirmed as a known risk** (referenced in PR #3). If `slo_name` from alert labels is used to construct file paths (e.g., `f"slos/{slo_name}.yaml"`), an attacker injecting `../../etc/passwd` as `slo_name` via the unauthenticated webhook can read arbitrary files. |
| Alertmanager payload | JSON from Alertmanager is structured, but label values are strings. If any label value is rendered unsanitized in the Next.js dashboard, XSS is possible. |

**Mitigations:**
- **PoC:** Use `yaml.safe_load()` exclusively. Sanitize `slo_name` to alphanumeric + hyphen only (`re.sub(r'[^a-zA-Z0-9_-]', '', slo_name)`). Add Strawberry query depth extension.
- **Production:** All of the above, plus WAF rules for GraphQL, input validation middleware on FastAPI.

---

### A04: Insecure Design

**Risk Level: MEDIUM**

| Surface | Finding |
|---|---|
| Trust boundaries | The enrichment pipeline treats alert payloads, DB content, and flat files as trusted input. An attacker who compromises any of these sources controls the agent's output. There is no integrity verification on OpenSLO files at rest. |
| GraphQL subscriptions | If used for real-time dashboard updates, each subscription holds an open WebSocket. No documented connection limits — potential DoS vector. |
| Browser notifications | Web Push notifications are delivered by the browser's push service. They cannot be "spoofed" in the traditional sense, but if the subscription endpoint is leaked, unwanted notifications can be sent. |
| AI agent autonomy | If the agent ever gains the ability to execute remediation commands (scaling, restarts), the unauthenticated webhook becomes a remote code execution vector. |

**Mitigations:**
- **PoC:** Document trust boundaries explicitly. Keep agent to read-only/enrichment-only actions.
- **Production:** Sign OpenSLO files (checksums in a separate integrity manifest). Rate-limit WebSocket connections. Implement approval gates before any automated remediation.

---

### A05: Security Misconfiguration

**Risk Level: HIGH**

| Surface | Finding |
|---|---|
| Django `DEBUG=True` | If deployed with `DEBUG=True`, full stack traces, settings, and SQL queries are exposed on error pages. |
| GraphQL introspection | Strawberry enables introspection by default. In production, this exposes the full schema to attackers, enabling targeted query crafting. |
| Prometheus `/metrics` | Exposed without auth by default in kube-prometheus-stack. Contains internal service topology, error rates, resource utilization. |
| Kubernetes RBAC | Default service accounts in Kind have broad permissions. The AI agent pod likely needs no access to the Kubernetes API, but may inherit a default service account token. |
| Helm chart defaults | kube-prometheus-stack ships with Grafana (default admin/prom-operator), many ServiceMonitors. Attack surface broader than needed for PoC. |

**Mitigations:**
- **PoC:** Set `DEBUG=False` even locally. Disable Grafana in Helm values if unused. Document that introspection is enabled intentionally.
- **Production:** Disable GraphQL introspection. Strip default Grafana credentials. Apply Pod Security Standards (restricted). Create dedicated service accounts with no API access for application pods. NetworkPolicy to restrict `/metrics` access to Prometheus pods only.

---

### A06: Vulnerable and Outdated Components

**Risk Level: MEDIUM**

| Surface | Finding |
|---|---|
| Python dependencies | No `pip-audit` or safety scanning mentioned. FastAPI, Strawberry, Django, PyYAML all have had CVEs. |
| Node.js dependencies | Next.js and its dependency tree. No `npm audit` integration mentioned. |
| Container base images | `python:3.12-slim` is reasonable but still carries OS-level packages. No Trivy/Grype scanning mentioned. |
| Helm charts | kube-prometheus-stack pins a Prometheus version — must track upstream CVEs. |
| Kind/Podman | Local tooling, but Podman CVEs could affect the build pipeline. |

**Mitigations:**
- **PoC:** Run `pip-audit` and `npm audit` once manually, document results.
- **Production:** Integrate dependency scanning into CI (pip-audit, npm audit, Trivy for images). Pin dependencies with lock files. Use distroless or chainguard base images. Renovate/Dependabot for automated updates.

---

### A07: Identification and Authentication Failures

**Risk Level: HIGH**

| Surface | Finding |
|---|---|
| Webhook endpoint | No authentication. By design for Alertmanager compatibility, but any network-reachable client can submit alerts. |
| GraphQL API | Auth mechanism unspecified. If JWT: validate issuer, audience, expiry, and signature algorithm. If session: CSRF protection needed. If API key: rotate strategy needed. |
| Next.js dashboard | No auth mentioned. If public, all business SLO data and alert history is readable. |
| Django admin | If enabled, brute-force protection (rate limiting, account lockout) is not default Django behavior. |

**Mitigations:**
- **PoC:** NetworkPolicy restricting `/alert` to Alertmanager source pods. Basic auth on Next.js dashboard.
- **Production:** HMAC webhook verification. OAuth2/OIDC for dashboard and GraphQL. Disable Django admin or IP-restrict. Add rate limiting to all auth endpoints.

---

### A08: Software and Data Integrity Failures

**Risk Level: LOW (PoC) / MEDIUM (Production)**

| Surface | Finding |
|---|---|
| Container images | No image signing (cosign/Notary) mentioned. Images built locally with Podman and loaded into Kind — supply chain is short but unverified. |
| Helm charts | Charts pulled from public repos without integrity verification beyond Helm's built-in. |
| CI/CD pipeline | Not yet implemented. When added: GitHub Actions secrets must use OIDC, not long-lived tokens. |
| OpenSLO flat files | No integrity verification. Files mounted via ConfigMap — anyone with ConfigMap write access can alter SLO definitions. |

**Mitigations:**
- **PoC:** Accept risk. Short supply chain for local development.
- **Production:** Sign container images with cosign. Pin Helm chart versions with SHA digests. Use Kyverno/OPA to enforce image signatures. RBAC-restrict ConfigMap writes.

---

### A09: Security Logging and Monitoring Failures

**Risk Level: MEDIUM**

| Surface | Finding |
|---|---|
| Self-monitoring paradox | This IS a monitoring system, but there is no documented monitoring of the monitoring stack itself. If Alertmanager goes down, no alerts flow — and nobody is alerted about it. |
| Audit logging | No audit logging for GraphQL mutations (create/update/delete of SLOs, goals). An attacker could modify business goals without trace. |
| Security events | Failed auth attempts, unusual query patterns, webhook injection attempts — none of these generate alerts in the current design. |
| Log aggregation | No centralized logging mentioned. Kubernetes pod logs are ephemeral by default. |

**Mitigations:**
- **PoC:** Add a Prometheus self-health check (Alertmanager → Watchdog alert). Log webhook requests with source IP and timestamp.
- **Production:** Deploy a log aggregator (Loki, EFK). Audit log all GraphQL mutations. Create Prometheus alerts for: Alertmanager down, webhook error rate spike, unusual query volume. Dead man's switch alert to external provider.

---

### A10: Server-Side Request Forgery (SSRF)

**Risk Level: LOW**

| Surface | Finding |
|---|---|
| AI agent | Reads from PostgreSQL and local flat files. No outbound HTTP calls to user-controlled URLs in current design. |
| GraphQL resolvers | If any resolver fetches external URLs (e.g., user-provided avatar URLs, external data sources), SSRF is possible. Current design doesn't indicate this. |
| Next.js SSR | Server-side rendering can be an SSRF vector if any page fetches user-controlled URLs during SSR. |

**Mitigations:**
- **PoC:** No action needed if no outbound URL fetching exists.
- **Production:** If outbound fetching is added, allowlist target hosts. Use network policies to restrict egress from application pods.

---

## MITRE ATT&CK Assessment

### Initial Access

| Technique | ID | Relevance | Notes |
|---|---|---|---|
| Exploit Public-Facing Application | T1190 | **HIGH** | GraphQL API, Next.js dashboard, and FastAPI webhook are all potential entry points. The unauthenticated `/alert` endpoint is the easiest target. |
| Valid Accounts | T1078 | MEDIUM | Stolen dashboard credentials, Django admin credentials, or Kubernetes service account tokens grant persistent access. |
| Trusted Relationship | T1199 | MEDIUM | Alertmanager is implicitly trusted by the webhook receiver. Compromising Alertmanager = full control of the alert pipeline. |

### Execution

| Technique | ID | Relevance | Notes |
|---|---|---|---|
| Command and Scripting Interpreter | T1059 | **HIGH (future)** | If the AI agent gains remediation capabilities (K8s API calls, script execution), fabricated alerts become RCE. Currently enrichment-only = low risk. |
| Exploitation for Client Execution | T1203 | MEDIUM | XSS via unsanitized alert labels rendered in the Next.js dashboard could execute JavaScript in operator browsers. |
| Server Software Component | T1505 | LOW | Django middleware or Strawberry extensions could be backdoored if dependency supply chain is compromised. |

### Persistence

| Technique | ID | Relevance | Notes |
|---|---|---|---|
| Account Manipulation | T1098 | MEDIUM | Django admin allows creating superuser accounts. If admin is accessible, attacker persists via new accounts. |
| Scheduled Task/Job | T1053 | LOW | K8s CronJobs (if used for exerciser scripts or maintenance) could be modified for persistence. |
| Implant Internal Image | T1525 | LOW | Attacker with registry/Kind access could replace container images with backdoored versions. |

### Privilege Escalation

| Technique | ID | Relevance | Notes |
|---|---|---|---|
| Valid Accounts: Cloud Accounts | T1078.004 | MEDIUM | Default K8s service account tokens mounted in pods may have excessive RBAC permissions. Compromising the agent pod could allow lateral movement via the K8s API. |
| Container Escape | T1611 | LOW | Requires kernel exploit or misconfigured pod security. Kind clusters may run containers as root by default. |

### Defense Evasion

| Technique | ID | Relevance | Notes |
|---|---|---|---|
| Indicator Removal | T1070 | **HIGH** | Since this IS the logging/monitoring system, an attacker who compromises it can suppress alerts, delete enrichment history, and tamper with audit trails. A compromised monitoring system is blind to its own compromise. |
| Impair Defenses | T1562 | HIGH | Disabling Alertmanager routes, modifying Prometheus rules, or corrupting OpenSLO definitions all silently degrade detection capability. |

### Lateral Movement

| Technique | ID | Relevance | Notes |
|---|---|---|---|
| Exploitation of Remote Services | T1210 | MEDIUM | PostgreSQL access from the agent pod could be leveraged to attack other services sharing the database. |
| Internal Proxy | T1090.001 | LOW | Compromised pods could proxy traffic through the cluster network. |

### Collection

| Technique | ID | Relevance | Notes |
|---|---|---|---|
| Data from Local System | T1005 | MEDIUM | PostgreSQL contains business-sensitive SLO data, operational goals, alert history. Flat files contain business strategy. |
| Data from Information Repositories | T1213 | MEDIUM | OpenSLO definitions reveal infrastructure architecture, service dependencies, and performance thresholds — valuable for planning further attacks. |

### Impact

| Technique | ID | Relevance | Notes |
|---|---|---|---|
| Data Destruction | T1485 | HIGH | Deleting enriched alert history removes incident response evidence. Deleting SLO definitions disables monitoring. |
| Service Stop | T1489 | **HIGH** | DoS on Alertmanager or the webhook endpoint = alerts don't flow = SLO breaches go undetected. This is the highest-impact scenario for a monitoring system. |
| Data Manipulation | T1565 | HIGH | Modifying SLO thresholds or business goals changes what the system considers "healthy" — attacks become invisible by redefining normal. |

---

## Threat Model Summary

| # | Threat | Likelihood | Impact | Risk | Mitigation Status |
|---|---|---|---|---|---|
| 1 | Fabricated alert injection via unauthenticated webhook | High | High | **Critical** | Unmitigated — no auth on `/alert` |
| 2 | Path traversal via `slo_name` in file lookups | Medium | High | **High** | Partially mitigated (PR #3 awareness) |
| 3 | GraphQL DoS via deep/complex queries | Medium | Medium | **High** | Unmitigated — no depth/complexity limits |
| 4 | Monitoring self-blindness (compromised system can't detect own compromise) | Low | Critical | **High** | Unmitigated — no external dead man's switch |
| 5 | SLO/goal data manipulation via unauthenticated GraphQL | Medium | High | **High** | Unmitigated — auth mechanism unspecified |
| 6 | Prometheus metrics exposing internal topology | High | Low | **Medium** | Unmitigated — default exposure |
| 7 | XSS via unsanitized alert labels in dashboard | Medium | Medium | **Medium** | Unknown — depends on Next.js sanitization |
| 8 | Django DEBUG mode / admin exposure in production | Medium | Medium | **Medium** | Unmitigated — not documented |
| 9 | Container image supply chain compromise | Low | High | **Medium** | Unmitigated — no signing/scanning |
| 10 | K8s service account token abuse for lateral movement | Low | High | **Medium** | Unmitigated — default RBAC |
| 11 | YAML deserialization via unsafe loader | Low | Critical | **Medium** | Unknown — must verify `safe_load` usage |
| 12 | AI agent escalation to RCE if remediation is added | Low | Critical | **Medium** | Mitigated by current design (enrichment only) |

---

## Recommendations (Prioritized)

### CRITICAL

1. **Authenticate the webhook endpoint.** Implement HMAC signature verification on `/alert` payloads. As a stopgap, deploy a Kubernetes NetworkPolicy restricting ingress to the FastAPI pod from Alertmanager pods only.

2. **Sanitize `slo_name` before file path construction.** Strip or reject any `slo_name` containing path separators, dots-dots, or non-alphanumeric characters. Validate against a known allowlist of SLO names.

### HIGH

3. **Add GraphQL query depth and complexity limits.** Use Strawberry's `MaxTokensLimiter` or a custom extension to cap query depth at 5–7 levels and total complexity at a defined threshold.

4. **Implement authentication on the GraphQL API.** JWT with short-lived tokens (15min access, 7d refresh) is recommended. Enforce on all mutations; reads can be scoped.

5. **Deploy Kubernetes NetworkPolicies.** Default-deny ingress per namespace. Explicitly allow only: Alertmanager → FastAPI, Prometheus → all `/metrics`, Next.js → GraphQL, Django → PostgreSQL.

6. **Add an external dead man's switch.** Configure Alertmanager's Watchdog alert to ping an external service (e.g., Healthchecks.io, PagerDuty). If the ping stops, the external service alerts — breaking the self-monitoring recursion.

### MEDIUM

7. **Set Django `DEBUG=False` and disable admin in non-dev environments.** Use environment variable gating: `DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'`.

8. **Disable GraphQL introspection in production.** Strawberry supports conditional introspection based on environment.

9. **Use `yaml.safe_load()` exclusively.** Grep the codebase for `yaml.load(` and replace all instances. Add a pre-commit hook or linter rule to prevent regression.

10. **Implement dependency scanning.** Add `pip-audit` and `npm audit` to CI. Run Trivy on container images before pushing.

11. **Restrict Kubernetes service account permissions.** Set `automountServiceAccountToken: false` on application pods. Create dedicated service accounts with minimal RBAC for pods that need K8s API access.

12. **Audit log GraphQL mutations.** Log who changed what, when. Use Django signals or Strawberry middleware.

### LOW

13. **Enable mTLS between services.** Deploy Linkerd (lighter) or Istio for automatic mTLS. Alternatively, use cert-manager to issue service certificates.

14. **Sign container images.** Use cosign with keyless signing (Fulcio/Rekor) or a local key pair. Enforce with Kyverno admission policy.

15. **Enable PostgreSQL TLS.** Set `sslmode=require` in Django/FastAPI database configuration. Use cert-manager to provision PostgreSQL server certificates.

16. **Plan for secrets rotation.** Implement external-secrets-operator pointing to a vault (HashiCorp Vault, AWS Secrets Manager) rather than static Kubernetes Secrets.

---

## Security Architecture Recommendations

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
│                                                             │
│  ┌──────────────┐  NetworkPolicy  ┌────────────────────┐   │
│  │  monitoring   │ ◄────────────► │    application      │   │
│  │  namespace    │  (restricted)  │    namespace        │   │
│  │              │                │                     │   │
│  │ Prometheus   │ scrape /metrics│ Next.js (auth'd)    │   │
│  │ Alertmanager ├───────────────►│ GraphQL (JWT)       │   │
│  │              │  webhook HMAC  │ Django (no admin)    │   │
│  │              ├───────────────►│ FastAPI (HMAC)      │   │
│  │              │                │ PostgreSQL (TLS)    │   │
│  └──────┬───────┘                └────────────────────┘   │
│         │                                                   │
│         │ Watchdog                                          │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │ Dead Man's   │ ──── external ping ───► Healthchecks.io  │
│  │ Switch       │                                          │
│  └──────────────┘                                          │
│                                                             │
│  Pod Security Standards: restricted                         │
│  Service Mesh: mTLS (Linkerd/Istio)                        │
│  Secrets: external-secrets-operator                         │
│  RBAC: least privilege, no auto-mount SA tokens             │
│  Images: signed (cosign), scanned (Trivy)                  │
│  Network: default-deny ingress, explicit allowlist          │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Principles

1. **Defense in depth** — No single control prevents all attacks. NetworkPolicy + auth + input validation + monitoring overlap intentionally.
2. **Least privilege** — Every pod, service account, and database user gets the minimum permissions needed.
3. **Assume breach** — The monitoring system must be monitored externally. Audit logs must be shipped off-cluster.
4. **PoC vs Production is a spectrum** — Items marked "PoC: accept risk" must be tracked and resolved before any production exposure. The threat model summary table serves as that tracking mechanism.

---

## Appendix: PoC vs Production Checklist

| Control | PoC (local Kind) | Production |
|---|---|---|
| Webhook auth | NetworkPolicy only | HMAC signature verification |
| GraphQL auth | None (local only) | JWT/OIDC |
| Dashboard auth | None (local only) | OAuth2 |
| mTLS | None | Service mesh |
| Secrets management | K8s Secrets | External vault |
| Image scanning | Manual one-time | CI pipeline |
| Network policies | Optional | Mandatory default-deny |
| GraphQL introspection | Enabled | Disabled |
| Django DEBUG | False | False |
| Audit logging | Pod stdout | Centralized (Loki/EFK) |
| Dead man's switch | None | External service |
| Dependency scanning | Manual | Automated in CI |
