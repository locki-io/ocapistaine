# WebSocket Fix for ocapistaine.vaettir.locki.io

## Current Problem

WebSocket connections to `wss://ocapistaine.vaettir.locki.io/_stcore/stream` are failing with errors:
- "WebSocket connection failed"
- Browser console shows repeated connection attempts

This prevents Streamlit from working properly through the proxy.

## Root Cause

The nginx proxy on vaettir is missing WebSocket upgrade headers required for Streamlit's real-time communication.

## Solution Steps

### Step 1: SSH to Vaettir

```bash
ssh jnxmas@vaettir.locki.io
cd ~/vaettir
```

### Step 2: Backup Current Config

```bash
cp proxy-configs/ocapistaine.conf.template proxy-configs/ocapistaine.conf.template.backup
```

### Step 3: Update Proxy Configuration

Edit the proxy config:

```bash
nano proxy-configs/ocapistaine.conf.template
```

Replace the entire content with:

```nginx
# WebSocket upgrade support - CRITICAL for Streamlit
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 80;

    # DNS resolver for dynamic upstream
    resolver 8.8.8.8 8.8.4.4 valid=300s ipv6=off;

    location / {
        # Target ngrok URL (from environment variable)
        proxy_pass ${OCAPISTAINE_TARGET_URL};

        # ====== WebSocket Support (REQUIRED for Streamlit) ======
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        # ====== Streaming Configuration ======
        # Disable buffering for real-time updates
        proxy_buffering off;
        proxy_cache off;

        # Prevent response body buffering
        proxy_request_buffering off;

        # ====== Standard Proxy Headers ======
        proxy_set_header Host ocapistaine.ngrok-free.app;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;

        # ====== SSL Configuration for Ngrok ======
        proxy_ssl_server_name on;
        proxy_ssl_name ocapistaine.ngrok-free.app;
        proxy_ssl_protocols TLSv1.2 TLSv1.3;

        # ====== Timeouts (Important for WebSocket) ======
        # Connection timeout
        proxy_connect_timeout 60s;

        # Timeout for sending data to upstream
        proxy_send_timeout 300s;

        # Timeout for reading from upstream (LONG for WebSocket)
        proxy_read_timeout 300s;

        # Keep WebSocket connections alive
        send_timeout 300s;
    }

    # Health check endpoint
    location /_stcore/health {
        proxy_pass ${OCAPISTAINE_TARGET_URL}/_stcore/health;
        proxy_http_version 1.1;
        proxy_set_header Host ocapistaine.ngrok-free.app;
    }
}
```

Save and exit (Ctrl+O, Enter, Ctrl+X in nano).

### Step 4: Rebuild and Restart Proxy

```bash
# Rebuild with new configuration
docker compose build ocapistaine

# Restart with production profile
docker compose --profile production --profile proxy up -d ocapistaine

# Verify it's running
docker compose ps ocapistaine
```

### Step 5: Check Logs

```bash
# Watch logs for errors
docker compose logs -f ocapistaine

# Press Ctrl+C to exit when satisfied

# Or check last 50 lines
docker compose logs ocapistaine --tail 50
```

### Step 6: Verify Configuration

```bash
# Check that nginx loaded the config correctly
docker exec vaettir-ocapistaine-1 cat /etc/nginx/nginx.conf | head -30

# Should see the "map $http_upgrade" block at the top
```

### Step 7: Test WebSocket Connection

From your local machine:

```bash
# Test the WebSocket endpoint
curl -I https://ocapistaine.vaettir.locki.io/_stcore/stream

# Expected: "426 Upgrade Required" (this is CORRECT)
# Bad: 403 Forbidden or 502 Bad Gateway
```

### Step 8: Test in Browser

```bash
open https://ocapistaine.vaettir.locki.io
```

Check browser console (F12):
- Network tab → Filter "WS" → Look for `_stcore/stream` with status "101 Switching Protocols"
- Console should NOT show "WebSocket connection failed" errors

## Verification Checklist

- [ ] Nginx config backed up
- [ ] New config with WebSocket headers applied
- [ ] Docker container rebuilt and restarted
- [ ] Container is running (docker compose ps shows "Up")
- [ ] Logs show no nginx errors
- [ ] curl test returns 426 (not 403 or 502)
- [ ] Browser shows WebSocket connected (status 101)
- [ ] Streamlit app works without "JavaScript required" message
- [ ] No repeated WebSocket errors in browser console

## Troubleshooting

### Container Won't Start

```bash
# Check for config syntax errors
docker compose logs ocapistaine --tail 100

# Common issue: nginx syntax error
# Fix: Review the config for typos
```

### Still Getting WebSocket Errors

```bash
# 1. Verify nginx config was actually updated
docker exec vaettir-ocapistaine-1 cat /etc/nginx/nginx.conf | grep "map \$http_upgrade"

# Should show the map block. If not, rebuild wasn't successful.

# 2. Check that environment variable is set
docker exec vaettir-ocapistaine-1 env | grep OCAPISTAINE_TARGET_URL

# Should show: OCAPISTAINE_TARGET_URL=https://ocapistaine.ngrok-free.app

# 3. Force recreate container
docker compose --profile production --profile proxy up -d --force-recreate ocapistaine
```

### 502 Bad Gateway

```bash
# Check ngrok is running and reachable
curl -I https://ocapistaine.ngrok-free.app

# Should return 200 OK

# If not, check your local machine:
curl http://localhost:4040/api/tunnels | jq '.tunnels[0].public_url'

# Verify it shows: https://ocapistaine.ngrok-free.app
```

## Rollback Plan

If something goes wrong:

```bash
# Restore backup
cp proxy-configs/ocapistaine.conf.template.backup proxy-configs/ocapistaine.conf.template

# Rebuild and restart
docker compose build ocapistaine
docker compose --profile production --profile proxy up -d ocapistaine
```

## Related Documentation

- [PROXY_MANAGEMENT.md](docs/docs/orchestration/PROXY_MANAGEMENT.md) - Comprehensive proxy management guide
- [STREAMLIT_SETUP.md](docs/docs/app/STREAMLIT_SETUP.md) - Streamlit CORS and configuration
- [Streamlit WebSocket Docs](https://docs.streamlit.io/develop/concepts/architecture/architecture#client-server-communication)
- [Nginx WebSocket Proxying](http://nginx.org/en/docs/http/websocket.html)

## Notes

- This fix is permanent - it will survive container restarts
- The configuration file is version controlled in the vaettir repo
- Consider committing the change: `git add proxy-configs/ && git commit -m "Add WebSocket support for Streamlit"`
