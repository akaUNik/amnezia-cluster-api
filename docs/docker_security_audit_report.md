# Docker Security Audit Report

Date: 2026-05-26

## Scope

Reviewed Docker and container runtime security for:

- `src/Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `nginx/templates/default.conf.template`
- Docker-related application access in `src/services/host_service.py` and `src/services/management/container_connection.py`
- Docker deployment notes in `README.md`

Validation performed:

- `docker --version`
- `docker compose config`
- `make smoke`
- Static review of Dockerfile, Compose mounts, nginx proxy configuration, build context exclusions, and Docker SDK usage.

## Executive Summary

The container setup is functional and keeps the direct API port bound to `127.0.0.1` by default, which is a good baseline for local development. The largest remaining risks are deployment and runtime hardening issues: the API container can access the host Docker socket and writes to `/opt/amnezia`. Those permissions appear intentional for the current product, but they make the API container part of the host trusted computing base.

The previous build-time issue around TLS certificate material entering the API image has been remediated. `.dockerignore` now excludes certificate and private key patterns, and `src/Dockerfile` copies only the runtime `src/` tree after dependency installation instead of copying the whole repository.

## Critical Findings

No critical Docker-specific findings were identified in this pass.

## High Findings

### DOCKER-001: TLS private keys can enter the API image build context

- Severity: High
- Status: Fixed
- Location: `src/Dockerfile`, lines 15; `.dockerignore`, lines 1-22; `docker-compose.yml`, lines 30-32; `README.md`, Docker section
- Previous evidence:
  ```dockerfile
  COPY . .
  ```
  ```text
  .dockerignore excludes .env, caches, and VCS files, but not nginx/certs or key material.
  ```
  ```yaml
  - ${NGINX_CERTS_PATH:-./nginx/certs}:/etc/nginx/certs:ro
  ```
- Impact: The README instructs production users to place `fullchain.pem` and `privkey.pem` under `NGINX_CERTS_PATH`, defaulting to `./nginx/certs`. If those files exist during `docker compose --profile nginx up --build`, Docker can send them in the API build context and `COPY . .` can bake them into the API image. Anyone with access to the image, image layers, registry, or build cache could recover the TLS private key.
- Remediation: Certificate and key material are now excluded from the build context:
  ```dockerignore
  nginx/certs/*
  !nginx/certs/.gitkeep
  *.pem
  *.key
  *.p12
  *.pfx
  id_rsa*
  id_ed25519*
  ```
  The API image also uses an explicit runtime copy:
  ```dockerfile
  COPY src ./src
  ```
- Mitigation: Keep production certificates outside the repository tree and set `NGINX_CERTS_PATH` to that external directory.
- False positive notes: Only `nginx/certs/.gitkeep` is present now. The issue appears when real certs are added for production as documented.

### DOCKER-002: API container has host-level control through the Docker socket

- Severity: High
- Status: Ignore
- Location: `docker-compose.yml`, line 13; `src/services/host_service.py`, lines 14, 62, 82, 106; `src/services/management/container_connection.py`, lines 51, 139, 184, 203, 260, 285
- Evidence:
  ```yaml
  - /var/run/docker.sock:/var/run/docker.sock
  ```
  ```python
  self.docker_client = docker.from_env()
  ```
- Impact: Docker socket access is effectively host-level control. If the API process is compromised through an application bug, dependency issue, leaked API key, or command execution path, an attacker can use Docker to inspect containers, mount host paths, start privileged containers, or alter running services.
- Recommended fix: Replace direct socket access with a narrow Docker socket proxy or a small privileged sidecar that exposes only the required operations, such as list/status/restart for the configured Amnezia container.
- Mitigation: Keep the API reachable only through a trusted network or reverse proxy allowlist, log Docker API access at the host level, and avoid mounting the socket in deployments that do not need container control.
- False positive notes: This access appears intentional because the API exposes container status and restart features. The finding is about blast radius, not accidental exposure.

### DOCKER-003: API container runs as root while holding privileged mounts

- Severity: High
- Status: Fixed
- Location: `src/Dockerfile`; `docker-compose.yml`
- Previous evidence:
  ```dockerfile
  FROM python:3.13-slim
  ...
  CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```
  No `USER` directive is set.
- Impact: The container runs as root by default. Combined with the Docker socket, writable `/opt/amnezia`, and writable `.env` mounts, any process compromise gets maximum practical container permissions and easier access to sensitive mounted files.
- Remediation: The image now creates a dedicated `app` user/group from UID/GID values defined in `src/Dockerfile`, adds only the Docker socket group configured in the Dockerfile, copies runtime files with `app:app` ownership, and switches to `USER app`. These values are intentionally kept out of the public `.env` examples.
- Mitigation: If direct Docker socket access blocks a non-root rollout, prioritize the sidecar/proxy change from `DOCKER-002`; otherwise non-root may give limited protection against the socket itself.
- False positive notes: Non-root does not neutralize Docker socket risk by itself, but it still reduces damage across the filesystem and accidental privilege use.

## Medium Findings

### DOCKER-004: Writable `.env` bind mount allows container-to-host secret persistence

- Severity: Medium
- Status: Fixed
- Location: `docker-compose.yml`; `src/management/security.py`; `src/management/settings.py`
- Previous evidence:
  ```yaml
  - ./.env:/app/.env:rw
  ```
  ```python
  api_key = self._generate_api_key()
  self._write_to_env_file(api_key)
  ```
- Previous impact: The app could write `API_KEY` into `.env`, which was convenient for first-run setup. In production, a compromised process could also modify a host-mounted environment file and potentially persist malicious configuration for later restarts.
- Remediation: `API_KEY` is now a required setting, the app no longer generates or writes keys into `.env`, and the API service no longer bind-mounts `.env`. Compose still uses `env_file: .env` to inject configuration into the container environment.
- Residual risk: Keep real `.env` files out of version control and prefer platform secrets for production deployments.

### DOCKER-005: Compose service lacks defense-in-depth runtime restrictions

- Severity: Medium
- Location: `docker-compose.yml`, lines 1-33
- Evidence: No `cap_drop`, `security_opt`, `read_only`, `tmpfs`, `pids_limit`, or resource limits are configured.
- Impact: If the application process is exploited, the container has a broad default Linux capability set and a writable root filesystem. The Docker socket still dominates the risk, but these controls reduce damage from non-Docker exploit paths and accidental writes.
- Recommended fix: Add restrictions where compatible:
  ```yaml
  security_opt:
    - no-new-privileges:true
  cap_drop:
    - ALL
  read_only: true
  tmpfs:
    - /tmp
  pids_limit: 256
  ```
- Mitigation: Test these incrementally because the app may need writable paths for runtime caches.
- False positive notes: Some controls may require small application or deployment changes before they can be enabled.

### DOCKER-006: Public nginx profile has no source allowlist or request rate limit

- Severity: Medium
- Location: `docker-compose.yml`, lines 18-33; `nginx/templates/default.conf.template`, lines 1-31
- Evidence:
  ```yaml
  ports:
    - 80:80
    - 443:443
  ```
  nginx terminates TLS and proxies to the API, but does not enforce IP allowlists or request rate limits.
- Impact: The public nginx profile exposes the admin API to any network that can reach ports 80 and 443. API key authentication remains required, but exposed admin endpoints are easier to brute force, scan, and probe.
- Recommended fix: Add source IP allowlists where deployments have known admin networks, and add nginx request limiting for authentication-protected routes.
- Mitigation: Use host firewall rules, VPN-only access, or a private load balancer when source IP allowlisting is not stable.
- False positive notes: App-level API key checks and host/TLS middleware reduce risk. Network-layer restriction is still appropriate for an administrative API.

### DOCKER-007: Base images are tag-pinned but not digest-pinned or scanned in this repo

- Severity: Medium
- Location: `src/Dockerfile`, lines 1 and 5; `docker-compose.yml`, line 19
- Evidence:
  ```dockerfile
  FROM python:3.13-slim
  COPY --from=ghcr.io/astral-sh/uv:0.10.5 /uv /uvx /bin/
  ```
  ```yaml
  image: nginx:stable-alpine
  ```
- Impact: Tags can move, and no repository-level container vulnerability scan is visible. Rebuilds may pick up changed base image contents without review, and known vulnerable packages may remain unnoticed.
- Recommended fix: Add a container scan step such as Trivy, Grype, Docker Scout, or equivalent in CI. Consider digest pinning for production builds and use automation to update digests deliberately.
- Mitigation: Rebuild regularly on base image security updates and keep `uv.lock` reviewed.
- False positive notes: Tag pinning is better than `latest`; digest pinning increases reproducibility but adds maintenance overhead.

## Low Findings

### DOCKER-008: Build context is broader than the runtime app needs

- Severity: Low
- Status: Fixed
- Location: `src/Dockerfile`, line 15; `.dockerignore`, lines 1-22
- Previous evidence:
  ```dockerfile
  COPY . .
  ```
- Remediation: The Dockerfile now copies only the runtime application tree:
  ```dockerfile
  COPY src ./src
  ```
- Mitigation: Keep sensitive local files out of the repository directory even if they are untracked.
- False positive notes: `.env`, Git metadata, cache directories, and bytecode are already excluded.

### DOCKER-009: Container health check is not defined in Compose

- Severity: Low
- Location: `docker-compose.yml`, lines 1-33
- Evidence: No `healthcheck` is configured for `api` or `nginx`.
- Impact: `restart: always` restarts crashed containers but does not detect a hung app, broken dependency, or failed HTTP health endpoint. This is primarily reliability, but stale unhealthy services can also hide failed security controls.
- Recommended fix: Add an API health check against `/health`, for example:
  ```yaml
  healthcheck:
    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 20s
  ```
- False positive notes: The app already exposes `/health`; Compose just does not use it.

## Positive Observations

- The direct API port is bound to loopback in Compose: `127.0.0.1:${API_PORT:-8000}:8000`.
- The nginx profile mounts certificates read-only into the nginx container.
- nginx redirects HTTP to HTTPS and proxies `X-Forwarded-Proto: https`.
- `.dockerignore` excludes `.env`, `.git`, virtual environments, Python bytecode, tool caches, TLS certificates, and common private key files.
- The Dockerfile uses `uv sync --locked --no-dev`, reducing dependency drift and excluding development dependencies.
- The API image now runs the application process as a dedicated non-root user.
- The general security report already documents that Docker socket access and `/opt/amnezia` writes are privileged operations.

## Recommended Remediation Order

1. Replace direct Docker socket mounting with a narrow proxy or privileged sidecar.
2. Make production configuration read-only and pre-provision `API_KEY` outside the container.
3. Add Compose runtime restrictions after testing compatibility.
4. Add a CI container vulnerability scan and define a base image update workflow.
5. Add nginx allowlisting/rate limiting for public deployments.
6. Add Compose health checks for `api` and `nginx`.

## Notes

This report is a static and configuration-level audit. It does not include a live image vulnerability scan.
