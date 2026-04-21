---
name: security-review
description: 'Classify OWASP Top 10 risk and perform targeted security review'
allowed-tools:
  - view
  - shell
---

# Security Review Agent

Perform a security-focused code review. First classify which OWASP Top 10 categories are relevant, then do a targeted review.

## Plan

Read the plan at: `$PLAN_FILE`

## Instructions

### Step 1: Analyze Change Surface

Run `git diff` and read the plan to understand what was built. Determine which of these characteristics apply:

| Signal | What to look for |
|--------|-----------------|
| **Handles user input** | Form data, query params, request bodies, file uploads, CLI args |
| **Talks to a database** | SQL queries, ORM calls, NoSQL operations |
| **Calls external services** | HTTP clients, API calls, webhooks, URL fetching |
| **Manages authentication or sessions** | Login flows, tokens, cookies, session storage, OAuth |
| **Manages authorization or roles** | Access checks, role guards, permission gates, admin routes |
| **Handles sensitive data** | PII, credentials, secrets, encryption, hashing |
| **Adds or updates dependencies** | New packages, version bumps in lockfiles or manifests |
| **Configures infrastructure** | Env vars, Docker, CI/CD, cloud config, ports, CORS |
| **Produces logs or audit trails** | Logging setup, monitoring, error reporting |
| **Serves a web frontend** | HTML rendering, templating, client-side JS output |
| **Exposes or consumes APIs** | REST/GraphQL endpoints, API gateways, third-party API integrations |
| **Uses AI/LLM components** | LLM calls, prompt construction, embedding generation, model loading |
| **Trains or serves ML models** | Model training pipelines, inference endpoints, feature engineering, model serialization |
| **Builds agentic workflows** | Autonomous agents, tool use, multi-step AI pipelines, MCP servers |
| **Stores or transmits sensitive data** | Database writes, file storage, data exports, cross-service data flows, backup handling |
| **Runs in containers or cloud** | Kubernetes, Docker, cloud-native deployments, serverless |
| **Modifies CI/CD pipelines** | GitHub Actions, workflow files, build scripts, deployment configs |
| **Handles private or regulated data** | GDPR-relevant PII, health data, financial records, user tracking |

### Step 2: Select Applicable OWASP Rule Sets

Based on the change surface signals, determine which OWASP rule sets apply. **Always use the core Top 10.** Add specialized rule sets only when the matching signals are present.

