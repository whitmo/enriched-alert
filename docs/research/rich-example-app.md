# Rich Example App: SLOs as the API to the Business

## Core Thesis

SLOs (measures of health) and their related operational responses ARE the API to the business. Business goals connect to SLOs, SLO breaches trigger enriched responses that reference business context, and everything is visible in real-time.

This document designs a concrete example application — **Meridian Marketplace** — that makes this principle tangible.

---

## Fictional Business: Meridian Marketplace

An online marketplace connecting local artisans with buyers. Three services:

| Service | Responsibility | Business Stake |
|---------|---------------|----------------|
| **Catalog Service** | Listings, search, recommendations | Buyer engagement, discoverability |
| **Order Service** | Checkout, payment processing, fulfillment tracking | Revenue, buyer trust |
| **Seller Service** | Onboarding, inventory management, payout processing | Seller retention, marketplace supply |

---

## 1. Business Goals to SLOs Mapping

The key insight: every SLO should answer "what business promise does this protect?"

### SLO Table

| # | Business Goal | SLI | SLO Target | Error Budget Response |
|---|--------------|-----|------------|----------------------|
| 1 | **Buyers find products fast** | Proportion of search requests returning 2xx with p95 < 300ms | 99.9% over 28d | Low: auto-alert Catalog team, log slow queries. Medium: page L1 on-call, auto-scale search. High: page L2 + IC, failover to read replica. |
| 2 | **Checkout just works** | Proportion of initiated checkouts completing successfully | 99.5% over 28d | Low: alert Order team, review payment gateway errors. Medium: page L1, test alternate payment processors, notify support. High: page L2 + IC, disable affected payment methods. |
| 3 | **Payments process quickly** | p99 latency of payment processing requests | 99% complete < 2s over 28d | Low: alert Order team, analyze gateway response times. Medium: page L1, contact gateway support. High: page L2, investigate failover to secondary gateway. |
| 4 | **Sellers get paid on time** | Proportion of scheduled payout jobs completing in batch window | 99.9% over 28d | Low: review batch logs, check bank API status. Medium: page L1, manually retrigger failed payouts, notify finance. High: page L2 + IC, prepare seller comms, arrange manual transfers. |
| 5 | **New sellers can join easily** | Proportion of onboarding flows reaching "approved seller" state | 98% over 28d | Low: review onboarding error logs, check document upload paths. Medium: page L1, proactive outreach to stuck sellers. High: page L2, investigate identity verification provider, open manual review queue. |
| 6 | **Product pages always load** | Proportion of product detail page requests returning 2xx | 99.95% over 28d | Low: alert Catalog team, check DB connection pools + cache hit rates. Medium: page L1, CDN purge, investigate upstream data health. High: page L2 + IC, disable new listing uploads to reduce load. |
| 7 | **Orders ship on schedule** | Proportion of orders entering "shipped" status within SLA window (varies by shipping tier) | 95% within tier SLA over 7d | Low: alert fulfillment ops, review warehouse queue depth. Medium: page logistics L1, notify affected buyers proactively. High: escalate to VP Ops, suspend expedited shipping option. |
| 8 | **Recommendations drive discovery** | Click-through rate on recommendation carousel items | CTR > 12% over 7d rolling | Low: alert ML team, check model staleness / feature drift. Medium: A/B test fallback (popularity-based recs). High: disable personalized recs, fall back to curated collections. |

### Design Notes (Claude Analysis)

**Where Gemini and I align:** The core 6 SLOs (search, checkout, payments, payouts, onboarding, page availability) are solid marketplace fundamentals. The tiered burn-rate response structure (low/medium/high) is the right model.

**Where I'd sharpen things:**

