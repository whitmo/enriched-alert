.PHONY: all help clean kind-up kind-down monitoring-up openslo-deploy rules-deploy \
	agent-build agent-load agent-deploy service-build service-load service-deploy \
	exercise-normal exercise-breach

# --- Configuration ---
KIND_CLUSTER_NAME   ?= enriched-alert
CONTAINER_RUNTIME   ?= docker
MONITORING_NS       := monitoring
AGENT_IMAGE         := ai-agent:latest
SERVICE_IMAGE       := example-service:latest

# --- General ---
all: kind-up monitoring-up rules-deploy agent-deploy service-deploy

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

clean: kind-down ## Delete cluster and all resources

# --- Kind Cluster ---
kind-up: ## Create Kind cluster
	KIND_EXPERIMENTAL_PROVIDER=$(CONTAINER_RUNTIME) kind create cluster \
		--name $(KIND_CLUSTER_NAME) \
		--config kind-config.yaml
	kubectl cluster-info --context kind-$(KIND_CLUSTER_NAME)

kind-down: ## Delete Kind cluster
	KIND_EXPERIMENTAL_PROVIDER=$(CONTAINER_RUNTIME) kind delete cluster \
		--name $(KIND_CLUSTER_NAME)

# --- Monitoring ---
monitoring-up: ## Deploy kube-prometheus-stack via Helm
	kubectl create namespace $(MONITORING_NS) --dry-run=client -o yaml | kubectl apply -f -
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts || true
	helm repo update
	helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
		--namespace $(MONITORING_NS) \
		-f kubernetes/monitoring/helm-values.yaml

# --- OpenSLO / Rules ---
openslo-deploy: ## Deploy OpenSLO definitions as a ConfigMap
	kubectl create configmap openslo-definitions \
		--from-file=openslo/ \
		--dry-run=client -o yaml | kubectl apply -f -

rules-deploy: ## Deploy Prometheus recording/alerting rules and ServiceMonitor
	kubectl apply -f kubernetes/monitoring/prometheus-rules.yaml -n $(MONITORING_NS)
	kubectl apply -f kubernetes/monitoring/service-monitor.yaml -n $(MONITORING_NS)

# --- AI Agent ---
agent-build: ## Build AI agent container image
	$(CONTAINER_RUNTIME) build -t $(AGENT_IMAGE) ./ai-agent

agent-load: ## Load AI agent image into Kind
	KIND_EXPERIMENTAL_PROVIDER=$(CONTAINER_RUNTIME) kind load docker-image $(AGENT_IMAGE) \
		--name $(KIND_CLUSTER_NAME)

agent-deploy: ## Deploy AI agent to cluster
	kubectl apply -f ai-agent/kubernetes/deployment.yaml

# --- Example Service ---
service-build: ## Build example service container image
	$(CONTAINER_RUNTIME) build -t $(SERVICE_IMAGE) ./example-service

service-load: ## Load example service image into Kind
	KIND_EXPERIMENTAL_PROVIDER=$(CONTAINER_RUNTIME) kind load docker-image $(SERVICE_IMAGE) \
		--name $(KIND_CLUSTER_NAME)

service-deploy: ## Deploy example service to cluster
	kubectl apply -f example-service/kubernetes/deployment.yaml

# --- Exerciser ---
exercise-normal: ## Send normal traffic to example service
	kubectl run exerciser --rm -i --restart=Never --image=curlimages/curl -- \
		sh -c 'for i in $$(seq 1 100); do curl -s http://example-service/; sleep 0.1; done'

exercise-breach: ## Send traffic designed to trigger SLO breach
	kubectl run exerciser --rm -i --restart=Never --image=curlimages/curl -- \
		sh -c 'for i in $$(seq 1 200); do curl -s "http://example-service/latency?delay_ms=2000"; curl -s http://example-service/error; sleep 0.05; done'