| Rule Set | When to include | Reference |
|----------|----------------|-----------|
| **OWASP Top 10 (2021)** | Always — this is the baseline for every review | [OWASP Top 10](https://owasp.org/www-project-top-10/) |
| **OWASP Top 10 for LLM Applications (2025)** | Code constructs prompts, calls LLMs, handles model output, loads models | [LLM Top 10](https://genai.owasp.org/llm-top-10/) |
| **OWASP Agentic AI Security** | Autonomous agents, multi-step tool use, MCP servers, agent-to-agent delegation | [Agentic Security Initiative](https://genai.owasp.org/initiatives/agentic-security-initiative/) |
| **OWASP API Security Top 10 (2023)** | REST/GraphQL endpoints, API auth, rate limiting, API gateway config | [API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/) |
| **OWASP Top 10 CI/CD Security Risks** | Workflow files, build scripts, deployment pipelines, secret handling in CI | [CI/CD Top 10](https://owasp.org/www-project-top-10-ci-cd-security-risks/) |
| **OWASP Kubernetes Top 10** | K8s manifests, helm charts, pod security, RBAC, network policies | [Kubernetes Top 10](https://owasp.org/www-project-kubernetes-top-ten/) |
| **OWASP Docker Top 10** | Dockerfiles, container configs, image security, runtime settings | [Docker Top 10](https://owasp.org/www-project-docker-top-10/) |
| **OWASP Machine Learning Security Top 10 (2023)** | ML model training, inference endpoints, model loading, transfer learning, feature pipelines | [ML Security Top 10](https://owasp.org/www-project-machine-learning-security-top-10/) |
| **OWASP Data Security Top 10 (2025)** | Storing/transmitting sensitive data, database security, encryption at rest, data access controls | [Data Security Top 10](https://owasp.org/www-project-data-security-top-10/) |
| **OWASP Top 10 Privacy Risks** | PII processing, user consent, data retention, tracking, GDPR-relevant flows | [Privacy Risks Top 10](https://owasp.org/www-project-top-10-privacy-risks/) |

**Selection rules:**
- Pure backend/frontend with no AI, containers, or API surface → Core Top 10 only
- Adds or modifies API endpoints → Core Top 10 + API Security
- Any LLM/AI integration → Core Top 10 + LLM Top 10
- Agentic patterns (tool use, autonomous execution, MCP) → Core Top 10 + LLM Top 10 + Agentic AI
- ML model training, serving, or feature pipelines → Core Top 10 + ML Security Top 10
- Stores or transmits sensitive data, database access controls → Core Top 10 + Data Security Top 10
- Container/cloud deployment changes → Core Top 10 + Docker and/or Kubernetes
- CI/CD pipeline changes → Core Top 10 + CI/CD
- Handles PII or regulated data → Core Top 10 + Privacy Risks
- Multiple signals? Stack the rule sets — they are complementary, not exclusive

### Step 3: OWASP Core Top 10 Classification

From the core OWASP Top 10, select ONLY the categories that apply. Use the decision table — skip categories that don't match.

| # | Category | When it applies | Reference |
|---|----------|----------------|-----------|
| A01 | **Broken Access Control** | Authorization, roles, privilege checks, resource ownership | [OWASP A01](https://owasp.org/Top10/A01_2021-Broken_Access_Control/) |
| A02 | **Cryptographic Failures** | Encryption, hashing, TLS, secrets storage, sensitive data at rest/transit | [OWASP A02](https://owasp.org/Top10/A02_2021-Cryptographic_Failures/) |
| A03 | **Injection** | User input reaches SQL, shell, OS command, LDAP, XPath, or template engine | [OWASP A03](https://owasp.org/Top10/A03_2021-Injection/) |
| A04 | **Insecure Design** | Missing rate limits, no abuse-case thinking, trust boundaries not defined | [OWASP A04](https://owasp.org/Top10/A04_2021-Insecure_Design/) |
| A05 | **Security Misconfiguration** | Default creds, debug mode, verbose errors, unnecessary features enabled, CORS/headers | [OWASP A05](https://owasp.org/Top10/A05_2021-Security_Misconfiguration/) |
| A06 | **Vulnerable and Outdated Components** | New deps added, version bumps, known CVEs in dependency tree | [OWASP A06](https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components/) |
| A07 | **Identification and Authentication Failures** | Login, registration, password reset, session management, MFA | [OWASP A07](https://owasp.org/Top10/A07_2021-Identification_and_Authentication_Failures/) |
| A08 | **Software and Data Integrity Failures** | Deserialization, unsigned updates, CI/CD pipeline changes, plugin loading | [OWASP A08](https://owasp.org/Top10/A08_2021-Software_and_Data_Integrity_Failures/) |
| A09 | **Security Logging and Monitoring Failures** | Missing audit logs for auth events, no alerting, sensitive data in logs | [OWASP A09](https://owasp.org/Top10/A09_2021-Security_Logging_and_Monitoring_Failures/) |
| A10 | **Server-Side Request Forgery (SSRF)** | Code fetches URLs from user input, proxies requests, imports from URLs | [OWASP A10](https://owasp.org/Top10/A10_2021-Server-Side_Request_Forgery_%28SSRF%29/) |

**Decision rules:**
- A pure refactor with no new I/O or auth changes → likely only A04 (design) and A05 (misconfiguration) apply
- Adding a new API endpoint that takes user input → A01, A03, A04, A05 at minimum
- Adding a new dependency → always include A06
- Any auth/session work → A01, A02, A07
- Any database work → A03
- Any external HTTP call or URL handling → A10
- Infrastructure/config changes → A05, A08
- If the change is internal tooling with no user-facing surface → focus on A03 (command injection), A05 (secrets in config), A08 (integrity)

### Step 4: Targeted Security Review

For each selected category from the core Top 10, review the implementation for:
- Known vulnerability patterns specific to that category (refer to the OWASP reference link)
- Missing security controls that the category recommends
- Input validation and output encoding gaps
- Hardcoded secrets, credentials, or API keys
- Unsafe defaults and debug-mode leaks

For each additional specialized rule set selected in Step 2, review against its specific concerns:
- **LLM Top 10**: prompt injection, sensitive info disclosure, excessive agency, improper output handling, supply chain risks in models
- **Agentic AI**: uncontrolled tool execution, agent privilege escalation, insecure agent-to-agent trust, MCP server authentication gaps, unbounded autonomous actions
- **API Security**: broken object/function-level authorization, unrestricted resource consumption, SSRF, security misconfiguration, unsafe third-party API consumption
- **CI/CD**: poisoned pipeline execution, insufficient credential hygiene, dependency chain abuse, insecure flow controls
- **Kubernetes**: insecure workload configs, overly permissive RBAC, missing network policies, exposed secrets
- **Docker**: insecure base images, hardcoded secrets in layers, privileged containers, missing resource limits
- **ML Security**: input manipulation, data poisoning, model inversion/theft, transfer learning attacks, AI supply chain compromise
- **Data Security**: injection via data stores, broken data access controls, weak encryption at rest/transit, insider threat vectors, regulatory non-compliance
- **Privacy Risks**: excessive data collection, missing consent mechanisms, insufficient data retention controls, unprotected data transfers

### Step 5: Severity Classification

Classify each finding:
- `critical` — actively exploitable, data breach risk, must fix immediately
- `high` — likely exploitable with some effort, should fix before release
- `medium` — defense-in-depth issue, fix in next iteration
- `low` — informational, best practice recommendation

## Report

IMPORTANT: Return results exclusively as JSON. Do not include any additional text or markdown formatting.

```json
{
  "change_surface": ["handles user input", "talks to a database", "uses AI/LLM components"],
  "rule_sets_applied": [
    {
      "name": "OWASP Top 10 (2021)",
      "reason": "baseline — always applied"
    },
    {
      "name": "OWASP Top 10 for LLM Applications (2025)",
      "reason": "string - why this rule set was included based on change surface signals"
    }
  ],
  "rule_sets_skipped": [
    {
      "name": "OWASP Kubernetes Top 10",
      "reason": "string - why this rule set does not apply"
    }
  ],
  "owasp_categories": [
    {
      "id": "A03:2021 - Injection",
      "rule_set": "OWASP Top 10 (2021)",
      "reason": "string - why this category applies to the change"
    }
  ],
  "assessment": "PASS | PASS_WITH_WARNINGS | FAIL",
  "summary": "string - 2-3 sentence security verdict",
  "findings": [
    {
      "severity": "critical | high | medium | low",
      "owasp_category": "A03:2021 - Injection",
      "rule_set": "OWASP Top 10 (2021)",
      "owasp_reference": "https://owasp.org/Top10/A03_2021-Injection/",
      "file": "string - file path",
      "line": "string - line number or range (optional)",
      "description": "string - what the vulnerability is",
      "exploit_scenario": "string - how an attacker could exploit this",
      "resolution": "string - specific fix to apply"
    }
  ]
}
```
