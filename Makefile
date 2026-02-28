# Makefile for PoC Deployment
#
# Namespace-isolated deployments for parallel testing.
# Cluster-level targets (shared): kind-up, kind-down, images
# Namespace-level targets (per TEST_NS): deploy, undeploy, monitoring-up,
#   openslo-deploy, rules-deploy, agent-deploy, service-deploy,
#   exercise-normal, exercise-breach

.PHONY: all help kind-up kind-down images \
	deploy undeploy monitoring-up agent-deploy service-deploy \
	openslo-deploy rules-deploy exercise-normal exercise-breach clean

# --- Configuration ---
KIND_CLUSTER_NAME ?= podman-poc-cluster
KIND_RUNTIME      := podman
GEMINI_TMP_DIR    ?= /Users/whit/.gemini/tmp/1a93520244d34034b85edcaf49363e36b9daf386fab35bdd7158f71fa937dd9e

# Namespace isolation: set TEST_NS to run parallel deploys.
#   make deploy TEST_NS=test-alpha
#   make deploy TEST_NS=test-beta
TEST_NS       ?= default
MONITORING_NS := $(TEST_NS)-monitoring

# Image names
AGENT_IMAGE_NAME   ?= ai-agent
AGENT_IMAGE_TAG    ?= latest
AGENT_BUILD_CONTEXT ?= ./ai-agent

SERVICE_IMAGE_NAME   ?= example-service
SERVICE_IMAGE_TAG    ?= latest
SERVICE_BUILD_CONTEXT ?= ./example-service

# Helm values template (contains DEPLOY_NAMESPACE placeholder)
HELM_VALUES_TPL := ./kubernetes/helm-values/alertmanager-values.yaml.tpl
HELM_VALUES_OUT := /tmp/alertmanager-values-$(TEST_NS).yaml

# Kubeconfig shorthand
KUBECONFIG_PATH := $(GEMINI_TMP_DIR)/kubeconfig-$(KIND_CLUSTER_NAME)
export KUBECONFIG := $(KUBECONFIG_PATH)

# ============================================================================
# General Targets
# ============================================================================

all: kind-up images deploy ## Builds and deploys everything (default namespace)

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

clean: kind-down ## Cleans up the Kind cluster and all deployments
	@echo "Cleaning up..."

# ============================================================================
# Cluster-level targets (shared, run once)
# ============================================================================

kind-up: ## Creates the Kind Kubernetes cluster using Podman
	@echo "Creating Kind cluster '$(KIND_CLUSTER_NAME)' with Podman runtime..."
	@mkdir -p $(GEMINI_TMP_DIR)
	@KIND_CONTAINER_RUNTIME=$(KIND_RUNTIME) kind create cluster --name $(KIND_CLUSTER_NAME) || true
	@echo "Kind cluster '$(KIND_CLUSTER_NAME)' is up."
	@kubectl cluster-info --context kind-$(KIND_CLUSTER_NAME)

kind-down: ## Deletes the Kind Kubernetes cluster
	@echo "Deleting Kind cluster '$(KIND_CLUSTER_NAME)'..."
	@KIND_CONTAINER_RUNTIME=$(KIND_RUNTIME) kind delete cluster --name $(KIND_CLUSTER_NAME)
	@echo "Kind cluster '$(KIND_CLUSTER_NAME)' deleted."

images: agent-build agent-load service-build service-load ## Build and load all images into Kind

agent-build:
	@echo "Building AI agent image '$(AGENT_IMAGE_NAME):$(AGENT_IMAGE_TAG)'..."
	@podman build -t $(AGENT_IMAGE_NAME):$(AGENT_IMAGE_TAG) $(AGENT_BUILD_CONTEXT)

agent-load: agent-build
	@echo "Loading AI agent image into Kind cluster '$(KIND_CLUSTER_NAME)'..."
	@KIND_CONTAINER_RUNTIME=$(KIND_RUNTIME) kind load docker-image $(AGENT_IMAGE_NAME):$(AGENT_IMAGE_TAG) --name $(KIND_CLUSTER_NAME)

service-build:
	@echo "Building example service image '$(SERVICE_IMAGE_NAME):$(SERVICE_IMAGE_TAG)'..."
	@podman build -t $(SERVICE_IMAGE_NAME):$(SERVICE_IMAGE_TAG) $(SERVICE_BUILD_CONTEXT)

service-load: service-build
	@echo "Loading example service image into Kind cluster '$(KIND_CLUSTER_NAME)'..."
	@KIND_CONTAINER_RUNTIME=$(KIND_RUNTIME) kind load docker-image $(SERVICE_IMAGE_NAME):$(SERVICE_IMAGE_TAG) --name $(KIND_CLUSTER_NAME)

