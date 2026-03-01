# Talos Linux for SLO-Enriched Alert System

## Abstract

Talos Linux is an immutable, API-driven, minimal Linux distribution purpose-built for Kubernetes. It eliminates SSH, shell access, and package managers in favor of a declarative, `talosctl`-driven operational model. For our SLO-enriched alert PoC (Prometheus + Alertmanager + OpenSLO + AI webhook + example service), Talos would work with minimal changes to the Kubernetes-layer deployment but fundamentally changes how you operate, debug, and develop locally. **Headline finding: our Helm-based monitoring stack deploys nearly identically on Talos, but the no-SSH/no-shell constraint requires rethinking debugging workflows and image delivery.**

## What is Talos?

Talos Linux is a secure, immutable operating system designed exclusively for running Kubernetes. Key properties:

- **Immutable**: The root filesystem is read-only. No modifications survive reboots except through machine configs.
- **API-driven**: All management goes through `talosctl` and the Talos API. No SSH, no shell, no `systemctl`.
- **Minimal**: ~50MB compressed. No package manager, no userland tools, no bash. Just `containerd`, `kubelet`, and the Talos machinery.
- **Secure by default**: Mutual TLS for all API communication, minimal attack surface, CIS-benchmarked.
- **Declarative**: Machine configuration is a YAML document applied atomically. Changes are `talosctl apply-config`.

