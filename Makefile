# Makefile for PoC Deployment

.PHONY: all help kind-up kind-down monitoring-up agent-build agent-load agent-deploy 
	service-build service-load service-deploy clean

KIND_CLUSTER_NAME ?= podman-poc-cluster
KIND_RUNTIME := podman
MONITORING_NAMESPACE := monitoring
GEMINI_TMP_DIR ?= /Users/whit/.gemini/tmp/1a93520244d34034b85edcaf49363e36b9daf386fab35bdd7158f71fa937dd9e

# --- General Targets ---
all: kind-up monitoring-up agent-deploy service-deploy ## Builds and deploys everything

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

clean: kind-down ## Cleans up the Kind cluster and all deployments
	@echo "Cleaning up..."

# --- Kind Cluster Management ---
kind-up: ## Creates the Kind Kubernetes cluster using Podman
	@echo "Creating Kind cluster '$(KIND_CLUSTER_NAME)' with Podman runtime..."
	@mkdir -p $(GEMINI_TMP_DIR) # Ensure temp directory exists
	@export KUBECONFIG=$(GEMINI_TMP_DIR)/kubeconfig-$(KIND_CLUSTER_NAME) && \
	KIND_CONTAINER_RUNTIME=$(KIND_RUNTIME) kind create cluster --name $(KIND_CLUSTER_NAME) || true
	@echo "Kind cluster '$(KIND_CLUSTER_NAME)' is up."
	@export KUBECONFIG=$(GEMINI_TMP_DIR)/kubeconfig-$(KIND_CLUSTER_NAME) && \
	kubectl cluster-info --context kind-$(KIND_CLUSTER_NAME)
	@echo "KUBECONFIG for cluster '$(KIND_CLUSTER_NAME)' is set to $(GEMINI_TMP_DIR)/kubeconfig-$(KIND_CLUSTER_NAME)"

kind-down: ## Deletes the Kind Kubernetes cluster
	@echo "Deleting Kind cluster '$(KIND_CLUSTER_NAME)'..."
	@export KUBECONFIG=$(GEMINI_TMP_DIR)/kubeconfig-$(KIND_CLUSTER_NAME) && \
	KIND_CONTAINER_RUNTIME=$(KIND_RUNTIME) kind delete cluster --name $(KIND_CLUSTER_NAME)
	@echo "Kind cluster '$(KIND_CLUSTER_NAME)' deleted."

# --- Monitoring Infrastructure (Prometheus, Alertmanager) ---
monitoring-up: ## Deploys Prometheus and Alertmanager via Helm
	@echo "Deploying monitoring infrastructure to namespace '$(MONITORING_NAMESPACE)'..."
	@kubectl create namespace $(MONITORING_NAMESPACE) --dry-run=client -o yaml | kubectl apply -f - || true
	@helm repo add prometheus-community https://prometheus-community.github.io/helm-charts || true
	@helm repo update
	@helm upgrade --install prometheus prometheus-community/kube-prometheus-stack --namespace $(MONITORING_NAMESPACE)

# --- AI Agent Targets ---
AGENT_IMAGE_NAME ?= ai-agent
AGENT_IMAGE_TAG ?= latest
AGENT_BUILD_CONTEXT ?= ./ai-agent # Assuming agent code is in a folder named ai-agent

agent-build: ## Builds the AI agent Podman image
	@echo "Building AI agent image '$(AGENT_IMAGE_NAME):$(AGENT_IMAGE_TAG)'..."
	@podman build -t $(AGENT_IMAGE_NAME):$(AGENT_IMAGE_TAG) $(AGENT_BUILD_CONTEXT)

agent-load: agent-build ## Loads the AI agent image into the Kind cluster
	@echo "Loading AI agent image into Kind cluster '$(KIND_CLUSTER_NAME)'..."
	@KIND_CONTAINER_RUNTIME=$(KIND_RUNTIME) kind load docker-image $(AGENT_IMAGE_NAME):$(AGENT_IMAGE_TAG) --name $(KIND_CLUSTER_NAME)

agent-deploy: agent-load ## Deploys the AI agent to the Kind cluster
	@echo "Deploying AI agent to Kind cluster '$(KIND_CLUSTER_NAME)'..."
	@kubectl apply -f ./kubernetes/agent-deployment.yaml # Assuming deployment manifests are here

# --- Example Service Targets ---
SERVICE_IMAGE_NAME ?= example-service
SERVICE_IMAGE_TAG ?= latest
SERVICE_BUILD_CONTEXT ?= ./example-service # Assuming service code is in a folder named example-service

service-build: ## Builds the example service Podman image
	@echo "Building example service image '$(SERVICE_IMAGE_NAME):$(SERVICE_IMAGE_TAG)'..."
	@podman build -t $(SERVICE_IMAGE_NAME):$(SERVICE_IMAGE_TAG) $(SERVICE_BUILD_CONTEXT)

service-load: service-build ## Loads the example service image into the Kind cluster
	@echo "Loading example service image into Kind cluster '$(KIND_CLUSTER_NAME)'..."
	@KIND_CONTAINER_RUNTIME=$(KIND_RUNTIME) kind load docker-image $(SERVICE_IMAGE_NAME):$(SERVICE_IMAGE_TAG) --name $(KIND_CLUSTER_NAME)

service-deploy: service-load ## Deploys the example service to the Kind cluster
	@echo "Deploying example service to Kind cluster '$(KIND_CLUSTER_NAME)'..."
	@kubectl apply -f ./kubernetes/service-deployment.yaml # Assuming deployment manifests are here
