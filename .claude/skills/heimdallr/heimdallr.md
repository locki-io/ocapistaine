---
name: heimdallr
description: "OCapistaine traffic control — Traefik proxy for cap.audierne2026.fr, geo-filtering, rate limiting, and access control via vaettir VPS."
---

# Heimdallr — OCapistaine Incarnation

## Current State (2026-03-11)

| Component | Status |
|-----------|--------|
| **Render app** | LIVE at `ocapistaine.onrender.com` |
| **DNS** | `cap.audierne2026.fr` CNAME → `vaettir.locki.io` (VPS) |
| **Traefik rule** | NOT YET CONFIGURED — traffic hits VPS but no route to Render |
| **Geo-filter** | NOT YET — needs Traefik GeoBlock plugin on VPS |
| **SSL** | Pending — Traefik ACME will auto-provision once routing is live |

## Architecture

```
cap.audierne2026.fr
  → CNAME vaettir.locki.io (213.136.85.11)
  → Traefik on VPS
     → GeoBlock middleware (FR only)
     → RateLimit middleware (30 req/s)
     → Proxy to https://ocapistaine.onrender.com
```

## VPS Details

- **Server**: vaettir.locki.io (213.136.85.11)
- **Repo**: `/Users/jnxmas/dev/vaettir/` (local), bare repo on VPS
- **Docker compose**: `docker-compose.yml` + `docker-compose.override.yml`
- **Traefik**: Already running (serves docs.locki.io, other services)
- **Git remote for docs**: `vps` = `jnxmas@vaettir.locki.io:repos/docs.locki.io.git`

## Setup TODO

1. **Add Traefik GeoBlock plugin** to `traefik.yml` or docker-compose static config
2. **Add MaxMind GeoLite2 database** (free, requires registration at maxmind.com)
3. **Add ocapistaine-proxy service** to vaettir `docker-compose.yml`:
   - Route: `Host(\`cap.audierne2026.fr\`)`
   - Middlewares: geo-fr, rate-limit
   - Backend: `https://ocapistaine.onrender.com`
4. **Test SSL**: Traefik ACME should auto-provision cert for `cap.audierne2026.fr`
5. **Verify**: `curl -I https://cap.audierne2026.fr` returns 200 from France, 403 from elsewhere

## CORS Alignment

`cap.audierne2026.fr` is already in CORS origins:
- `render.yaml` (Streamlit allowed origins)
- `app/main.py` (FastAPI CORS middleware)
- `.env.example` (documentation)

## Toggle Commands (once configured)

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
