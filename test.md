# Deployment Guide

This document explains how every service in this monorepo is deployed to Kubernetes (AKS on Azure) using Helm, what every file does, and how the CI/CD pipeline ties everything together. Written for people who are new to Kubernetes, Helm, or kubectl.

---

## Background — The Big Picture

### What is Kubernetes (K8s)?

Kubernetes is a platform that runs your Node.js/NestJS applications inside a cloud cluster. Instead of running `node app.js` on a bare server, you tell Kubernetes **what you want** (e.g. "run 2 copies of the ECW service using this Docker image") and Kubernetes makes it happen and keeps it that way — restarting pods if they crash, distributing traffic, etc.

The cluster used here is **AKS** (Azure Kubernetes Service) — a managed Kubernetes cluster hosted on Azure.

**Key Kubernetes terms you'll encounter:**

| Term | Plain English |
|------|---------------|
| **Pod** | One running instance of a container (your app) |
| **Deployment** | Tells Kubernetes how to create and manage pods |
| **Service** | A stable internal network address that routes traffic to pods |
| **Ingress** | Exposes the service to the outside world via HTTP/HTTPS routing |
| **HPA** | HorizontalPodAutoscaler — automatically scales pod count up/down based on CPU/memory |
| **ConfigMap** | Non-secret config data stored in the cluster |
| **SecretProviderClass** | Pulls secrets from Azure Key Vault and injects them into pods |

### What is Helm?

Helm is a **templating and packaging tool** for Kubernetes. Instead of writing one static YAML file per environment (dev, staging, prod), you write templates with variables (e.g. `{{ .Values.branchName }}`). Helm fills in the values and applies everything to the cluster.

Think of it like: **Helm = Kubernetes + templating engine**.

A **Helm Chart** is a folder containing templates + default values. Running `helm upgrade --install` deploys or updates the application.

### What is kubectl?

`kubectl` is the command-line tool to talk to a Kubernetes cluster directly — listing pods, reading logs, describing resources, applying raw YAML files. Helm uses kubectl under the hood.

Common commands used in this project:

```bash
# See all running pods in a namespace
kubectl get pods -n momoconsumer-be

# Read logs from a pod
kubectl logs <pod-name> -n momoconsumer-be

# Describe a deployment (shows events, errors)
kubectl describe deployment momoconsumer-be-3-3-x-ecw -n momoconsumer-be

# Force-delete a stuck pod so it restarts
kubectl delete pod <pod-name> -n momoconsumer-be
```

---

## Deploy Folder Structure

Every service has its own Helm chart under the `deploy/` folder:

```
deploy/
├── momo-consumer-be-ecw/        ← ECW service chart
├── momo-consumer-be-gha/        ← GHA service chart
├── momo-consumer-be-gips/       ← GIPS service chart
├── momo-consumer-be-device/
├── momo-consumer-be-cashin/
├── momo-consumer-be-cis/
├── momo-consumer-be-buytickets/
├── momo-consumer-be-gsm/
├── momo-consumer-be-jumo/
├── momo-consumer-be-mad/
├── momo-consumer-be-referral/
├── momo-consumer-be-registration/
├── momo-consumer-be-senkyu/
├── momo-consumer-be-virtualcard/
└── momo-consumer-be-evesis/
```

Each folder has the same structure:

```
momo-consumer-be-ecw/
├── Chart.yaml              ← Chart metadata (name, version)
├── values.yaml             ← Default configuration values
├── .helmignore             ← Files to exclude (like .gitignore)
├── environments/           ← Per-environment value overrides
│   ├── dev.yaml
│   ├── staging.yaml
│   └── prod.yaml
└── templates/              ← Kubernetes resource templates
    ├── deployment.yaml     ← How to run the app
    ├── service.yaml        ← Internal network routing
    ├── ingress.yaml        ← External HTTP routing
    ├── hpa.yaml            ← Auto-scaling rules
    ├── config-map.yaml     ← Non-secret environment config
    └── secret-provider-class.yaml  ← Azure Key Vault secret injection
```

---

## File-by-File Explanation

### `Chart.yaml`

Identifies the Helm chart. The `version` and `appVersion` fields are replaced by the build pipeline with the actual release version.

```yaml
apiVersion: v2
name: momo-consumer-be-ecw
description: A Helm chart for deploying momo-consumer-be-ecw to Kubernetes
version: "{version}"       # Filled in by the pipeline
appVersion: "{version}"    # Filled in by the pipeline
```

---

### `values.yaml`

The **central configuration file**. Contains all the default settings that the templates reference with `{{ .Values.something }}`. The pipeline and environment override files can overwrite any of these values at deploy time.

Key sections in `values.yaml`:

