# TASK-08: Kubernetes Deployment

## Objective
Create production-style Kubernetes manifests for all Meridian Marketplace services, with Helm chart or Kustomize overlays for environment variation, and ensure the docker-compose local dev path remains functional.

## Components
- Kubernetes Deployment, Service, and ConfigMap manifests for: django-api, fastapi-agent, next-app, catalog-service, order-service, seller-service
- Prometheus and Alertmanager deployment (via kube-prometheus-stack Helm chart)
- PostgreSQL StatefulSet or Helm chart
- Helm chart or Kustomize overlays for dev/staging configuration
- Namespace isolation (e.g., `meridian-apps`, `meridian-monitoring`)
- Docker-compose for local dev without K8s

## Steps
1. Create `k8s/` directory with subdirectories: `base/`, `overlays/dev/`, `overlays/staging/`.
2. Write base Kubernetes manifests for each service:
   - Deployment with resource requests/limits, liveness/readiness probes, environment variables from ConfigMaps/Secrets
   - Service (ClusterIP) exposing the appropriate port
   - ConfigMap for non-sensitive configuration
3. Write PostgreSQL deployment (StatefulSet with PVC, or reference Bitnami Helm chart).
4. Write Prometheus/Alertmanager deployment using kube-prometheus-stack Helm chart values file.
5. Create Kustomize overlays:
   - `dev` overlay: reduced replicas, relaxed resource limits, debug logging
   - `staging` overlay: production-like replicas, stricter limits
6. Define namespaces: `meridian-apps` for application services, `meridian-monitoring` for Prometheus stack.
7. Add Ingress or Gateway resources for external access to Next.js dashboard and GraphQL endpoint.
8. Create ServiceMonitor resources for all services (if not already in TASK-05).
9. Add Alertmanager configuration ConfigMap routing alerts to the FastAPI agent webhook.
10. Verify `docker-compose.yaml` still works for local dev without K8s.
11. Add Makefile targets: `k8s-apply-dev`, `k8s-apply-staging`, `k8s-delete`.
12. Test full deployment to a Kind cluster.

## Acceptance Criteria
- [ ] `kubectl apply -k k8s/overlays/dev/` deploys all services to a Kind cluster
- [ ] All pods reach Running state with passing health checks
- [ ] Prometheus discovers and scrapes all service metrics via ServiceMonitors
- [ ] Alertmanager routes alerts to the FastAPI agent webhook
- [ ] Next.js dashboard is accessible via Ingress or port-forward
- [ ] Namespace isolation is enforced (apps and monitoring in separate namespaces)
- [ ] `docker-compose up` still works for local development
- [ ] Kustomize overlays produce valid manifests (`kustomize build` succeeds)

## Dependencies
- TASK-01 (project scaffolding — Dockerfiles and docker-compose)
- TASK-04 (enrichment agent — Alertmanager webhook config)
- TASK-05 (example services — ServiceMonitors)

## Estimated Complexity
Large
