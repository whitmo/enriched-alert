# Parallel Testing with Namespace Isolation

Multiple test runs coexist in a single Kind cluster via separate namespaces. Each `TEST_NS` gets its own application namespace and a derived `<TEST_NS>-monitoring` namespace. Cleanup is `kubectl delete namespace`.

## Setup (once)

```bash
make kind-up    # Create the Kind cluster
make images     # Build and load all container images
```

## Run parallel tests

Each worker sets a unique `TEST_NS`:

```bash
# Worker A
make deploy TEST_NS=test-alpha

# Worker B (in parallel)
make deploy TEST_NS=test-beta
```

This deploys the full stack (monitoring, agent, service, SLOs, rules) into isolated namespaces:

| TEST_NS      | App namespace | Monitoring namespace     |
|--------------|---------------|--------------------------|
| test-alpha   | test-alpha    | test-alpha-monitoring    |
| test-beta    | test-beta     | test-beta-monitoring     |

## Exercise traffic

```bash
make exercise-normal TEST_NS=test-alpha
make exercise-breach TEST_NS=test-beta
```

## Cleanup

Delete a single test environment:

```bash
make undeploy TEST_NS=test-alpha
```

This deletes both the `test-alpha` and `test-alpha-monitoring` namespaces.

Tear down everything:

```bash
make kind-down
```

## Default behavior

Running `make all` with no arguments uses `TEST_NS=default`, which behaves like the original single-namespace setup.

## How it works

- **Helm release names** include `TEST_NS` (e.g., `prometheus-test-alpha`) so multiple monitoring stacks don't collide.
- **Alertmanager webhook URL** uses the `DEPLOY_NAMESPACE` placeholder in `kubernetes/helm-values/alertmanager-values.yaml.tpl`. The Makefile substitutes the actual `TEST_NS` value via `sed` before passing to Helm.
- **Namespace-level targets** (`deploy`, `undeploy`, `monitoring-up`, `agent-deploy`, `service-deploy`, `openslo-deploy`, `rules-deploy`, `exercise-normal`, `exercise-breach`) all pass `-n $(TEST_NS)` or `-n $(MONITORING_NS)` to kubectl/helm.
- **Cluster-level targets** (`kind-up`, `kind-down`, `images`) are shared and only need to run once.