```yaml
serviceName: ecw             # Used to name all K8s resources

image:
  tag: '{version}'           # Docker image tag — set by the pipeline to the build number

envName: __set_by_pipeline__ # e.g. "development", "production"
locationName: __defined_per_env__  # e.g. "ghana", "uganda"

deployIntoEnv: true          # Master switch — if false, nothing deploys

containerRegistry: __defined_per_env__  # Azure Container Registry URL

branchName: __set_by_pipeline__   # e.g. "3-3-x", "main"

resources:                   # CPU/memory limits for each pod
  limits:
    cpu: "1"
    memory: 2Gi
  requests:
    cpu: 500m
    memory: 1Gi

autoscaling:
  enabled: true              # Whether HPA manages replica count
  minReplicas: 1
  maxReplicas: 2
  targetCPUUtilizationPercentage: 80
  targetMemoryUtilizationPercentage: 80
```

Anything marked `__set_by_pipeline__` or `__defined_per_env__` is **not** set here — the pipeline injects the real value at deploy time using `--set` flags or environment-specific override files.

---

### `templates/deployment.yaml`

This is the most important file. It tells Kubernetes **how to run your application**.

```yaml
{{- if .Values.deployIntoEnv -}}   ← Only creates this resource if deployIntoEnv is true
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: 'momoconsumer-be-{{ .Values.branchName }}-{{ .Values.serviceName }}'
  # e.g. "momoconsumer-be-3-3-x-ecw"
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: 1                ← Only set when HPA is OFF (see HPA section below)
  {{- end }}
  selector:
    matchLabels:
      app: 'momoconsumer-be-{{ .Values.branchName }}-{{ .Values.serviceName }}'
  template:
    spec:
      containers:
        - name: '...'
          image: '{{ .Values.containerRegistry }}.azurecr.io/momoconsumer-be-{{ .Values.serviceName }}:{{ .Values.image.tag }}'
          # ↑ Pulls the Docker image from Azure Container Registry
          envFrom:
            - secretRef:
                name: 'keyvault-secrets-...'  ← Injects secrets as env vars
          env:
            - name: NODE_ENV
              value: '{{ .Values.envName }}'   ← e.g. "development"
          resources:
            limits:
              cpu: {{ .Values.resources.limits.cpu }}
              memory: {{ .Values.resources.limits.memory }}
```

**Important: `replicas` is conditional**

When HPA (auto-scaling) is enabled, the HPA controller in Kubernetes owns the replica count. If Helm also tried to set `replicas`, the two would conflict and the deployment would fail with:

```
conflict with "kube-controller-manager" using apps/v1: .spec.replicas
```

The fix: `replicas` is only written into the manifest when `autoscaling.enabled` is `false`. When HPA is active, the replicas line is omitted entirely and HPA has full control.

**`hostAliases`** — The deployment file also contains a long list of internal IP-to-hostname mappings. These are like a `/etc/hosts` file injected into every pod, so the service can resolve internal MTN hostnames (e.g. `ecw-test.mtn.com.gh`) that aren't in public DNS.

---

### `templates/service.yaml`

Creates an internal **ClusterIP Service** — a stable internal IP address and DNS name that other services or the Ingress can use to reach your pods.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: 'momoconsumer-be-{{ .Values.branchName }}-{{ .Values.serviceName }}'
spec:
  type: ClusterIP    ← Only reachable inside the cluster, not from the internet
  ports:
    - port: 80
  selector:
    app: momoconsumer-be-{{ .Values.branchName }}-{{ .Values.serviceName }}
    # ↑ Routes traffic to pods that have this label
```

Without this, your pods are isolated — nothing can reach them.

---

### `templates/ingress.yaml`

Exposes the service to the **outside world** via NGINX Ingress. This is what makes the service reachable via a hostname like `api.momo.mtn.com`.

The ingress in this project uses the **"minion"** pattern (NGINX Ingress Controller mergeable ingresses) — a single master Ingress handles TLS termination, and each service registers itself as a minion with its own path.

```yaml
{{- if .Values.ingress.minion.enabled -}}   ← Only created if enabled in values
spec:
  rules:
    - host: {{ .Values.ingress.hostname }}   ← e.g. "api.momo.mtn.com"
      http:
        paths:
          - path: /{{ .Values.serviceName }}/momoconsumer-be-{{ .Values.branchName }}/(.*)
            # e.g. /ecw/momoconsumer-be-3-3-x/*
            backend:
              service:
                name: 'momoconsumer-be-...'
                port:
                  number: 80
  tls:
    - secretName: ingress-tls-csi   ← TLS certificate from Key Vault
```

---

### `templates/hpa.yaml`

The **HorizontalPodAutoscaler** automatically increases or decreases the number of running pods based on real-time CPU and memory usage.

```yaml
{{- if .Values.autoscaling.enabled -}}   ← Only created when autoscaling is on
spec:
  scaleTargetRef:
    kind: Deployment
    name: 'momoconsumer-be-...'     ← Points at the Deployment to scale
  minReplicas: 1     ← Never go below 1 pod
  maxReplicas: 2     ← Never go above 2 pods (prod overrides this to a higher number)
  metrics:
    - cpu: 80%       ← If average CPU across all pods exceeds 80%, add more pods
    - memory: 80%    ← Same for memory