- **SLO #7 (fulfillment) is critical but Gemini omitted it.** A marketplace lives and dies on whether orders actually arrive. This SLO bridges the digital/physical boundary and shows SLOs aren't just about HTTP latency.
- **SLO #8 (recommendations CTR) is deliberately different.** It's a *quality* SLI, not an *availability* SLI. Including it demonstrates that SLOs can measure business outcomes directly (are recommendations actually useful?), not just technical health. This is what makes the "API to the business" concept click.
- **I'd use p95 not p90 for search latency** — p90 is too forgiving for a marketplace where search IS the product. But I'd avoid p99 for a PoC because it's noisier and harder to demo.
- **28-day windows are correct for most SLOs**, but fulfillment and recommendations use 7-day windows because those signals need faster feedback loops.
- **Error budget responses should be concrete, not generic.** "Activate emergency incident response plan" means nothing. "Disable expedited shipping option" or "fall back to curated collections" are real actions someone can take.

---

## 2. Stack Architecture

```
                                        +-----------------+
                                        |   Next.js       |
                                        |   Dashboard     |
                                        | (Alert log,     |
                                        |  SLO status,    |
                                        |  browser notifs)|
                                        +--------+--------+
                                                 |
                                          WebSocket + HTTP
                                                 |
                                        +--------+--------+
                                        |   GraphQL API   |
                                        |  (Strawberry)   |
                                        +--------+--------+
                                                 |
                                        +--------+--------+
                                        |   Django        |
                                        |   Backend       |
                                        | (Models, webhook|
                                        |  receiver,      |
                                        |  enrichment)    |
                                        +--------+--------+
                                           |           |
                              +------------+     +-----+------+
                              |                  |            |
                    +---------+---------+  +-----+------+  +-+----------+
                    |  PostgreSQL       |  | Prometheus  |  | OpenSLO   |
                    |  (business models,|  | (metrics,   |  | (YAML     |
                    |   alert history)  |  |  recording  |  |  defs)    |
                    +-------------------+  |  rules)     |  +-----------+
                                           +------+------+
                                                  |
                                           +------+------+
                                           | Alertmanager|
                                           | (webhook to |
                                           |  Django)    |
                                           +-------------+
```

### Technology Choices

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **Frontend** | Next.js | SSR for initial load, React for interactivity, good WebSocket support |
| **API** | Strawberry (Python GraphQL) | Native Django integration, type-safe, subscriptions via WebSocket. Avoids Apollo Server as a separate Node process. |
| **Backend** | Django | Strong ORM for business models, battle-tested admin for data management, good ecosystem. Already in project spec. |
| **Database** | PostgreSQL | JSONField support for enriched_context, robust, standard |
| **Real-time** | Django Channels + Redis | WebSocket transport for GraphQL subscriptions |
| **Monitoring** | Prometheus + Alertmanager + OpenSLO | Existing project infrastructure |

**Why Strawberry over Apollo:** Keeping the entire backend in Python means one deployment, one test suite, one set of dependencies. Apollo would require a Node.js GraphQL server sitting between Django and Next.js — unnecessary complexity for a demo. Strawberry integrates directly with Django views and Django Channels.

---

## 3. GraphQL Schema Design

### Key Types

