# Kubernetes IaC Tool Comparison

Research comparing Helm, Kustomize, Jsonnet/Tanka, cdk8s, Pulumi, and Timoni for Kubernetes config management. Dual-perspective analysis (Gemini + Claude) with project-specific recommendation.

**Note:** ksonnet was archived in 2019 and is dead. It influenced later tools (particularly Tanka) but should not be considered for any new project.

## Detailed SWOT per Tool

### Helm

| | |
|---|---|
| **Strengths** | De facto standard, massive chart ecosystem (Artifact Hub), strong release management (versioning, rollback), dependency management between charts, every monitoring/infra tool ships a Helm chart |
| **Weaknesses** | Go templates are painful to debug (whitespace, indentation, `{{ include }}` nesting), no native secrets handling, templates process YAML as text not structure, over-templating is a common trap |
| **Opportunities** | GitOps integration improving (ArgoCD/Flux both have first-class Helm support), OCI registry support maturing, helm-secrets plugin ecosystem |
| **Threats** | Templating approach is architecturally limited (text substitution into YAML), community charts vary wildly in quality and maintenance |

**Templating:** Go templates with `values.yaml` overrides. Text-based substitution into YAML.
**Env promotion:** Override values files per environment (`values-dev.yaml`, `values-prod.yaml`).
**Secrets:** Not handled natively. Requires helm-secrets plugin, External Secrets Operator, or Sealed Secrets.
**Dependencies:** `Chart.yaml` dependencies, sub-charts. Works but can create deep nesting.
**Drift:** No built-in detection. `helm diff` plugin helps. GitOps tools provide reconciliation.

### Kustomize

| | |
|---|---|
| **Strengths** | Built into `kubectl` (zero install), template-free (plain YAML + patches), excellent for "last-mile" customization, base/overlay model maps cleanly to env promotion, default renderer in ArgoCD and Flux |
| **Weaknesses** | No programming logic (loops, conditionals), can't generate complex dynamic config, patch management gets unwieldy with many environments, no package distribution story |
| **Opportunities** | Components feature adds reusable config blocks, Kustomize + Helm (post-render) gives best of both worlds |
| **Threats** | Feature development has slowed, limited expressiveness ceiling means you'll outgrow it for complex scenarios |

**Templating:** None. Uses strategic merge patches, JSON patches, and overlays on base YAML.
**Env promotion:** `base/` + `overlays/{dev,staging,prod}/` directory structure. Clean and git-friendly.
**Secrets:** `secretGenerator` creates secrets from files/literals, but no encryption. Pair with SOPS or External Secrets.
**Dependencies:** None built-in. Ordering is implicit by resource type.
**Drift:** `kubectl diff` for manual checks. GitOps reconciliation loops for automated detection.

### Jsonnet/Tanka