# ============================================================================
# Namespace-level targets (per TEST_NS)
# ============================================================================

deploy: monitoring-up agent-deploy service-deploy openslo-deploy rules-deploy ## Deploy all components into TEST_NS
	@echo "All components deployed to namespace '$(TEST_NS)'."

undeploy: ## Tear down TEST_NS and its monitoring namespace
	@echo "Deleting namespace '$(TEST_NS)'..."
	@kubectl delete namespace $(TEST_NS) --ignore-not-found
	@echo "Deleting namespace '$(MONITORING_NS)'..."
	@kubectl delete namespace $(MONITORING_NS) --ignore-not-found
	@echo "Namespaces deleted. Cleanup complete."

monitoring-up: ## Deploy Prometheus and Alertmanager via Helm into MONITORING_NS
	@echo "Deploying monitoring to namespace '$(MONITORING_NS)' (TEST_NS=$(TEST_NS))..."
	@kubectl create namespace $(MONITORING_NS) --dry-run=client -o yaml | kubectl apply -f -
	@helm repo add prometheus-community https://prometheus-community.github.io/helm-charts || true
	@helm repo update
	@if [ -f "$(HELM_VALUES_TPL)" ]; then \
		sed 's/DEPLOY_NAMESPACE/$(TEST_NS)/g' $(HELM_VALUES_TPL) > $(HELM_VALUES_OUT); \
		helm upgrade --install prometheus-$(TEST_NS) prometheus-community/kube-prometheus-stack \
			--namespace $(MONITORING_NS) \
			-f $(HELM_VALUES_OUT); \
	else \
		helm upgrade --install prometheus-$(TEST_NS) prometheus-community/kube-prometheus-stack \
			--namespace $(MONITORING_NS); \
	fi

agent-deploy: ## Deploy the AI agent into TEST_NS
	@echo "Deploying AI agent to namespace '$(TEST_NS)'..."
	@kubectl create namespace $(TEST_NS) --dry-run=client -o yaml | kubectl apply -f -
	@kubectl apply -n $(TEST_NS) -f ./kubernetes/agent-deployment.yaml

service-deploy: ## Deploy the example service into TEST_NS
	@echo "Deploying example service to namespace '$(TEST_NS)'..."
	@kubectl create namespace $(TEST_NS) --dry-run=client -o yaml | kubectl apply -f -
	@kubectl apply -n $(TEST_NS) -f ./kubernetes/service-deployment.yaml

openslo-deploy: ## Deploy OpenSLO definitions into TEST_NS
	@echo "Deploying OpenSLO definitions to namespace '$(TEST_NS)'..."
	@kubectl create namespace $(TEST_NS) --dry-run=client -o yaml | kubectl apply -f -
	@if [ -d "./kubernetes/openslo" ]; then \
		kubectl apply -n $(TEST_NS) -f ./kubernetes/openslo/; \
	else \
		echo "  (no openslo manifests found in ./kubernetes/openslo/ - skipping)"; \
	fi

rules-deploy: ## Deploy Prometheus rules into MONITORING_NS
	@echo "Deploying Prometheus rules to namespace '$(MONITORING_NS)'..."
	@if [ -d "./kubernetes/rules" ]; then \
		kubectl apply -n $(MONITORING_NS) -f ./kubernetes/rules/; \
	else \
		echo "  (no rules found in ./kubernetes/rules/ - skipping)"; \
	fi

exercise-normal: ## Send normal traffic to the example service in TEST_NS
	@echo "Exercising normal traffic in namespace '$(TEST_NS)'..."
	@kubectl run exerciser-normal-$(TEST_NS) --rm -i --restart=Never \
		-n $(TEST_NS) \
		--image=curlimages/curl -- \
		sh -c 'for i in $$(seq 1 100); do curl -s http://example-service.$(TEST_NS).svc.cluster.local:8080/health; done'

exercise-breach: ## Send breach-inducing traffic to the example service in TEST_NS
	@echo "Exercising breach traffic in namespace '$(TEST_NS)'..."
	@kubectl run exerciser-breach-$(TEST_NS) --rm -i --restart=Never \
		-n $(TEST_NS) \
		--image=curlimages/curl -- \
		sh -c 'for i in $$(seq 1 100); do curl -s http://example-service.$(TEST_NS).svc.cluster.local:8080/latency?delay=2000; curl -s http://example-service.$(TEST_NS).svc.cluster.local:8080/error; done'