```graphql
type BusinessGoal {
  id: ID!
  name: String!
  description: String!
  ownerTeam: Team!
  slos: [SLO!]!
  # Computed: worst status among child SLOs
  overallHealth: SLOStatus!
}

type SLO {
  id: ID!
  name: String!
  description: String!
  service: ServiceName!
  businessGoal: BusinessGoal!

  # Definition (sourced from OpenSLO YAML)
  sliDescription: String!
  target: Float!            # e.g., 0.999
  timeWindowDays: Int!

  # Live status (updated from Prometheus)
  status: SLOStatus!
  errorBudgetRemaining: Float!  # 0.0 - 1.0
  burnRate: BurnRate!

  # Business context (from Django models)
  ownerTeam: Team!
  escalationContacts: [Contact!]!
  errorBudgetPolicy: ErrorBudgetPolicy!

  # History
  recentAlerts(limit: Int = 10): [EnrichedAlert!]!
  budgetHistory(days: Int = 28): [BudgetPoint!]!
}

type ErrorBudgetPolicy {
  lowBurnActions: [String!]!
  mediumBurnActions: [String!]!
  highBurnActions: [String!]!
  businessImpact: String!
  affectedSegments: [String!]!
  revenueImpact: String
}

type EnrichedAlert {
  id: ID!
  slo: SLO!
  severity: AlertSeverity!
  status: AlertStatus!
  summary: String!
  firedAt: DateTime!
  resolvedAt: DateTime

  # Enrichment from Django
  ownerTeam: Team!
  burnRateAtFire: BurnRate!
  businessImpact: String!
  affectedSegments: [String!]!
  revenueImpact: String
  triggeredActions: [String!]!

  # Raw Alertmanager payload for debugging
  rawPayload: JSON
}

enum SLOStatus { OK, WARNING, BREACHED, UNKNOWN }
enum BurnRate { NONE, LOW, MEDIUM, HIGH }
enum AlertSeverity { INFO, WARNING, CRITICAL }
enum AlertStatus { FIRING, RESOLVED, ACKNOWLEDGED }
enum ServiceName { CATALOG, ORDER, SELLER }
```

### Key Queries

```graphql
type Query {
  # Top-level views
  businessGoals: [BusinessGoal!]!
  slos(service: ServiceName, status: SLOStatus): [SLO!]!

  # Detail views
  slo(id: ID!): SLO
  businessGoal(id: ID!): BusinessGoal

  # Alert feed
  alerts(
    sloId: ID
    severity: AlertSeverity
    status: AlertStatus
    limit: Int = 20
    offset: Int = 0
  ): [EnrichedAlert!]!

  # Overview
  systemHealth: SystemHealth!
}

type SystemHealth {
  totalSLOs: Int!
  healthySLOs: Int!
  warningSLOs: Int!
  breachedSLOs: Int!
  activeAlerts: Int!
}
```

### Subscriptions (Real-time)

```graphql
type Subscription {
  # New alert fired or existing alert resolved
  alertUpdate(sloId: ID): EnrichedAlert!

  # SLO status changed (OK -> WARNING, etc.)
  sloStatusChange(service: ServiceName): SLO!
}
```

### Design Notes (Claude Analysis)

**Differences from Gemini's schema:**

