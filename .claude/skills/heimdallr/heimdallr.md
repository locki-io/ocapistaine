---
name: heimdallr
description: "OCapistaine traffic control and realm preservation — Traefik proxy, geo-filtering, backup/restore of n8n workflows and PostgreSQL, and access control via vaettir VPS."
---

# Heimdallr — OCapistaine Incarnation

## Current State (2026-03-12)

| Component | Status |
|-----------|--------|
| **Render app** | LIVE at `ocapistaine.onrender.com` |
| **DNS** | `cap.audierne2026.fr` CNAME → `vaettir.locki.io` (VPS) |
| **Traefik routing** | ✅ LIVE — `ocap-citizen` router on `ocapistaine` service |
| **SSL** | ✅ Auto-provisioned by Traefik ACME (no manual step needed) |
| **WebSocket** | ✅ Fixed — Origin header override in nginx proxy config |
| **Geo-filter** | NOT YET — needs Traefik GeoBlock plugin on VPS |
| **Backup** | ✅ Fresh backup 2026-03-11 before deploy |

## Architecture

```
cap.audierne2026.fr
  → CNAME vaettir.locki.io (213.136.85.11)
  → Traefik on VPS (SSL termination, router: ocap-citizen)
     → nginx proxy container (ocapistaine service, port 80)
        → proxy_pass https://ocapistaine.onrender.com
           → Render CDG edge (cf-ray confirms Paris)
```

## VPS Details

- **Server**: vaettir.locki.io (213.136.85.11)
- **Repo**: `/Users/jnxmas/dev/vaettir/` (local), `~/vaettir` on VPS
- **Docker compose**: `docker-compose.yml` + `docker-compose.override.yml`
- **Traefik**: Running (serves docs.locki.io, vaettir.locki.io, mail.lockilabs.com, cap.audierne2026.fr)
- **Git remote for docs**: `vps` = `jnxmas@vaettir.locki.io:repos/docs.locki.io.git`

## Deployment History

### Step 1 — Routing (2026-03-11) ✅

Added second Traefik router to existing `ocapistaine` service in `docker-compose.yml`:

```yaml
# Router 2: citizen-facing subdomain (Heimdallr gate)
- "traefik.http.routers.ocap-citizen.rule=Host(`cap.audierne2026.fr`)"
- "traefik.http.routers.ocap-citizen.entrypoints=websecure"
- "traefik.http.routers.ocap-citizen.tls=true"
- "traefik.http.routers.ocap-citizen.tls.certresolver=myresolver"
- "traefik.http.routers.ocap-citizen.service=ocapistaine"
```

No new service, no new proxy-config. Same nginx container, same Render backend. Just a second hostname on the same door.

### Step 1b — WebSocket Fix (2026-03-12) ✅

**Problem**: `wss://cap.audierne2026.fr/_stcore/stream` failed — Streamlit rejected cross-origin WebSocket.

**Root cause**: Browser sends `Origin: https://cap.audierne2026.fr`, but Render/Streamlit expects `Origin: https://ocapistaine.onrender.com`. Same pattern as the ngrok WebSocket issue documented in `docs/docs/orchestration/WEBSOCKET_FIX.md`.

**Fix**: Added one line to `proxy-configs/ocapistaine.conf.template` **on the VPS** (gitignored file):

```nginx
proxy_set_header Origin https://ocapistaine.onrender.com;
```

Then rebuilt the proxy container:
```bash
docker compose build ocapistaine
docker compose --profile proxy up -d ocapistaine
```

**Lesson learned**: Every new hostname routed through the proxy needs the Origin header override. The WebSocket upgrade headers (`Upgrade`, `Connection`) were already present — the missing piece is always the `Origin` rewrite. This applies to Render, ngrok, or any backend that validates the Origin header.

### Step 1c — SSL Certificate (2026-03-11) ✅

Traefik logs showed `No ACME certificate generation required for domains ["cap.audierne2026.fr"]` — cert was already in `acme.json` from DNS pointing to the VPS. No manual manipulation needed this time.

**Key insight from `SELF_HOSTED_DOCS.md`**: When adding a new service/router, Traefik may need a restart to discover the new labels and trigger ACME. The sequence is:
1. Deploy container with Traefik labels
2. Ensure DNS points to VPS
3. `docker compose --profile production restart traefik`
4. Traefik discovers route → triggers ACME → cert issued

### Step 1d — Docker Build Fix (2026-03-11) ✅

