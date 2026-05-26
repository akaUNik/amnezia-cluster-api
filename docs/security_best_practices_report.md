# Security Best Practices Report

Date: 2026-05-26

## Executive Summary

The service protects operational routes with an `X-API-Key` header and disables OpenAPI routes when `DEVELOPMENT=false`, which are good baseline controls. The main risks are concentrated around secret exposure, privileged Docker/container access, shell execution helpers, and production hardening gaps. Because this API can create VPN peers, return client private keys, write protocol configuration, and restart containers, compromise of the API key or the app process has a high operational impact.

## Critical Findings

### [FIXED] SEC-001: Full API key is written to application logs

- Rule ID: FASTAPI-AUTH / secret logging
- Severity: Critical
- Location: `src/main.py`, `lifespan`, lines 25-26
- Evidence:
  ```python
  api_key = get_api_key_storage().get_api_key()
  logger.info(f"The API key was successfully installed: {api_key}")
  ```
- Impact: Anyone with access to container logs, centralized logging, terminal scrollback, or support bundles can obtain the admin API key and call protected endpoints that create peer credentials, inspect peer state, and restart the configured Amnezia container.
- Fix: Never log the API key. Log only that a key exists or was generated, then rotate any key that may already have appeared in logs.
- Mitigation: Restrict log access, scrub historical logs, and rotate `API_KEY` immediately if this service has been run in a shared or production environment.
- False positive notes: This is an actual secret disclosure in app code; severity depends on who can access logs.

## High Findings

### [IGNORE] SEC-002: Privileged Docker socket and host mounts create a large blast radius

- Rule ID: deployment hardening / least privilege
- Severity: High
- Location: `docker-compose.yml`, lines 8-13; `src/Dockerfile`, lines 1-19
- Evidence:
  ```yaml
  ports:
    - 8000:8000
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
    - /opt/amnezia:/opt/amnezia:rw
    - ./.env:/app/.env:rw
  ```
  ```dockerfile
  FROM python:3.13-slim
  ...
  CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```
- Impact: An application-level code execution flaw, dependency exploit, or leaked API key can become host/container control because the container can talk to Docker and write Amnezia configuration. The service is also published directly on all interfaces by the compose file.
- Fix: Keep the API behind a private network, VPN, or reverse proxy allowlist. Replace direct Docker socket access with a narrow Docker socket proxy or a small privileged sidecar exposing only the operations needed. Run the app as a non-root user and mount only the exact paths required.
- Mitigation: Firewall port 8000, restrict source IPs, use host-level logging/auditing for Docker API calls, and keep the Docker socket out of deployments that do not need container restart/status features.
- False positive notes: The mounts appear intentional for this product, but they are privileged and should be treated as part of the trusted computing base.

### [FIXED] SEC-003: Shell helpers execute interpolated command strings in privileged contexts

- Rule ID: FASTAPI-CMD-001 / command injection prevention
- Severity: High
- Location: `src/services/host_service.py`, `run_command` and `read_file`, lines 20-58 and 114-115; `src/services/management/container_connection.py`, `run_command`, `read_file`, `write_file`, validators, and Docker archive helpers, lines 56-286; `src/services/protocols/amneziawg2/amneziawg2_connection.py`, lines 16-78
- Evidence:
  ```python
  process = await asyncio.create_subprocess_exec(*args, ...)
  ```
  ```python
  container.exec_run(cmd=list(argv), ...)
  ```
  ```python
  archive_stream, _ = container.get_archive(path)
  container.put_archive(parent_dir, tar_stream.getvalue())
  ```
  ```python
  await self.run_command(["wg", "pubkey"], input_data=f"{private_key.strip()}\n")
  ```
- Impact: Any attacker-controlled or misconfigured value that reaches these helpers can alter shell syntax. Because the helpers run on the host or inside the Amnezia container and the app has Docker access, successful injection could read/write sensitive files or execute arbitrary commands in a privileged environment.
- Fix: Replaced host shell execution with `create_subprocess_exec()`, replaced container `sh -c` execution with argv-based Docker exec, moved container file reads/writes to Docker archive APIs, passed WireGuard stdin data through Docker exec stdin, and added strict validation for protocol-controlled `container_name`, `interface`, and container paths.
- Mitigation: Treat `protocols.yaml` and env-controlled paths as privileged configuration. Limit write access to `.env`, `protocols.yaml`, and `/opt/amnezia` to trusted administrators only.
- False positive notes: The primary remote routes do not currently pass arbitrary request strings directly into these helpers. The finding is still high risk because the sink is privileged and several inputs come from deployment/config files and container file contents.