- **Flatter structure.** Gemini proposed separate `SLI` and `User` types. For a demo, SLI description belongs on the SLO type directly (it's always 1:1 in practice), and `Contact` is simpler than a full `User` type.
- **`triggeredActions` on EnrichedAlert.** This is the punchline — when an alert fires, you can see exactly what actions were triggered. Gemini had this on the policy but not on the alert instance.
- **`SystemHealth` aggregate query.** The dashboard needs a quick "how are we doing?" without fetching every SLO individually.
- **`overallHealth` on BusinessGoal.** Computed field — worst status among child SLOs. Lets you show "Buyer Retention: BREACHED" at a glance.
- **Dropped mutations.** For the demo, business data is seeded / managed via Django admin. The GraphQL API is read-only + subscriptions. This keeps the demo focused.

---

## 4. Django Model Design

```python
# core/models.py

class Team(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slack_channel = models.CharField(max_length=100, blank=True)

class Contact(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField()
    slack_handle = models.CharField(max_length=50, blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='contacts')

class BusinessGoal(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField()
    owner_team = models.ForeignKey(Team, on_delete=models.PROTECT)

class SLO(models.Model):
    SERVICE_CHOICES = [
        ('CATALOG', 'Catalog Service'),
        ('ORDER', 'Order Service'),
        ('SELLER', 'Seller Service'),
    ]
    STATUS_CHOICES = [
        ('OK', 'OK'), ('WARNING', 'Warning'),
        ('BREACHED', 'Breached'), ('UNKNOWN', 'Unknown'),
    ]
    BURN_RATE_CHOICES = [
        ('NONE', 'None'), ('LOW', 'Low'),
        ('MEDIUM', 'Medium'), ('HIGH', 'High'),
    ]

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField()
    service = models.CharField(max_length=20, choices=SERVICE_CHOICES)
    business_goal = models.ForeignKey(
        BusinessGoal, on_delete=models.PROTECT, related_name='slos'
    )
    owner_team = models.ForeignKey(
        Team, on_delete=models.PROTECT, related_name='owned_slos'
    )
    escalation_contacts = models.ManyToManyField(Contact, blank=True)

    # SLO definition
    sli_description = models.TextField()
    target = models.FloatField()           # 0.999 = 99.9%
    time_window_days = models.IntegerField(default=28)
    openslo_yaml_ref = models.CharField(max_length=255, blank=True)

    # Live status (updated by prometheus poller or webhook handler)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='UNKNOWN')
    error_budget_remaining = models.FloatField(default=1.0)
    burn_rate = models.CharField(max_length=20, choices=BURN_RATE_CHOICES, default='NONE')

class ErrorBudgetPolicy(models.Model):
    slo = models.OneToOneField(SLO, on_delete=models.CASCADE, related_name='policy')

    low_burn_actions = models.JSONField(default=list)
    medium_burn_actions = models.JSONField(default=list)
    high_burn_actions = models.JSONField(default=list)

    business_impact = models.CharField(max_length=500)
    affected_segments = models.JSONField(default=list)  # ["Buyers", "Sellers"]
    revenue_impact = models.CharField(max_length=200, blank=True)

class EnrichedAlert(models.Model):
    STATUS_CHOICES = [
        ('FIRING', 'Firing'), ('RESOLVED', 'Resolved'),
        ('ACKNOWLEDGED', 'Acknowledged'),
    ]
    SEVERITY_CHOICES = [
        ('INFO', 'Info'), ('WARNING', 'Warning'), ('CRITICAL', 'Critical'),
    ]

    external_id = models.CharField(max_length=255, unique=True)
    slo = models.ForeignKey(SLO, on_delete=models.CASCADE, related_name='alerts')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='FIRING')
    summary = models.CharField(max_length=500)
    fired_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Snapshot of enrichment at fire time
    owner_team_name = models.CharField(max_length=200)
    burn_rate_at_fire = models.CharField(max_length=20)
    business_impact = models.CharField(max_length=500)
    affected_segments = models.JSONField(default=list)
    revenue_impact = models.CharField(max_length=200, blank=True)
    triggered_actions = models.JSONField(default=list)

    # Raw alertmanager payload
    raw_payload = models.JSONField(default=dict)

    class Meta:
        ordering = ['-fired_at']
```

### Design Notes (Claude Analysis)

**Key differences from Gemini's models:**

- **`JSONField` for action lists instead of comma-separated text.** Gemini proposed `TextField` with comma-separated values — that's fragile to parse and awkward to render. `JSONField` with `default=list` is clean and native to both Django and GraphQL.
- **Snapshot fields on `EnrichedAlert`.** The alert captures `owner_team_name`, `business_impact`, `triggered_actions` etc. as snapshots at fire time, not as foreign keys. This is deliberate — if the policy changes after an alert fires, the historical record should reflect what the policy *was*, not what it became.
- **Simpler `Contact` model instead of full `User`.** We don't need Django auth users for this. Contacts are just names/emails/slack handles for escalation.
- **No `SLOErrorBudgetHistory` model.** Gemini proposed this, but Prometheus already stores this data as time-series. Duplicating it in PostgreSQL adds complexity without value for a demo. Query Prometheus directly for budget history graphs.
- **`models.PROTECT` on business-critical FKs.** Don't let someone accidentally delete a team and cascade-delete all its SLOs.

---

## 5. Enriched Alert Flow

### Sequence

```
1. Prometheus evaluates alerting rules (generated from OpenSLO)
   Alert fires: slo_name="checkout-success-rate", burn_rate="high"
       |
       v
2. Alertmanager receives, groups, routes
   Sends webhook POST to Django: /webhooks/alertmanager/
       |
       v
3. Django webhook view:
   a. Parse Alertmanager JSON payload
   b. Extract slo_name label -> lookup SLO model
   c. Load ErrorBudgetPolicy for that SLO
   d. Determine triggered actions based on burn rate
   e. Create EnrichedAlert record with:
      - Business context (impact, segments, revenue)
      - Ownership (team, escalation contacts)
      - Triggered actions (concrete list of what to do)
      - Raw payload (for debugging)
   f. Update SLO.status and SLO.burn_rate
       |
       v
4. Django signals -> Django Channels
   Publish to Redis channel: "alerts.new"
   Payload: serialized EnrichedAlert
       |
       v
5. Strawberry GraphQL subscription resolver
   Picks up message from Redis
   Pushes to all WebSocket subscribers of `alertUpdate`
       |
       v
6. Next.js dashboard (client):
   a. Receives subscription payload via WebSocket
   b. Adds alert to live feed with full business context
   c. Updates SLO status cards
   d. If severity=CRITICAL: fires browser notification
      Title: "SLO Breach: Checkout Success Rate"
      Body: "High burn rate - $50k/hr revenue impact. Order team paged."
```

### What Gets Enriched at Each Stage

| Stage | Raw Data | Enrichment Added |
|-------|----------|-----------------|
| **Prometheus** | Metric values, threshold breach | Alert labels: `slo_name`, `service`, computed `burn_rate` |
| **Alertmanager** | Grouped/deduplicated alert | Routing labels, `severity`, `summary` annotation |
| **Django** | Alertmanager JSON payload | Team ownership, escalation contacts, business impact, revenue estimate, affected segments, concrete triggered actions, link to business goal |
| **GraphQL** | Flat enriched record | Resolved relationships (team -> contacts, SLO -> business goal), computed fields (`overallHealth`) |
| **Next.js** | Structured GraphQL payload | Visual presentation, browser notification, link to SLO detail view |

### The "Aha Moment"

The enriched alert that arrives in the browser notification doesn't say:

> "ALERT: http_request_duration_seconds bucket exceeds threshold"

It says:

> "Checkout Success Rate breached (high burn). Buyers can't complete purchases. ~$50k/hr revenue impact. Order team paged. Actions: disable affected payment methods, notify customer support."

**That's the difference between a monitoring system and an API to the business.**

---

## 6. What Makes This Compelling

### Must-haves for the demo (things that make the thesis tangible)

1. **Business Goal → SLO tree view.** The dashboard opens with business goals, each showing its child SLOs with live status. An executive can see "Buyer Trust" is amber because checkout success rate is burning budget. No Prometheus knowledge required.

2. **Enriched alert feed with business context.** Every alert shows: what business promise is breaking, who's affected, what it costs, who's responsible, and what actions to take. Side-by-side with the raw Alertmanager payload to show the enrichment delta.

3. **Error budget burn-down per SLO.** A simple chart showing budget consumption over the window. When it crosses a threshold line, the corresponding actions light up. Visual proof that the response policy is wired to the measurement.

4. **Browser notifications with business language.** When a critical alert fires, the browser notification speaks business, not Prometheus. This is the most visceral demo moment.

5. **Live exerciser toggle.** A button in the dashboard (or CLI command) that triggers the exerciser to degrade a specific service. Watch the SLO status change, the alert fire, the enrichment happen, the notification pop. End-to-end in real-time.

### Nice-to-haves (strengthen the thesis but not required for PoC)

6. **Diff view: raw vs. enriched alert.** Show the Alertmanager payload side-by-side with the enriched alert. Visually demonstrates the value of the enrichment layer.

7. **"Who to call" panel.** When an SLO breaches, show the escalation chain with actual contact methods (Slack handle, etc.). Makes ownership concrete.

8. **Historical correlation.** "Last time this SLO breached was 3 days ago, triggered by deployment X." Links alert history to deployment events.

### What to explicitly NOT build (keep the demo focused)

- No automated remediation (scaling, restarts). The demo is about visibility and communication, not automation.
- No auth/login. Single-user dashboard.
- No multi-tenant. One marketplace, one view.
- No Grafana integration. The Next.js dashboard IS the visualization layer. Grafana would dilute the message.

---

## 7. Implementation Sequence (Suggested)

For a PoC, build in this order to get to a demo-able state fastest:

1. **Django models + seed data** — Define the models, create fixtures for Meridian Marketplace's teams, business goals, SLOs, and policies. Use Django admin to verify.

2. **Alertmanager webhook receiver** — Accept Alertmanager payloads, look up SLO, create EnrichedAlert. Test with curl / manual webhook payloads first.

3. **GraphQL API (read-only)** — Expose the seeded data and alert history via Strawberry. Verify with GraphiQL.

4. **Next.js dashboard (static first)** — Render business goals, SLO status, alert feed from GraphQL queries. No real-time yet.

5. **Real-time subscriptions** — Add Django Channels + Redis, wire up Strawberry subscriptions, add WebSocket client to Next.js.

6. **Browser notifications** — Request permission, fire notifications on critical alert subscription events.

7. **Exerciser integration** — Wire up the existing exerciser (TASK-4) to trigger real SLO breaches, watch the full flow end-to-end.

---

## 8. Relationship to Existing Tasks

This example app builds on top of the existing PoC tasks:

| Existing Task | Relationship |
|--------------|-------------|
| TASK-1: Deployment Pipeline (Kind + Podman) | Meridian services deploy here |
| TASK-2: Monitoring Infrastructure (Prometheus + Alertmanager) | Provides the monitoring backbone |
| TASK-3: AI Agent Webhook | The Django webhook receiver IS an evolution of this — same concept, richer implementation |
| TASK-4: Example Service + Exerciser + OpenSLO | The example services become Meridian's Catalog/Order/Seller services; exerciser drives the demo |

The rich example app is the **integration layer** that ties tasks 1-4 together and adds the business context that makes SLOs meaningful.

---

## Appendix: Gemini's Full Analysis

The analysis above incorporates and builds on Gemini's research (obtained via `gemini -p`). Key areas where this document diverges from Gemini's proposals:

1. **Added SLOs #7 (fulfillment) and #8 (recommendations CTR)** — These demonstrate that SLOs extend beyond HTTP availability into physical operations and ML quality. Gemini stayed within the standard availability/latency pattern.

2. **Chose Strawberry over Apollo** — Gemini suggested Apollo or Strawberry as equivalent options. I strongly prefer Strawberry to keep the entire backend in Python and avoid a separate Node.js process.

3. **Used JSONField instead of comma-separated text** — Gemini's Django models used `TextField` with comma-separated values for action lists. JSONField is cleaner.

4. **Dropped SLOErrorBudgetHistory model** — Prometheus already stores this data. Duplicating it in PostgreSQL is unnecessary complexity for a demo.

5. **Added snapshot fields on EnrichedAlert** — Rather than foreign keys to current policy state, the alert captures what the policy was at fire time. Historical accuracy matters.

6. **Explicitly scoped what NOT to build** — Gemini suggested "What If" scenario modeling as a bonus feature. For a PoC focused on proving the thesis, this is scope creep. Better to nail the core flow first.

7. **Error budget responses are concrete, not generic** — Gemini's responses included phrases like "activate emergency incident response plan." The whole point of this project is that responses should be specific and actionable: "disable affected payment methods," "fall back to curated collections."