| | |
|---|---|
| **Strengths** | Real programming language (functions, imports, deep merge), Tanka adds K8s-specific environment management, `tk diff` is excellent, used in production at Grafana Labs scale |
| **Weaknesses** | Jsonnet is a niche DSL with steep learning curve, ecosystem has stalled (it's basically a Grafana Labs tool now), jsonnet-bundler dependency management is rough, limited community outside Grafana ecosystem |
| **Opportunities** | If you're already in the Grafana ecosystem (Loki, Mimir, Tempo), the jsonnet libraries are excellent |
| **Threats** | Adoption peaked and declined, new projects rarely choose it, talent pool is very small, bus-factor risk |

**Templating:** Jsonnet language compiles to JSON. Full programming: variables, functions, imports, deep merging.
**Env promotion:** Tanka environments with per-env main.jsonnet files applying different parameters.
**Secrets:** No native support. External tools required (Vault, SOPS, Sealed Secrets).
**Dependencies:** jsonnet-bundler (`jb`) for library management. Works but rough edges.
**Drift:** `tk diff` compares rendered output against live cluster. Excellent when it works.

### cdk8s

| | |
|---|---|
| **Strengths** | Define K8s resources in TypeScript/Python/Go/Java, type safety and IDE autocompletion, testable with standard testing frameworks, CNCF sandbox project |
| **Weaknesses** | Adoption has essentially flatlined, AWS isn't pushing it hard, synthesize-to-YAML workflow adds indirection, no deployment mechanism (just generates YAML), construct ecosystem never materialized, `cdk8s+` (the ergonomic layer) is incomplete |
| **Opportunities** | Conceptually sound for teams that strongly prefer code-over-config |
| **Threats** | Low momentum, small community, competing with Pulumi for the "code-based" niche and losing |

**Templating:** General-purpose programming languages. Synthesizes to standard K8s YAML.
**Env promotion:** Generate different YAML per environment in code, apply via external tools.
**Secrets:** Defines Secret objects but doesn't handle secure storage. External tools required.
**Dependencies:** `addDependency()` for resource ordering within a chart. No cross-chart dependency model.
**Drift:** None. Relies entirely on external tooling (GitOps, kubectl diff).

### Pulumi

| | |
|---|---|
| **Strengths** | Full programming languages (TS, Python, Go, C#, Java), manages cloud infra AND K8s in one tool, automatic dependency graph, Pulumi ESC for secrets, state management with drift detection (`pulumi refresh`), Kubernetes Operator for GitOps |
| **Weaknesses** | Overkill for K8s-only config management, commercial model with pricing concerns (cloud backend), steeper learning curve than declarative tools, state management adds operational complexity |
| **Opportunities** | Strong position for platform engineering, AI-assisted IaC (Pulumi AI/Neo), multi-cloud unification |
| **Threats** | OpenTofu competition for Terraform refugees, pricing model may push smaller teams away, complexity overhead |

**Templating:** General-purpose programming languages define resources as code.
**Env promotion:** Stacks (isolated instances per environment) with per-stack config.
**Secrets:** Native encrypted secrets in state, Pulumi ESC for environment-level secret management. Best-in-class for secrets among these tools.
**Dependencies:** Automatic from code structure. Pulumi builds a dependency DAG.
**Drift:** `pulumi refresh` detects drift. Kubernetes Operator provides continuous reconciliation.

### Timoni

| | |
|---|---|
| **Strengths** | CUE language provides genuine type safety and schema validation, modules + bundles model is clean, built-in drift detection and correction, no large state stored in cluster secrets (unlike Helm), intelligent patching (only changed objects) |
| **Weaknesses** | Immature and APIs still breaking, CUE hasn't achieved critical mass, tiny community, no GitOps controller yet (planned), documentation is sparse |
| **Opportunities** | If CUE takes off, Timoni is well-positioned, addresses real Helm pain points |
| **Threats** | CUE adoption is the existential risk, could remain a niche experiment, Stefan Prodan (primary author) moved focus |

**Templating:** CUE language with type constraints, validation, and code generation.
**Env promotion:** Modules parameterized per environment, bundles compose multiple modules.
**Secrets:** Runtime attributes, SOPS-encrypted files, CUE string interpolation from external stores.
**Dependencies:** Module and bundle composition.
**Drift:** Built-in detection and correction. Can review diffs before applying.

## Feature Comparison Matrix

| Feature | Helm | Kustomize | Jsonnet/Tanka | cdk8s | Pulumi | Timoni |
|---|---|---|---|---|---|---|
| **Learning curve** | Medium | Low | High | Medium | High | High |
| **Ecosystem size** | Huge | Large (built-in) | Small | Tiny | Medium | Tiny |
| **Type safety** | None | None | Partial | Full | Full | Full |
| **Native secrets** | No | No | No | No | Yes | Partial |
| **Drift detection** | Plugin | kubectl diff | tk diff | No | Yes | Yes |
| **Package distribution** | Charts/OCI | No | jsonnet-bundler | Constructs | Packages | Modules/OCI |
| **GitOps integration** | Excellent | Excellent | Good | Good | Good | Evolving |
| **2025 momentum** | Stable/dominant | Stable | Declining | Stalled | Growing | Niche |

## For This Project

**Recommendation: Stay with Helm for kube-prometheus-stack. Use plain manifests or Kustomize for custom components. Don't change anything.**

Rationale for this specific PoC:

1. **We're consuming, not authoring charts.** The kube-prometheus-stack is a Helm chart. That's a fact of the ecosystem, not a choice. Ripping it out to use another tool would mean reimplementing thousands of lines of tested configuration.

2. **Custom components are simple.** The OpenSLO integration, webhook agent service, and example exerciser services are small enough that plain `kubectl apply -f manifests/` or a Kustomize base/overlay is perfectly adequate.

3. **This is a PoC designed to be thrown away.** Adding cdk8s, Pulumi, or Timoni would mean learning a new tool before doing the actual work. The tool choice should be invisible at PoC stage.

4. **Namespace isolation is trivial with any tool.** None of these tools make namespace isolation meaningfully easier or harder. It's a `metadata.namespace` field.

5. **Practical approach:**
   - `helm install` for kube-prometheus-stack with a custom `values.yaml`
   - `kustomize` or plain manifests for our custom resources (PrometheusRule CRDs, ServiceMonitors, webhook deployment)
   - A `Makefile` tying it all together (which we already have)

If this PoC graduates to production, revisit the tooling question then. The right time to pick a sophisticated IaC tool is when you have multiple environments, multiple teams, and actual operational pain. Not before.

## Gemini's Take

*Raw analysis from Gemini (2026-02-28):*

Gemini provided a comprehensive, balanced SWOT analysis of all six tools. Key points from Gemini's assessment:

- **Helm** is the de facto standard with the largest ecosystem. Templating complexity and secret management are primary weaknesses.
- **Kustomize** is Kubernetes-native and template-free, ideal for GitOps workflows. Lacks programming logic for complex scenarios.
- **Jsonnet/Tanka** offers strong programmability and abstraction. Learning curve and smaller ecosystem are barriers.
- **cdk8s** brings programming language benefits (type safety, testing) but still generates YAML and lacks native deployment.
- **Pulumi** provides full IaC across clouds with best-in-class secrets management but is complex and has pricing concerns.
- **Timoni** is the most modern option with CUE-based type safety and built-in drift detection, but is immature with potential breaking changes.

Gemini's conclusion was diplomatic: "The choice largely depends on team expertise, existing workflows, the complexity of configurations, and the desired level of abstraction." It noted the industry trend toward GitOps, enhanced secrets management, and proactive drift detection across all tools.

<details>
<summary>Full Gemini analysis (click to expand)</summary>

### Helm (Gemini)
- **S:** Powerful Go-template templating, package management via charts, dependency management, release management (versioning, rollbacks), widespread adoption
- **W:** Templating complexity, YAML-as-text processing, no native secrets management, configuration drift potential, learning curve
- **O:** Advanced secrets integration (Vault, ESO), proactive drift detection, AI/ML workload management
- **T:** Security vulnerabilities in charts, uncontrolled drift, evolving tool landscape

### Kustomize (Gemini)
- **S:** Kubernetes native (built into kubectl), template-free YAML, declarative overlays, granular customization, dynamic ConfigMap/Secret generation
- **W:** No programming language, manual dependency management, patch complexity at scale, limited secret encryption
- **O:** GitOps integration excellence, improved env promotion, enhanced drift detection, components feature
- **T:** Configuration drift without GitOps enforcement, security concerns for secrets, custom scripting workarounds

### Jsonnet/Tanka (Gemini)
- **S:** Programmability with functions/conditionals/deep merge, modularity through libraries, environment management, reliable diffing (tk diff)
- **W:** DSL learning curve, less widespread adoption, no native secrets, jsonnet-bundler tooling overhead
- **O:** Suited for increasing K8s complexity, GitOps alignment, integration with AI/ML workloads
- **T:** Competition from other tools, potential native K8s enhancements reducing DSL need, community fragmentation

### cdk8s (Gemini)
- **S:** Programming language benefits (type safety, autocompletion, testing), reusable constructs, multi-language support, CRD management
- **W:** Still synthesizes to YAML, verbose without cdk8s+, no native deployment mechanism, learning curve for constructs
- **O:** GitOps integration for generated YAML, custom orchestration, constructs hub growth
- **T:** YAML debugging challenges persist, competition, adoption effort

### Pulumi (Gemini)
- **S:** Code-driven IaC, strong K8s SDK, Pulumi ESC for secrets, environment isolation via stacks, multi-cloud, AI-assisted operations
- **W:** Steeper learning curve, backend pricing, smaller community, drift if changes occur outside Pulumi
- **O:** GitOps adoption growth, platform engineering rise, policy-as-code, AI integration
- **T:** Terraform/OpenTofu competition, K8s complexity, evolving security threats, skills gap

### Timoni (Gemini)
- **S:** CUE-powered type safety and validation, modules/bundles modularity, performance (intelligent patching), built-in drift detection, comprehensive lifecycle management, flexible secrets
- **W:** APIs still breaking, CUE learning curve, GitOps integration evolving, external dependency management evolving
- **O:** Growing demand for type-safe config, planned GitOps controller, community growth, Helm alternative
- **T:** Intense competition, tied to CUE adoption, development pace concerns, perception challenges

</details>

## Claude's Take

### Where I disagree with Gemini

1. **Gemini is too generous to Jsonnet/Tanka.** In 2025/2026 reality, Tanka's adoption has stalled. It's essentially a Grafana Labs internal tool that happens to be open source. Unless you're deploying Grafana's own products (Loki, Mimir, Tempo), there's no compelling reason to adopt it. The Jsonnet talent pool is vanishingly small. Gemini presents it as a viable option for "large-scale, complex projects" -- I'd say it's only viable if you're already committed to the Grafana ecosystem.

2. **Gemini significantly underestimates cdk8s's trajectory problems.** The "Constructs Hub" never materialized into a meaningful ecosystem. AWS has effectively deprioritized it. The project still exists but momentum is near-zero. Gemini frames it as appealing for teams who "prefer code-over-config" but doesn't mention that Pulumi has won that niche decisively.

3. **Gemini's Helm assessment understates the ecosystem lock-in.** The real strength of Helm isn't its templating (which is genuinely bad). It's that virtually every infrastructure component ships as a Helm chart first. Prometheus, cert-manager, ingress-nginx, ArgoCD, Vault -- they all have official Helm charts. This isn't a feature of Helm; it's an ecosystem fact that makes Helm unavoidable for consuming third-party software.

4. **Gemini overstates Timoni's near-term viability.** CUE is intellectually interesting but hasn't crossed the adoption chasm. Timoni's primary author (Stefan Prodan, who also created Flux) has limited bandwidth. For production use in 2025/2026, Timoni is a gamble, not an option.

### What Gemini misses

1. **The Helm + Kustomize combo is the pragmatic default.** In practice, most production K8s deployments use Helm for consuming community charts and Kustomize for custom resources and last-mile patching. ArgoCD and Flux both support this pattern natively. Gemini presents these as competing alternatives rather than complementary tools.

2. **Plain manifests are underrated.** For small projects, custom services, and PoCs, a directory of YAML files with `kubectl apply -k` or just `kubectl apply -f` is perfectly fine. The industry over-indexes on tooling. If you have 3-5 custom resources, you don't need a tool. You need a directory.

3. **The real decision axis is "consuming vs. authoring."** If you're consuming community charts: Helm is mandatory, not a choice. If you're authoring config for your own services: Kustomize or plain YAML for simple cases, Pulumi or Helm for complex cases. Gemini frames this as a single choice when it's actually two separate decisions.

4. **GitOps tool choice matters more than config tool choice.** Whether you pick ArgoCD or Flux will shape your config management approach more than whether you pick Helm or Kustomize. Both GitOps tools have opinions about how config should be structured, and fighting those opinions is painful.

### My opinionated 2025/2026 ranking

For a **new project starting today**:

1. **Helm + Kustomize** -- pragmatic default, covers 90% of use cases
2. **Pulumi** -- if you need cloud infra + K8s in one tool and have engineering capacity
3. **Plain manifests** -- if you have < 10 custom resources and no env promotion needs
4. **Timoni** -- watch but don't adopt yet
5. **Jsonnet/Tanka** -- only if you're deep in Grafana ecosystem
6. **cdk8s** -- don't pick this for new projects
