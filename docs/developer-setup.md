# Developer Setup

Everything a new developer needs to get the enriched-alert PoC running locally.

## Prerequisites

| Tool | Purpose | Install (macOS) |
|------|---------|-----------------|
| [Podman](https://podman.io/) | Container runtime (used instead of Docker) | `brew install podman` |
| [Kind](https://kind.sigs.k8s.io/) | Local Kubernetes clusters | `brew install kind` |
| [kubectl](https://kubernetes.io/docs/tasks/tools/) | Kubernetes CLI | `brew install kubectl` |
| [Helm](https://helm.sh/) | Kubernetes package manager | `brew install helm` |
| [uv](https://docs.astral.sh/uv/) | Python package/project manager | `brew install uv` |
| Python 3.12 | AI agent and example service runtime | `uv python install 3.12` |

After installing Podman, initialize and start the machine:

```bash
podman machine init
podman machine start
```

Verify everything is available:

```bash
podman --version
kind --version
kubectl version --client
helm version
uv --version
python3.12 --version
```

> **Note:** The Makefile defaults to `podman` as the container runtime (`KIND_RUNTIME := podman`). No Docker installation is needed.

## Quick Start

```bash
git clone <repo-url> && cd enriched-alert
make all
```

That single `make all` command will:
1. Create a Kind cluster (`podman-poc-cluster`) using Podman
2. Deploy Prometheus + Alertmanager via Helm
3. Build and deploy the AI agent
4. Build and deploy the example service

To tear everything down:

```bash
make clean
```

## Project Structure

```
.
├── Makefile                  # All build/deploy targets
├── ai-agent/                 # Python webhook receiver (FastAPI)
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── app.py
├── example-service/          # Python HTTP service with Prometheus metrics
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── app.py
├── kubernetes/               # K8s deployment manifests
│   ├── agent-deployment.yaml
│   └── service-deployment.yaml
├── openslo/                  # OpenSLO definition YAML files
└── docs/
    ├── developer-setup.md    # This file
    └── todo/                 # Task specs (TASK-1 through TASK-4)
```

## Development Workflows

### Running services locally (outside cluster)

**Example service:**
```bash
cd example-service
uv run uvicorn app:app --port 8081
```

**AI agent:**
```bash
cd ai-agent
uv run uvicorn app:app --port 8080
```

### Running tests

```bash
cd ai-agent && uv run pytest
cd example-service && uv run pytest
```

### Running in the Kind cluster

**1. Create the cluster:**
```bash
make kind-up
```

**2. Deploy monitoring (Prometheus + Alertmanager):**
```bash
make monitoring-up
```

**3. Build and deploy services:**
```bash
make agent-deploy    # builds image, loads into Kind, applies manifests
make service-deploy  # builds image, loads into Kind, applies manifests
```

**4. Access services via port-forward:**
```bash
# Prometheus UI
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
# Open http://localhost:9090

# Alertmanager UI
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-alertmanager 9093:9093
# Open http://localhost:9093

# Grafana
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
# Open http://localhost:3000 (default: admin/prom-operator)

# AI Agent
kubectl port-forward svc/ai-agent 8080:8080

# Example Service
kubectl port-forward svc/example-service 8081:8081
```

### Triggering SLO breaches

The exerciser script sends traffic patterns that deterministically breach SLOs:

```bash
# Normal traffic — keeps SLOs healthy
make exercise-normal

# Breach traffic — induces latency/errors to trigger alerts
make exercise-breach
```

Watch the AI agent respond to alerts:
```bash
kubectl logs -l app=ai-agent -f
```

Watch Alertmanager fire:
```bash
kubectl logs -l app=alertmanager -n monitoring -f
```

## Namespace-Isolated Testing

Run multiple independent test environments in parallel using the `TEST_NS` variable:

```bash
# Deploy to a custom namespace
make deploy TEST_NS=my-test

# Run a second environment in parallel
make deploy TEST_NS=experiment-2

# Tear down a specific namespace
make undeploy TEST_NS=my-test
```

Each namespace gets its own copy of the agent and example service, isolated from others.

## Troubleshooting

### Podman not running

```bash
podman machine list            # check machine status
podman machine start           # start if stopped
podman system connection list  # verify connection
```

### Kind cluster won't start

```bash
# Check if cluster already exists
kind get clusters

# Delete stale cluster and recreate
make clean && make kind-up

# Verify podman socket is accessible
podman info
```

### Images not loading into Kind

```bash
# Verify image exists locally
podman images | grep ai-agent

# Manually load
KIND_CONTAINER_RUNTIME=podman kind load docker-image ai-agent:latest --name podman-poc-cluster
```

### Pods not starting

```bash
kubectl get pods -A                          # overview of all pods
kubectl describe pod <pod-name>              # events and scheduling info
kubectl logs <pod-name>                      # application logs
kubectl logs <pod-name> --previous           # logs from crashed container
```

### Helm deployment issues

```bash
helm list -n monitoring                      # check release status
helm status prometheus -n monitoring         # detailed release info
kubectl get pods -n monitoring               # pod health
```

### Common checks

```bash
# Cluster health
kubectl get nodes
kubectl cluster-info

# All resources in default namespace
kubectl get all

# All resources in monitoring namespace
kubectl get all -n monitoring
```

## CI/CD

- **PR opened:** runs smoke tests + unit tests
- **PR merged to main:** runs integration tests (full Kind cluster deploy + exerciser)
- **Coverage threshold:** 80% minimum

## Makefile Targets Reference

Run `make help` to see all targets. Key ones:

| Target | Description |
|--------|-------------|
| `make all` | Build and deploy everything |
| `make clean` | Delete Kind cluster and all deployments |
| `make kind-up` | Create Kind cluster with Podman |
| `make kind-down` | Delete Kind cluster |
| `make monitoring-up` | Deploy Prometheus + Alertmanager via Helm |
| `make agent-build` | Build AI agent container image |
| `make agent-deploy` | Build, load, and deploy AI agent |
| `make service-build` | Build example service container image |
| `make service-deploy` | Build, load, and deploy example service |
