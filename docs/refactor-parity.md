# Refactor Parity Notes

Use this document when reviewing behavior-preserving refactor passes. Public HTTP
routes, response shapes, status codes, API-key behavior, generated peer config
formats, and protocol configuration keys should stay stable unless a PR
explicitly declares a functional change.

## Endpoint Contract

| Method | Path | Auth | Request | Current success response | Current error behavior |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/health` | none | none | `{"app": "Amnezia API", "status": "running"}` | standard FastAPI errors |
| `GET` | `/peers/` | `X-API-Key` | optional `app_type`, `online_only` query params | list of peer summaries with traffic and online status | `401` invalid API key, `400` invalid `app_type`, `500` unexpected service error |
| `POST` | `/peers/` | `X-API-Key` | `{"app_type": "amnezia_vpn" \| "amnezia_wg"}` | created peer keys, allocated IP, endpoint, protocol, app type, config | `401` invalid API key, `422` invalid enum payload, `400` service validation, `500` unexpected service error |
| `PATCH` | `/peers/` | `X-API-Key` | `public_key` plus new `app_type` | old/new public key, preserved allocated IP, protocol, app type, config | `401`, `404` missing peer, `422` invalid enum payload, `400` service validation, `500` unexpected service error |
| `DELETE` | `/peers/` | `X-API-Key` | `{"public_key": "..."}` | deleted status and public key | `401`, `404` missing peer, `500` unexpected service error |
| `GET` | `/server/status` | `X-API-Key` | none | running/stopped container status, UDP port, interface, protocol | `401`, `500` unexpected service error |
| `GET` | `/server/traffic` | `X-API-Key` | none | aggregate RX/TX bytes and peer counts | `401`, `500` unexpected service error |
| `POST` | `/server/restart` | `X-API-Key` | none | restarted status and message | `401`, `400` stopped container, `500` unexpected service error |

## Protocol Fixture Coverage

- WireGuard dump parsing is pinned by `tests/services/test_amneziawg2_config_helpers.py`; it covers endpoint mapping, allowed IP parsing, handshake timestamps, traffic counters, keepalive, and online/offline status.
- Raw config mutation is pinned by helper and service tests; peer removal must remove only the matching `[Peer]` section and leave unrelated sections untouched.
- App type metadata is stored as `# AppType = ...` in peer sections. Unknown or missing metadata falls back to the configured default app type.
- IP allocation currently preserves existing IPv4-only behavior: it reads the interface subnet, skips the server address, skips used peer IPv4 addresses, and returns the next `/32`.
- Generated `vpn://` payload and AmneziaWG text config parity are pinned by golden-style assertions in the config generator and service tests.

## Review Checklist

Each refactor PR should state:

- current behavior being preserved;
- structural improvement being made;
- validation command, normally `make test`;
- whether OpenAPI output or golden config fixtures changed;
- any intentionally deferred migration such as dependency upgrades, API versioning, Docker command execution changes, or startup lifecycle changes.