```

**How autoscaling works:**

1. All pods sit at 1 replica (the minimum).
2. A spike in traffic causes CPU to jump above 80%.
3. HPA adds pods (up to the `maxReplicas` limit) to spread the load.
4. Traffic drops → HPA scales back down after a cooldown period.

---

### `templates/secret-provider-class.yaml`

Connects Azure Key Vault to pods. Secrets stored in Key Vault (e.g. `NODE-DATABASE-PASSWORD`, `JWT-SECRET`, `AZURE-CACHE-FOR-REDIS-ACCESS-KEY`) are fetched by the CSI driver and **mounted as files** into the pod's filesystem at `/mnt/secrets`. The `envFrom: secretRef` in the deployment then picks them up as environment variables automatically.

```yaml
spec:
  provider: azure
  parameters:
    keyvaultName: {{ .Values.keyVault.name }}
    userAssignedIdentityID: {{ .Values.keyVault.userAssignedIdentityID }}
    rotationPollInterval: "24h"    ← Re-checks Key Vault every 24h for secret rotation
    objects: |
      array:
        - objectName: NODE-DATABASE-PASSWORD
          objectType: secret
        - objectName: JWT-SECRET
          objectType: secret
        # ... more secrets
```

No secret values ever appear in code or Git — they live only in Azure Key Vault.

---

### `templates/config-map.yaml`

Stores non-sensitive configuration that is injected as environment variables. Unlike secrets (which go through Key Vault), ConfigMaps hold plain config like feature flags or service names.

---

## How the Pipeline Uses All This

The CI/CD pipeline (Azure DevOps or GitHub Actions) runs these steps on every merge to a deploy branch:

```
1. Build Docker image
   └─ docker build -t <registry>.azurecr.io/momoconsumer-be-ecw:<version> .

2. Push image to Azure Container Registry (ACR)
   └─ docker push <registry>.azurecr.io/momoconsumer-be-ecw:<version>

3. Deploy using Helm
   └─ helm upgrade --install \
        momoconsumer-be-<branch>-ecw \           ← Release name
        ./deploy/momo-consumer-be-ecw \          ← Path to the Helm chart
        --namespace momoconsumer-be \            ← K8s namespace
        --set image.tag=<version> \              ← The Docker image version just built
        --set branchName=<branch> \              ← e.g. "3-3-x"
        --set envName=development \              ← Target environment
        --set containerRegistry=<acr-name> \
        -f ./deploy/momo-consumer-be-ecw/environments/dev.yaml \  ← Env overrides
        --server-side                            ← Uses server-side apply (SSA)
```

The `--server-side` flag is important — it tells Kubernetes to track field ownership server-side, which is why the `replicas` / HPA conflict exists if not handled correctly.

---

## Resource Naming Convention

All Kubernetes resources follow this pattern:

```
momoconsumer-be-{branchName}-{serviceName}
```

Examples:
- `momoconsumer-be-3-3-x-ecw` — ECW service on the `3-3-x` branch
- `momoconsumer-be-main-gha` — GHA service on the `main` branch

This means **multiple branches of the same service can run in the cluster at the same time** without colliding — each branch is a fully isolated deployment.

---

## Common Issues and Fixes

### `conflict with "kube-controller-manager" using apps/v1: .spec.replicas`

**Cause:** HPA is enabled for the service, but the Deployment manifest also hardcodes `replicas: 1`. Kubernetes uses Server-Side Apply (SSA) to track field ownership. The HPA controller owns `.spec.replicas`; Helm trying to set it causes a conflict.

**Fix (already applied):** The `replicas` field in all `deployment.yaml` files is now conditional:
```yaml
{{- if not .Values.autoscaling.enabled }}
replicas: 1
{{- end }}
```
When `autoscaling.enabled: true`, Helm does not write `replicas` to the manifest at all. The HPA owns it exclusively.

**If the release is stuck in a broken state**, reset it with:
```bash
# Option 1: Remove replicas field from the live resource so the next deploy succeeds
kubectl patch deployment momoconsumer-be-3-3-x-ecw -n momoconsumer-be \
  --type=json -p='[{"op": "remove", "path": "/spec/replicas"}]'

# Option 2: Roll back the Helm release to the last good revision
helm rollback momoconsumer-be-3-3-x-ecw 0 -n momoconsumer-be
```

---

### Pod stuck in `ImagePullBackOff`

The pod can't pull its Docker image. Usually means:
- The image tag doesn't exist in ACR (build failed before push)
- The AKS cluster doesn't have pull permissions for ACR

```bash
kubectl describe pod <pod-name> -n momoconsumer-be
# Look at the Events section for the exact error
```

---

### Pod stuck in `CrashLoopBackOff`

The container starts but immediately crashes. Check logs:
```bash
kubectl logs <pod-name> -n momoconsumer-be
kubectl logs <pod-name> -n momoconsumer-be --previous  # logs from the crashed instance
```

---

### Secrets not loading / `undefined` env vars

The `SecretProviderClass` couldn't reach Key Vault. This usually means:
- Wrong `userAssignedIdentityID` in values
- The secret name in Key Vault doesn't match what's defined in `secret-provider-class.yaml`

```bash
kubectl describe secretproviderclass keyvault-secrets-ecw-3-3-x -n momoconsumer-be
```