### [FIXED] SEC-004: Raw internal exception messages are returned to API clients

- Rule ID: FASTAPI-ERR-001 / information disclosure
- Severity: High
- Location: `src/api/v1/server/router.py`, lines 42-47, 67-72, and 95-100; `src/api/v1/peers/crud/create.py`, lines 44-49; `src/api/v1/peers/crud/read.py`, lines 51-56; `src/api/v1/peers/crud/update.py`, lines 52-57; `src/api/v1/peers/crud/delete.py`, lines 37-42
- Evidence:
  ```python
  raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=str(exc),
  )
  ```
- Impact: Authenticated clients can receive Docker errors, command stderr, filesystem paths, container names, protocol configuration details, and other internals. If the API key leaks, this helps an attacker refine follow-on attacks.
- Fix: Added a shared internal server error helper, changed unexpected 500 handlers to return `"internal server error"`, logged detailed exceptions internally with static messages, and added regression tests proving sensitive exception strings are not returned to clients.
- Mitigation: Preserve specific 400/404 validation messages where they are intentionally user-actionable; avoid exposing stack, command, path, or container internals for unexpected failures.
- False positive notes: This API is admin-oriented, so some operational detail may be acceptable. Unexpected exception strings should still be treated as sensitive.

## Medium Findings

### [FIXED] SEC-005: API key comparison is not constant-time and has no visible brute-force controls

- Rule ID: FASTAPI-AUTH-001 / API key hardening
- Severity: Medium
- Location: `src/management/security.py`, `verify_api_key`, lines 90-94; `src/api/v1/management/middlewares/auth.py`, lines 27-104; `src/management/settings.py`, lines 11-14
- Evidence:
  ```python
  provided_digest = hashlib.sha256(provided_key.encode("utf-8")).digest()
  stored_digest = hashlib.sha256(stored_key.encode("utf-8")).digest()
  return secrets.compare_digest(provided_digest, stored_digest)
  ```
- Impact: Direct string comparison could leak timing differences, and lack of rate limiting made repeated invalid key attempts harder to control.
- Fix: Replaced direct comparison with fixed-length SHA-256 digest comparison via `secrets.compare_digest()`. Added an in-memory failed-auth limiter keyed by client host, returning HTTP 429 after repeated failures. The defaults are configurable with `API_KEY_FAILED_AUTH_LIMIT`, `API_KEY_FAILED_AUTH_WINDOW_SECONDS`, and `API_KEY_FAILED_AUTH_BLOCK_SECONDS`.
- Mitigation: Restrict API access to trusted networks and rotate keys periodically.
- False positive notes: Timing attacks may be hard to exploit over noisy networks, but the implemented change is low-cost and appropriate for a single shared admin key. Deployments should still prefer proxy or firewall rate limiting for distributed attacks.

### [FIXED] SEC-006: Outbound sync uses dedicated central credentials and URL validation

- Rule ID: FASTAPI-SSRF-001 / secret exfiltration via outbound requests
- Severity: Medium
- Location: `src/services/peers_service.py`, `sync_peers_status`, lines 171-209, and `_validate_sync_url`, lines 211-238; `src/management/settings.py`, lines 16-18; `.env.example`, lines 20-24
- Evidence:
  ```python
  sync_url = (central_api_url or self.settings.central_api_url or "").strip()
  sync_api_key = (central_api_key or self.settings.central_api_key or "").strip()
  headers = {"X-API-Key": sync_api_key}
  ```
  ```env
  # CENTRAL_API_URL=https://central-api.example.com/api/v1
  # CENTRAL_API_KEY=replace-with-dedicated-central-sync-key
  # CENTRAL_API_ALLOWED_HOSTS=central-api.example.com
  ```
- Impact: Before the fix, the local admin API key was sent to the configured central URL. If that URL was mistyped, downgraded to plaintext HTTP, controlled by an attacker, or changed through compromised deployment config, the admin key could be exposed.
- Fix: Replaced admin-key reuse with a separate `CENTRAL_API_KEY`, added `CENTRAL_API_ALLOWED_HOSTS`, fail-fast URL validation, HTTPS enforcement outside development, credential/query/fragment rejection for the central URL, and explicit no-redirect outbound sync requests.
- Mitigation: Keep `CENTRAL_API_URL` unset unless sync is required. Use network policy or firewall rules to restrict outbound destinations.
- False positive notes: The URL is configuration-controlled, not request-controlled, so this is primarily a deployment/configuration risk.

### [FIXED] SEC-007: Production host-header and HTTPS enforcement are not visible in app code

