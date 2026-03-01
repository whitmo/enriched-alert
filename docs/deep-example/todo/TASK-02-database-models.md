# TASK-02: Database Models

## Objective
Define Django ORM models for the Meridian Marketplace domain, run migrations, and load seed data that represents a realistic e-commerce marketplace scenario.

## Components
- Django models: `BusinessGoal`, `SLODefinition`, `OperationalResponse`, `EnrichedAlert`, `Service`, `Team`
- Database migrations
- Fixture files with Meridian Marketplace seed data
- Admin site registration for all models

## Steps
1. Create a Django app (e.g., `core`) inside `django-api/`.
2. Define `Team` model — name, slug, escalation contact, on-call rotation URL.
3. Define `Service` model — name, slug, description, owning team (FK to Team), repository URL, tier (critical/standard/best-effort).
4. Define `BusinessGoal` model — title, description, impact description, revenue impact estimate, priority (P0-P3), linked services (M2M).
5. Define `SLODefinition` model — name, description, service (FK), sli metric name, target percentage, window (e.g., "30d"), openslo reference path, linked business goals (M2M).
6. Define `OperationalResponse` model — slo definition (FK), severity level, recommended actions (JSONField), escalation path, runbook URL.
7. Define `EnrichedAlert` model — title, raw alert JSON, service (FK), slo definition (FK), severity, status (firing/acknowledged/resolved), business context summary, recommended actions, created at, acknowledged at, resolved at.
8. Run `python manage.py makemigrations` and `python manage.py migrate`.
9. Create fixture JSON/YAML for Meridian Marketplace seed data:
   - Teams: platform, payments, search, seller-experience
   - Services: catalog-service, order-service, payment-service, seller-portal, search-service
   - Business goals: "Holiday revenue target", "Seller onboarding velocity", "Payment processing reliability", "Search conversion rate"
   - SLO definitions: 8 SLOs covering latency, error rate, and availability across services
   - Operational responses for each SLO at warning and critical severity
10. Load seed data with `python manage.py loaddata`.
11. Register all models in Django admin.

## Acceptance Criteria
- [ ] All six models exist with appropriate fields, relationships, and constraints
- [ ] Migrations run cleanly on a fresh database
- [ ] `python manage.py loaddata` populates all tables with Meridian Marketplace data
- [ ] Django admin shows all models and seed data is browsable
- [ ] Foreign key and M2M relationships are navigable in admin
- [ ] Model `__str__` methods return readable representations

## Dependencies
- TASK-01 (project scaffolding — Django project must exist)

## Estimated Complexity
Medium
