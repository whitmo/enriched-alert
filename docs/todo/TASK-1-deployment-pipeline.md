# PoC Plan: Task 1 - Simple Deployment Pipeline (Local Kubernetes with Kind and Podman)

## Objective
Establish a local Kubernetes development environment using Kind (Kubernetes in Docker, powered by Podman) to facilitate the deployment and testing of all PoC components. This pipeline will enable quick iteration and easy teardown of the entire environment, utilizing Podman as the container runtime.

## Components
*   **Kind (Kubernetes in Docker)**: For provisioning a local Kubernetes cluster.
*   **Podman**: The container engine for running Kind nodes and other containerized components.
*   **`kubectl`**: The command-line tool for interacting with the Kubernetes cluster.

## Steps

### 1. Install Kind and `kubectl` (and ensure Podman is configured)
*   Ensure Kind and `kubectl` are installed and properly configured on the local development machine.
    *   `brew install kind`
    *   `brew install kubectl`
*   Verify Podman installation and ensure its daemon is running if required by your setup. No build is needed for Podman.

### 2. Configure Kind to use Podman
*   Before creating the cluster, set the `KIND_CONTAINER_RUNTIME` environment variable:
    ```bash
    export KIND_CONTAINER_RUNTIME=podman
    ```
    *Note: This environment variable needs to be set in the shell session where you run `kind create cluster`.*

### 3. Create a Kind Cluster
*   Define a `kind-config.yaml` (optional, for specific cluster details like number of nodes or Kubernetes version). For a basic cluster:
    ```bash
    kind create cluster --name podman-poc-cluster # --config kind-config.yaml if needed
    ```
*   Configure `kubectl` to use the new Kind cluster's context:
    ```bash
    kubectl cluster-info --context kind-podman-poc-cluster
    ```
    (This command will usually automatically set the context, but it's good to verify or explicitly set if multiple contexts exist).

### 4. Basic Cluster Verification
*   Verify the cluster is running and accessible:
    ```bash
    kubectl get nodes
    ```
*   Check for default namespaces and services.

### 5. Integrate with Local Development Workflow
*   Document commands for easy startup and shutdown of the Kind cluster.
    *   To start/create: `export KIND_CONTAINER_RUNTIME=podman && kind create cluster --name podman-poc-cluster`
    *   To delete: `export KIND_CONTAINER_RUNTIME=podman && kind delete cluster --name podman-poc-cluster`
*   Outline how to deploy Kubernetes manifests (`.yaml` files) to the cluster using `kubectl apply -f <directory>`.
*   Note for building images locally for Kind with Podman: you will need to build the images using `podman build` and then load them into the Kind cluster using `kind load docker-image <image-name>:<tag> --name podman-poc-cluster`.

## Acceptance Criteria
*   A Kind Kubernetes cluster can be reliably created and deleted using documented commands, specifically leveraging Podman as the container runtime.
*   `kubectl` can successfully interact with the Kind cluster.
*   Basic Kubernetes resources (e.g., namespaces, deployments) can be deployed to the cluster.
*   Locally built Podman images can be loaded into the Kind cluster.