- Rule ID: FASTAPI-HOST-001 / production baseline
- Severity: Medium
- Location: `src/main.py`, FastAPI app construction, lines 33-42
- Evidence:
  ```python
  app = FastAPI(...)
  ```
  No `TrustedHostMiddleware` or HTTPS redirect/proxy enforcement appears in the app.
- Impact: If this service is exposed directly, missing host validation can allow host-header abuse in some proxy and URL-generation scenarios. Missing HTTPS enforcement can expose API keys and generated peer private keys over plaintext transport.
- Fix: Added production-only `TrustedHostMiddleware` using `API_ALLOWED_HOSTS` or `SERVER_PUBLIC_HOST`, added optional `API_ENFORCE_HTTPS` app redirects, and added an nginx profile that terminates TLS and redirects HTTP to HTTPS before proxying to the API.
- Mitigation: Keep the API on a private interface or VPN-only network. Verify reverse proxy config before public exposure.
- False positive notes: These protections may exist outside this repository. If so, document the deployment requirement.

### [FIXED] SEC-008: Development defaults can expose OpenAPI docs if copied into production

- Rule ID: FASTAPI-OPENAPI-001
- Severity: Medium
- Location: `.env.example`, lines 1-4; `.env.production.example`; `src/main.py`, lines 65-68; README environment and Docker sections
- Evidence:
  ```env
  DEVELOPMENT=false
  ```
  ```python
  docs_url="/docs" if settings.development else None
  redoc_url="/redoc" if settings.development else None
  openapi_url="/openapi.json" if settings.development else None
  swagger_ui_parameters={"persistAuthorization": False}
  ```
- Impact: OpenAPI/Swagger exposure reveals all admin endpoints and enables browser-side persisted authorization when `DEVELOPMENT=true`. This is acceptable for local development but risky if the example `.env` is reused on a reachable server.
- Fix: Changed `.env.example` to default `DEVELOPMENT=false`, added `.env.production.example`, changed the local quick-start command to bind loopback, documented production setup with docs endpoints disabled, and disabled Swagger UI persisted authorization even in development.
- Mitigation: Do not expose `/docs`, `/redoc`, or `/openapi.json` on public deployments. Clear browser storage after using Swagger UI with an API key.
- False positive notes: The code correctly disables docs when `DEVELOPMENT=false`; the risk is deployment drift.

## Low Findings

### SEC-009: Dynamic protocol service imports depend on local configuration integrity

- Rule ID: configuration integrity
- Severity: Low
- Location: `src/services/management/protocol_factory.py`, lines 44-80 and 108-131; `src/management/settings.py`, line 15
- Evidence:
  ```python
  protocol_config_path: str = "src/management/protocols.yaml"
  ```
  ```python
  service_class_path = config["service_class"]
  module_path, class_name = service_class_path.rsplit(".", 1)
  module = importlib.import_module(module_path)
  service_class = getattr(module, class_name)
  ```
- Impact: A local attacker or deployment mistake that changes `PROTOCOL_CONFIG_PATH` or `protocols.yaml` can influence which Python class is imported at startup.
- Fix: Restrict `service_class` to a static registry of known protocol implementations instead of arbitrary import paths.
- Mitigation: Keep protocol configuration owned by root or deployment automation and read-only to the app where possible.
- False positive notes: This is not remotely exploitable through the current API surface.

## Positive Observations

- Protected routers are attached with `Depends(get_current_api_key)` at router registration in `src/main.py` lines 45-57.
- Authentication uses a header-based API key scheme in `src/api/v1/management/middlewares/auth.py` lines 7-18.
- `/health` is the only intentionally public route in `src/main.py` lines 59-64.
- YAML loading uses `yaml.safe_load()` in `src/services/management/protocol_factory.py` line 56.
- No CORS middleware is configured, which is a safer default for a non-browser admin API.
- `.env` is ignored by Git via `.gitignore` line 117, and no tracked `.env`, `.pem`, or `.key` files were found.

## Recommended Remediation Order

1. Remove API key logging, rotate the current key, and scrub logs where possible.
2. Replace generic `detail=str(exc)` on unexpected 500s with generic messages.
3. Harden deployment: private network or reverse proxy allowlist, non-root container user, Docker socket proxy or sidecar.
4. Refactor shell helpers to use argv-style execution and strict config validation.
5. Add `compare_digest`, auth failure rate limiting, and key rotation guidance.
6. Split outbound sync credentials from the admin API key and require HTTPS for sync in production.
7. Document production-only host/TLS requirements and `DEVELOPMENT=false`.