Built by [Sidero Labs](https://www.siderolabs.com/). Current stable: v1.11.x.

## Boilerplate Setup

### Install talosctl

```bash
# macOS
brew install siderolabs/tap/talosctl

# Linux
curl -sL https://talos.dev/install | sh
```

### Create a Local Cluster (Docker Provider)

The Docker provider is the fastest way to get a local Talos cluster. It runs Talos nodes as Docker containers.

```bash
# Create a single-node cluster (default: 1 controlplane, 1 worker)
talosctl cluster create

# macOS Docker Desktop: if you get a socket error, link the socket first
sudo ln -s "$HOME/.docker/run/docker.sock" /var/run/docker.sock

# Larger cluster (resource-intensive)
talosctl cluster create --controlplanes 3 --workers 2
```

This automatically:
1. Generates machine configs (controlplane + worker)
2. Creates Docker containers running Talos
3. Bootstraps etcd
4. Starts the Kubernetes control plane
5. Sets up `talosconfig` and `kubeconfig`

### Verify and Access

```bash
# Dashboard (live view of node status)
talosctl dashboard --nodes 10.5.0.2

# Get kubeconfig (auto-merged into ~/.kube/config)
talosctl kubeconfig

# Verify
kubectl get nodes -o wide
```

### Teardown

```bash
talosctl cluster destroy
```

### Production Setup (Non-Docker)

For bare metal or cloud, the flow is:
```bash
# 1. Generate configs
talosctl gen config my-cluster https://<controlplane-vip>:6443

# 2. Apply to machines (over network)
talosctl apply-config --insecure --nodes <ip> --file controlplane.yaml

# 3. Bootstrap etcd on first controlplane
talosctl bootstrap --nodes <first-cp-ip>

# 4. Get kubeconfig
talosctl kubeconfig --nodes <cp-ip>
```

## Deploying Our Stack on Talos

### What Stays the Same

Almost everything at the Kubernetes layer is unchanged:

```bash
# Helm works identically
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f values.yaml
```

- **PrometheusRule CRDs**: Work exactly the same. OpenSLO-generated rules apply identically.
- **ServiceMonitors / PodMonitors**: Unchanged. Prometheus Operator discovers them the same way.
- **Alertmanager webhook config**: Unchanged. Kubernetes Services route to our AI agent webhook.
- **Grafana**: Deploys the same way.

### What Changes

#### 1. Storage for Prometheus/Alertmanager

Kind uses ephemeral storage by default. Talos needs explicit storage configuration:

- **local-path-provisioner** (recommended for PoC/dev): Officially recommended by Talos docs. Needs a kustomize patch to use `/var/mnt/local-path-provisioner` path.
- **Longhorn**: For multi-node replicated storage. Requires Talos system extensions for iSCSI support and a privileged namespace label.
- **Rook-Ceph**: For production-grade distributed storage. Heavier.

For our PoC, local-path-provisioner is sufficient.

#### 2. Control Plane Metrics Scraping

Talos runs etcd, kube-controller-manager, and kube-scheduler differently than standard distros. To scrape them:

- Patch machine config to expose metrics endpoints:
  ```yaml
  cluster:
    etcd:
      extraArgs:
        listen-metrics-urls: http://0.0.0.0:2381
    controllerManager:
      extraArgs:
        bind-address: 0.0.0.0
    scheduler:
      extraArgs:
        bind-address: 0.0.0.0
  ```
- The kube-prometheus-stack service selectors may need adjustment since control plane components run in host network mode on Talos, not as regular pods.

#### 3. Custom Image Delivery (AI Webhook, Example Service)

No `docker` or `podman` on Talos nodes. No `kind load docker-image`. Options:

| Method | Best For |
|--------|----------|
| **Container registry** (DockerHub, ghcr.io, private) | Production, CI/CD |
| **`talosctl image import`** | Local dev, one-off testing |
| **Local registry mirror** | Faster local iteration |

For local dev with the Docker provider:
```bash
# Build locally
docker build -t my-webhook:dev .

# Option A: Push to a registry the cluster can reach
docker tag my-webhook:dev localhost:5000/my-webhook:dev
docker push localhost:5000/my-webhook:dev

# Option B: Import directly into a node
talosctl image import my-webhook:dev --nodes 10.5.0.2
```

**This is the biggest workflow change from Kind**, where `kind load docker-image` just works.

#### 4. Node Exporter Considerations

The `kube-prometheus-stack` deploys node-exporter as a DaemonSet. On Talos, node-exporter may need host path adjustments since Talos's filesystem layout differs from standard Linux. The `/proc` and `/sys` mounts are available but some paths vary. Test and adjust the node-exporter DaemonSet's volume mounts if metrics are missing.

## Instrumenting Services

### No Differences for Application-Level Metrics

For our example Go/Python service with Prometheus metrics endpoints:

- **Prometheus scraping via ServiceMonitor**: Identical. Prometheus discovers services by label selectors; the underlying OS is irrelevant.
- **PodMonitor**: Identical.
- **Annotations-based scraping**: Identical (`prometheus.io/scrape: "true"`, etc.).
- **Metric exposition**: Your `/metrics` endpoint works the same. The Go `prometheus/client_golang` or Python `prometheus_client` libraries are application-level — they don't care about the host OS.

### One Caveat: Host-Level Metrics

If your SLOs reference node-level metrics (CPU, memory, disk from node-exporter), verify those metrics are being collected correctly on Talos. Container and pod metrics from cAdvisor/kubelet are fine.

## Caveats

### No SSH, No Shell, No Package Manager

This is the defining characteristic and the biggest culture shock:

| Need | Kind/kubeadm | Talos |
|------|-------------|-------|
| Check a file on the node | `docker exec` / `ssh` | `talosctl read /path/to/file` |
| View system logs | `ssh` + `journalctl` | `talosctl logs <service>` |
| View pod logs | `kubectl logs` | `kubectl logs` (same) |
| Debug networking | `ssh` + `tcpdump` | `talosctl pcap` or `kubectl debug` with ephemeral container |
| Install a debug tool | `apt install` | Not possible. Use `kubectl debug` with a debug image |
| Restart a service | `systemctl restart` | `talosctl service restart <svc>` |
| Check disk usage | `ssh` + `df` | `talosctl usage /var` |
| Edit config files | `ssh` + `vim` | `talosctl edit machineconfig` or `talosctl apply-config` |

### What This Means Practically

1. **No ad-hoc debugging on nodes**: You can't install `curl`, `dig`, `strace`, etc. on a Talos node. Instead, use `kubectl debug` with an ephemeral container that has those tools:
   ```bash
   kubectl debug node/<node-name> -it --image=alpine
   ```

2. **No config file editing**: Everything is in the machine config YAML, applied atomically. No tweaking `/etc/prometheus/` or similar.

3. **Logs are API-only**: `talosctl logs kubelet`, `talosctl logs etcd`, etc. There's no `/var/log` to browse.

4. **Upgrades are atomic**: `talosctl upgrade` replaces the entire OS image. No `apt upgrade` drift.

5. **Extensions for host-level tools**: Need `iscsi` for Longhorn? Need a specific kernel module? These go through [Talos system extensions](https://github.com/siderolabs/extensions), not package installs.

### What Doesn't Break

- All Kubernetes-layer operations (kubectl, Helm, Kustomize) work identically
- Container networking (CNI) works normally
- Ingress controllers, cert-manager, etc. deploy the same way
- CI/CD pipelines that target `kubectl apply` are unaffected

## Tradeoffs

| Dimension | Talos | Kind | k3s | kubeadm |
|-----------|-------|------|-----|---------|
| **Setup complexity** | Low (single command for local) | Very low | Low | Medium-High |
| **Security posture** | Excellent (immutable, minimal, mTLS) | Minimal (dev only) | Good | Depends on hardening |
| **Production readiness** | Yes (designed for it) | No (dev/CI only) | Yes (lightweight prod) | Yes (reference implementation) |
| **Local dev speed** | Good (Docker provider, ~2-3 min) | Excellent (~30-60s) | Good (~1-2 min) | Poor (VM-based) |
| **Resource usage** | Medium (real kubelet per node) | Low (containers) | Low (single binary) | High (full VMs typically) |
| **Debugging ease** | Hard (API-only, learning curve) | Easy (docker exec) | Easy (SSH + standard tools) | Easy (SSH + standard tools) |
| **Learning curve** | Medium (new mental model) | Very low | Low | Medium |
| **Image loading** | Registry or `talosctl image import` | `kind load docker-image` | `ctr images import` or registry | Registry |
| **Upgrades** | Atomic OS replacement | Recreate cluster | Binary replacement | `kubeadm upgrade` |
| **Multi-node local** | Yes (Docker containers) | Yes (Docker containers) | Yes (VMs or containers) | Yes (VMs) |
| **Our PoC fit** | Overkill but educational | Best fit for PoC | Good alternative | Overkill |

## Recommendations for This PoC

### Don't Switch Yet

For a PoC focused on proving out the SLO alerting pipeline (Prometheus -> OpenSLO rules -> Alertmanager -> AI webhook), **Kind + Podman remains the right choice**:

1. **Faster iteration**: `kind load docker-image` vs registry/import workflow
2. **Simpler debugging**: `docker exec` into nodes when things go wrong
3. **Lower cognitive load**: Focus on the alerting pipeline, not the OS
4. **The monitoring stack is identical**: kube-prometheus-stack deploys the same way

### When Talos Makes Sense

Consider Talos when:
- Moving toward production deployment
- Security posture matters (immutable, minimal attack surface)
- You want infrastructure-as-code for the OS layer too
- You need to demonstrate the PoC on a production-like platform

### Migration Path

The migration from Kind to Talos would be straightforward:
1. `talosctl cluster create` instead of `kind create cluster`
2. Same Helm charts, same values (plus storage config)
3. Push images to a registry instead of `kind load`
4. Add machine config patches for control plane metrics
5. Everything else stays the same

## Gemini's Perspective

*Analysis from Gemini CLI (via `gemini -p`):*

Gemini emphasized Talos's **security-first design** as the primary differentiator and recommended it for production deployments where consistency and security are paramount. Key points from Gemini's analysis:

- The `kube-prometheus-stack` Helm chart generally "just works" on Talos, with caveats around node-exporter host path mounts and control plane metrics endpoints
- Custom images must go through a registry since there's no Docker/Podman on nodes; `talosctl image import` is available for dev workflows
- The immutable model forces a "more Kubernetes-native and API-driven operational model, emphasizing declarative configuration and automated remediation over manual intervention"
- Gemini rated the local dev experience as "high" with the Docker provider, comparable to Kind
- Recommended proceeding with Talos for production while using the Docker provider for consistent local development

*My additions to Gemini's analysis:*

- Gemini underestimated the **control plane metrics gotchas** — you need explicit machine config patches for etcd/scheduler/controller-manager metrics, and service selectors in kube-prometheus-stack may need adjustment since Talos runs these in host network mode
- Gemini's mention of `talosctl upload image` appears to be for an older version; current docs reference `talosctl image import`
- The **storage story** is more nuanced than Gemini suggested — local-path-provisioner needs a kustomize patch for Talos's filesystem layout, and Longhorn requires system extensions for iSCSI
- For our PoC specifically, Gemini's recommendation to "proceed with Talos" is premature — Kind is the right tool for proving the alerting pipeline; Talos is the right tool for hardening it later

## Sources

- [Talos Linux Official Site](https://www.talos.dev/)
- [Talos Quickstart Guide](https://docs.siderolabs.com/talos/v1.11/getting-started/quickstart)
- [Talos Local Storage Guide](https://www.talos.dev/v1.10/kubernetes-guides/configuration/local-storage/)
- [Installing Longhorn on Talos](https://joshrnoll.com/installing-longhorn-on-talos-with-helm/)
- [Talos etcd Metrics Discussion](https://github.com/siderolabs/talos/discussions/7214)
- [How to SSH into Talos Linux (You Can't)](https://www.siderolabs.com/blog/how-to-ssh-into-talos-linux/)
- [Talos Debug Container Issue](https://github.com/siderolabs/talos/issues/8720)
- [Easiest Kubernetes on a Mac (Sidero Labs)](https://www.siderolabs.com/blog/easiest-kubernetes-on-a-mac/)
- [No SSH? What Is Talos? (The New Stack)](https://thenewstack.io/no-ssh-what-is-talos-this-linux-distro-for-kubernetes/)
- [Talos local-path-provisioner Issue](https://github.com/siderolabs/talos/issues/11251)