Build failed with `permission denied` on `docker-data/dms/mail-state/spool-postfix/active` — Docker build context tried to read mailserver spool files owned by root.

**Fix**: Added `.dockerignore` on VPS:
```
docker-data/
PRIVATE_backups/
PRIVATE_security/
```

## Setup TODO

### Geo-Filtering (Step 2 — TODO)
1. **Add Traefik GeoBlock plugin** to docker-compose static config
2. **Add MaxMind GeoLite2 database** (free, requires registration at maxmind.com)
3. **Add geo-fr middleware** to `ocap-citizen` router labels
4. **Verify**: 200 from France, 403 from elsewhere

## CORS Alignment

`cap.audierne2026.fr` is already in CORS origins:
- `render.yaml` (Streamlit allowed origins)
- `app/main.py` (FastAPI CORS middleware)
- `.env.example` (documentation)

## Proxy Config — Gitignored Files

Proxy configs in `proxy-configs/` are **server-specific and gitignored**. Only `agent.conf.template.example` and `error-offline.html.template` are tracked.

To edit the live config, SSH to the VPS:
```bash
ssh jnxmas@vaettir.locki.io
nano ~/vaettir/proxy-configs/ocapistaine.conf.template
docker compose build ocapistaine
docker compose --profile proxy up -d ocapistaine
```

**Current ocapistaine.conf.template critical headers:**
```nginx
proxy_set_header Host ocapistaine.onrender.com;          # SNI routing
proxy_set_header Origin https://ocapistaine.onrender.com; # WebSocket Origin override
proxy_set_header Upgrade $http_upgrade;                   # WebSocket upgrade
proxy_set_header Connection $connection_upgrade;          # WebSocket connection
```

## Toggle Commands (once geo-filter configured)

```bash
# Check current state
ssh jnxmas@vaettir.locki.io "docker compose exec traefik traefik healthcheck"

# France only (default for elections)
# → set allowCountries: ["FR"] in docker-compose labels

# Maintenance mode
# → set allowCountries: [] (empty = block all)

# Open to all
# → remove geo-filter middleware from router
```

## The Keep — Vaettir Realm Preservation

### Assets Under Guard

| Asset | What | Volume/Location | Criticality |
|-------|------|-----------------|-------------|
| **n8n workflows** | All automation flows, credentials, execution history | `vaettir_postgres_data` | CRITICAL |
| **n8n settings** | Custom nodes, config | `vaettir_n8n_data` | HIGH |
| **Traefik certs** | Let's Encrypt ACME certs for all domains | `traefik_data` | MEDIUM (auto-regenerates) |
| **Mail data** | Mailserver state | `docker-data/dms/` | HIGH |
| **Config** | `.env`, `docker-compose.yml` | `~/vaettir/` | HIGH (secrets) |

### Backup Procedure

```bash
# From /Users/jnxmas/dev/vaettir/
./scripts/PRIVATE_backup.sh            # Full: db + volumes + config → PRIVATE_backups/
./scripts/PRIVATE_backup.sh db-only    # Quick: postgres dump only
./scripts/PRIVATE_restore.sh <file>    # Restore from archive
```

### Pre-Deploy Sequence (MANDATORY)

```bash
# 1. Backup
cd /Users/jnxmas/dev/vaettir && ./scripts/PRIVATE_backup.sh

# 2. Push
git push origin main dev

# 3. Deploy (VPS may need HTTPS remote if SSH key not configured)
ssh jnxmas@vaettir.locki.io 'cd ~/vaettir && git pull && docker compose --profile proxy --profile production up -d --build'

# 4. Verify
curl -I https://vaettir.locki.io          # n8n
curl -I https://docs.locki.io             # docs
curl -I https://cap.audierne2026.fr       # citizen gate
```

### Gotchas Log

| Issue | Cause | Fix |
|-------|-------|-----|
| Docker build `permission denied` | Build context reads `docker-data/dms/` (root-owned) | `.dockerignore` excluding `docker-data/`, `PRIVATE_*` |
| WebSocket `onerror` on new hostname | Origin header mismatch (browser vs backend) | `proxy_set_header Origin https://ocapistaine.onrender.com` in nginx |
| `git pull` fails on VPS | SSH key not configured for GitHub | Switch remote to HTTPS: `git remote set-url origin https://...` |
| New router not discovered | Traefik reads labels at startup only | `docker compose --profile production restart traefik` |
| Submodule not populated | `git pull` doesn't update submodules | `git submodule init && git submodule update --remote docs` |
