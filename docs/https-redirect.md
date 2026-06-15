# HTTPS redirect — DeltaTrack (deltatrack.agoradmv.org)

If `http://deltatrack.agoradmv.org/...` loads without redirecting, fix **Apache**
first. The app cannot see whether the browser used HTTP unless the proxy tells it.

## ISPConfig checklist

1. **Sites → Web Domain → deltatrack.agoradmv.org**
2. **SSL** + **Let's Encrypt** enabled
3. **Force HTTPS** enabled (belt-and-suspenders with the `RewriteRule` below)

## Apache Directives (paste entire block)

Replace whatever is in **Options → Apache Directives** with this — order matters:

```apache
# --- HTTP → HTTPS (no-op on :443 where %{HTTPS} is on) ---
RewriteEngine On
RewriteCond %{HTTPS} !=on
RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [R=301,L]

# --- Reverse proxy to uvicorn (127.0.0.1:8077) ---
ProxyRequests Off
ProxyPreserveHost On

RequestHeader set X-Forwarded-Proto "https" env=HTTPS
RequestHeader set X-Forwarded-Proto "http" env=!HTTPS

<Proxy *>
    Require all granted
</Proxy>

# ACME challenges must be served from disk, not proxied
ProxyPass        /.well-known  !
ProxyPass        /  http://127.0.0.1:8077/
ProxyPassReverse /  http://127.0.0.1:8077/

# Upload cap — keep aligned with MAX_UPLOAD_BYTES in server/app.py (150 MB)
LimitRequestBody 157286400

# Security headers
Header always set Content-Security-Policy "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
Header always set X-Content-Type-Options "nosniff"
Header always set Referrer-Policy "no-referrer"
Header always set X-Frame-Options "DENY"
```

Required Apache modules: `proxy`, `proxy_http`, `headers`, `rewrite`, `reqtimeout`.

Then:

```bash
sudo systemctl reload apache2
sudo systemctl restart deltatrack
```

## Verify

```bash
curl -sI http://deltatrack.agoradmv.org/index.html | head -5
```

Expect `301` and `Location: https://deltatrack.agoradmv.org/index.html`.

## What does *not* work on this deploy

| Mechanism | Why |
|---|---|
| `webapp/.htaccess` | Apache proxies everything to uvicorn; never reads disk |
| App middleware alone | Only redirects when forwarded headers signal cleartext |

The `RewriteRule` at the top of this block is the reliable fix.
