# CI/CD Pipeline — Test Pyramid

The CI/CD pipeline is structured as a test pyramid: many fast checks at the base, fewer slow checks at the top. Each layer gates the next — failures block promotion.

## Pipeline Triggers

| Trigger | Stages Run |
|---------|-----------|
| Push to any branch / PR opened | Smoke Tests, Unit Tests |
| PR merged to `main` | Integration Tests |

## Test Pyramid

```mermaid
graph TB
    subgraph trigger_push ["Push / PR Opened"]
        direction TB
    end

    subgraph trigger_main ["PR to main"]
        direction TB
    end

    trigger_push --> smoke["Smoke Tests<br/><i>ruff, yamllint, hadolint, syntax check</i><br/>⏱ &lt;1 min"]
    trigger_push --> unit["Unit Tests<br/><i>pytest + coverage per service via uv</i><br/>⏱ ~2-5 min"]
    smoke --> gate1{Pass?}
    unit --> gate1
    trigger_main --> gate1
    gate1 -->|Yes| integration["Integration Tests<br/><i>Kind cluster · full stack deploy<br/>exerciser breach mode · Prometheus scraping<br/>alerts firing · AI agent receiving</i><br/>⏱ ~10-15 min"]
    gate1 -->|No| fail["❌ Pipeline Fails"]

    style smoke fill:#4caf50,color:#fff
    style unit fill:#2196f3,color:#fff
    style integration fill:#ff9800,color:#fff
    style fail fill:#f44336,color:#fff
    style gate1 fill:#fff,stroke:#333
```

## Pyramid View

```mermaid
block-beta
    columns 1
    block:top:1
        integration["Integration Tests (few, slow)"]
    end
    block:mid:1
        unit["Unit Tests (moderate)"]
    end
    block:base:1
        smoke["Smoke Tests (many, fast)"]
    end

    style integration fill:#ff9800,color:#fff
    style unit fill:#2196f3,color:#fff
    style smoke fill:#4caf50,color:#fff
```

## Stage Details

### Smoke Tests — Base of the Pyramid

Runs on every push and PR. Fast linters and syntax validators that catch obvious mistakes before anything else runs.

| Check | Tool | What it catches |
|-------|------|----------------|
| Python lint | `ruff` | Style violations, unused imports, basic errors |
| YAML lint | `yamllint` | Malformed Kubernetes manifests, OpenSLO defs |
| Dockerfile lint | `hadolint` | Dockerfile anti-patterns, pinning issues |
| Syntax check | `python -m py_compile` | Import errors, syntax errors |

**Target:** <1 minute total.

### Unit Tests — Middle of the Pyramid

Runs on every push and PR, in parallel with smoke tests. Per-service `pytest` suites executed via `uv` with coverage enforcement.

| Aspect | Detail |
|--------|--------|
| Runner | `uv run pytest` per service |
| Coverage | `pytest-cov`, enforced per service |
| Threshold | **80% line coverage minimum** |
| Services | `ai-agent`, `example-service`, `exerciser` |
| Isolation | Each service tested independently with mocked dependencies |

**Target:** ~2-5 minutes.

### Integration Tests — Top of the Pyramid

Runs only when a PR targets `main`. Spins up a real Kind cluster, deploys the full stack, and exercises the end-to-end alert pipeline.

| Step | What happens |
|------|-------------|
| 1. Cluster up | Kind cluster created with Podman runtime |
| 2. Deploy monitoring | Prometheus + Alertmanager via kube-prometheus-stack Helm chart |
| 3. Deploy services | Example service + AI agent loaded and deployed |
| 4. Exerciser breach mode | Exerciser script induces latency/error SLO breaches |
| 5. Verify Prometheus scraping | Assert metrics are being collected from example service |
| 6. Verify alerts firing | Assert Alertmanager has received SLO breach alerts |
| 7. Verify AI agent receiving | Assert AI agent webhook received and logged alert + OpenSLO context |
| 8. Teardown | Kind cluster deleted |

**Target:** ~10-15 minutes.

## Notes

- Smoke and unit tests run **in parallel** on push/PR to minimize wall-clock time.
- Integration tests are expensive (Kind cluster lifecycle) so they only run on PR-to-main.
- The 80% coverage threshold is per-service, not aggregate — no service can hide behind another's coverage.
- `uv` is used as the Python package/task runner for reproducible, fast dependency resolution.
- Integration test failures should produce artifacts (pod logs, Prometheus snapshots) for debugging.
- The exerciser's "breach mode" is the same script used in TASK-4, run with flags that deterministically trigger SLO violations.
