# Deployment

Demo target: a single GCP `e2-standard-4` instance (4 vCPU, 16 GB RAM, ~€100/month). All components run on one box for the demo. Production scale-out is documented but out of scope for the June 2026 pitch.

## Topology

```
                          Greek operator's browser
                                   ↓
                          ┌──────────────────┐
                          │  nginx :443      │  TLS termination, static assets,
                          │  (systemd)       │  reverse proxy to FastAPI
                          └────────┬─────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                ↓                  ↓                  ↓
    ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
    │  uvicorn :8000 │  │  Neo4j :7687   │  │  Ollama :11434 │
    │  (systemd)     │  │  (systemd)     │  │  (systemd)     │
    │                │  │                │  │                │
    │  FastAPI app   │  │  Graph store   │  │  Local LLM     │
    │  + WS broker   │  │                │  │                │
    └────────────────┘  └────────────────┘  └────────────────┘
                  ↓
        ┌─────────────────┐
        │  GCP Secret Mgr │  ← all .env values, mounted at runtime
        └─────────────────┘
```

Everything runs on the same instance. No external dependencies at runtime — that's the sovereignty story. Only outbound calls during the demo are to **MapLibre's CARTO tile CDN** (which we'd swap for self-hosted Protomaps in production hardening — see "Sovereignty hardening" below).

## Steps

### 1. Provision the instance

```bash
gcloud compute instances create damocles \
    --machine-type=e2-standard-4 \
    --zone=europe-west3-a \
    --image-family=debian-12 \
    --image-project=debian-cloud \
    --boot-disk-size=100GB \
    --boot-disk-type=pd-balanced \
    --tags=http-server,https-server
```

For a GPU-backed deployment (recommended for Ollama 8B with sub-3-second agent latency):

```bash
gcloud compute instances create damocles-gpu \
    --machine-type=n1-standard-4 \
    --accelerator=type=nvidia-tesla-t4,count=1 \
    --zone=europe-west3-c \
    --maintenance-policy=TERMINATE \
    --image-family=debian-12-cuda \
    --image-project=ml-images \
    --boot-disk-size=200GB
```

### 2. Bootstrap the OS

SSH in and run:
```bash
sudo bash <(curl -fsSL https://raw.githubusercontent.com/<your-org>/damocles/main/scripts/setup_linux.sh)
```

[`scripts/setup_linux.sh`](../scripts/setup_linux.sh) installs:
- Python 3.12 + system build tools
- Docker (for Neo4j fallback if not running natively)
- Node.js 20 LTS (for `npm run build`)
- `uv` (Python package manager)
- Ollama (`curl -fsSL https://ollama.com/install.sh | sh`)
- nginx
- Pulls a known-good Neo4j 5.24 image

### 3. Install the application

```bash
git clone <repo> /opt/damocles
cd /opt/damocles
uv sync                                    # Python deps
npm --prefix frontend ci                   # frontend deps (production install)
npm --prefix frontend run build            # → frontend/dist/
uv run python -m spacy download el_core_news_lg
```

### 4. Wire secrets via GCP Secret Manager

Map every `.env` field to a GCP secret. Don't deploy the `.env` file itself — it shouldn't exist on the prod instance.

```bash
# Once per environment, in your build pipeline or operator workstation:
echo -n "$GEMINI_API_KEY"            | gcloud secrets create damocles-gemini-key       --data-file=-
echo -n "$SENTINELHUB_CLIENT_ID"     | gcloud secrets create damocles-sh-client-id     --data-file=-
echo -n "$SENTINELHUB_CLIENT_SECRET" | gcloud secrets create damocles-sh-client-secret --data-file=-
echo -n "$TELEGRAM_API_ID"           | gcloud secrets create damocles-tg-api-id        --data-file=-
echo -n "$TELEGRAM_API_HASH"         | gcloud secrets create damocles-tg-api-hash      --data-file=-
echo -n "$TELEGRAM_PHONE"            | gcloud secrets create damocles-tg-phone         --data-file=-
echo -n "$AISSTREAM_API_KEY"         | gcloud secrets create damocles-aisstream-key    --data-file=-
echo -n "$NEO4J_PASSWORD"            | gcloud secrets create damocles-neo4j-password   --data-file=-
```

Grant the instance's service account `secretAccessor` on each:
```bash
for s in damocles-gemini-key damocles-sh-client-id damocles-sh-client-secret \
         damocles-tg-api-id damocles-tg-api-hash damocles-tg-phone \
         damocles-aisstream-key damocles-neo4j-password ; do
    gcloud secrets add-iam-policy-binding $s \
        --member="serviceAccount:damocles-runtime@<project>.iam.gserviceaccount.com" \
        --role="roles/secretmanager.secretAccessor"
done
```

The systemd unit (next step) reads them at start-up via the GCP metadata server.

### 5. systemd units

Three services. All read secrets from Secret Manager via a small helper script.

**`/etc/systemd/system/damocles-secrets.sh`** — fetches secrets at start, exports as env vars:
```bash
#!/usr/bin/env bash
set -euo pipefail
fetch() { gcloud secrets versions access latest --secret="$1" 2>/dev/null; }

cat > /run/damocles.env <<EOF
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_DEVIL_MODEL=qwen2.5:7b

GEMINI_API_KEY=$(fetch damocles-gemini-key)
SENTINELHUB_CLIENT_ID=$(fetch damocles-sh-client-id)
SENTINELHUB_CLIENT_SECRET=$(fetch damocles-sh-client-secret)
TELEGRAM_API_ID=$(fetch damocles-tg-api-id)
TELEGRAM_API_HASH=$(fetch damocles-tg-api-hash)
TELEGRAM_PHONE=$(fetch damocles-tg-phone)
AISSTREAM_API_KEY=$(fetch damocles-aisstream-key)

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=$(fetch damocles-neo4j-password)

DAMOCLES_ENV=production
LOG_LEVEL=INFO
DEMO_MODE=true
EOF
chmod 600 /run/damocles.env
```

**`/etc/systemd/system/neo4j.service`**:
```ini
[Unit]
Description=Damocles Neo4j
After=network.target

[Service]
Type=forking
User=neo4j
ExecStart=/usr/share/neo4j/bin/neo4j start
ExecStop=/usr/share/neo4j/bin/neo4j stop
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/ollama.service`** (installer creates this; just `systemctl enable ollama`):
```ini
[Service]
ExecStart=/usr/local/bin/ollama serve
Environment="OLLAMA_HOST=127.0.0.1:11434"
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/damocles-backend.service`**:
```ini
[Unit]
Description=Damocles backend (uvicorn)
After=network.target neo4j.service ollama.service
Requires=neo4j.service ollama.service

[Service]
Type=simple
User=damocles
WorkingDirectory=/opt/damocles
ExecStartPre=/etc/systemd/system/damocles-secrets.sh
EnvironmentFile=/run/damocles.env
ExecStart=/opt/damocles/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Bring everything up:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now neo4j ollama damocles-backend
journalctl -u damocles-backend -f          # follow logs
```

### 6. Pull Ollama models

```bash
ollama pull llama3.1:8b                    # primary reasoning, ~4.7 GB
ollama pull qwen2.5:7b                     # devil's advocate, ~4.4 GB
ollama pull llama3.2:3b                    # fast watch-query parser, ~2.0 GB
```

Or use the helper: [`scripts/download_models.sh`](../scripts/download_models.sh).

Total disk: ~12 GB. First cold inference is ~5 s longer than subsequent (model load into VRAM/RAM).

### 7. nginx

`/etc/nginx/sites-available/damocles`:
```nginx
server {
    listen 80;
    server_name damocles.eyp.gr;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name damocles.eyp.gr;

    # TLS — replace with your cert / Let's Encrypt
    ssl_certificate     /etc/letsencrypt/live/damocles.eyp.gr/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/damocles.eyp.gr/privkey.pem;

    # Static frontend assets (built via `npm run build`)
    root /opt/damocles/frontend/dist;
    index index.html;

    # Single-page app — fall back to index.html for non-asset routes
    location / { try_files $uri $uri/ /index.html; }

    # FastAPI proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Static evidence files (SAR PNGs)
    location /static/ {
        proxy_pass http://127.0.0.1:8000;
    }

    # WebSocket upgrade for the progress stream
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 300s;
    }

    # Content Security Policy — adjust for your tile source
    add_header Content-Security-Policy "
        default-src 'self';
        script-src 'self' 'unsafe-inline' 'unsafe-eval';
        style-src 'self' 'unsafe-inline';
        img-src 'self' data: https://basemaps.cartocdn.com;
        connect-src 'self' https://basemaps.cartocdn.com wss://damocles.eyp.gr;
        font-src 'self' data:;
        worker-src 'self' blob:;
    " always;
}
```

The CSP `connect-src` includes `basemaps.cartocdn.com` while we ship the hosted CARTO style. Drop it once self-hosted Protomaps is wired (next section).

```bash
sudo ln -s /etc/nginx/sites-available/damocles /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 8. TLS

```bash
sudo certbot --nginx -d damocles.eyp.gr
```

Certbot installs cron auto-renewal. Verify with:
```bash
sudo certbot renew --dry-run
```

### 9. Firewall

GCP firewall rule allowing 80/443 only:
```bash
gcloud compute firewall-rules create damocles-web \
    --allow tcp:80,tcp:443 \
    --target-tags=http-server,https-server
```

Block everything else by default. The instance's internal services (Neo4j 7687, Ollama 11434, uvicorn 8000) are bound to `127.0.0.1`, so they're not reachable externally even without firewall rules.

### 10. Deploy

```bash
# On dev box
git push origin main

# On prod instance
ssh damocles@damocles.eyp.gr
cd /opt/damocles
git pull
uv sync
npm --prefix frontend ci
npm --prefix frontend run build
sudo systemctl restart damocles-backend
```

Total downtime per deploy: ~3 seconds. uvicorn picks up changes on restart; nginx keeps serving the static frontend during the brief gap.

For zero-downtime: run two instances behind a GCP load balancer. Out of scope for the demo.

## Sovereignty hardening (production-only)

The June 2026 demo runs on the topology above with the following caveats acknowledged:

### Map tiles — swap CARTO for self-hosted Protomaps
- Today: `mapStyle = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"` (free hosted style)
- Production: download a Protomaps `.pmtiles` extract for the Greek/Aegean AOI (~1-2 GB), serve with the `pmtiles` server on `127.0.0.1`, swap the style URL.
- Same MapLibre style format. Zero outbound calls. No CSP `connect-src` exception needed.
- Documented in [limitations.md §6.1](limitations.md).

### LLM — confirmed Ollama-only at the demo
The plan's hard rule: **the demo's LLM_PROVIDER must be `ollama`**. Gemini is dev-only.
- Test the swap before the demo: edit `/run/damocles.env` to `LLM_PROVIDER=ollama`, `sudo systemctl restart damocles-backend`, run [`scripts/test_e2e.py`](../scripts/test_e2e.py). All 22 assertions must pass.
- Latency budget per agent call: ~3-5 s on T4 GPU, ~30-60 s on CPU only. Demo budget per watch: 60 s. **GPU is required for a smooth demo.**

### Audit chain — external anchoring
- Ship the daily root hash to a public bulletin (OpenTimestamps + Bitcoin, or a national PKI). See [audit.md §"External anchoring"](audit.md).
- A determined operator with full host access can rewrite both stores atomically; external anchoring closes that gap.

### Auth — wire OIDC at the API edge
- Today the audit log's `actor` is a literal string set by the executor; the citation-chain endpoint logs as `"analyst"`.
- Production: front the API with an OIDC dependency (FastAPI's `OAuth2AuthorizationCodeBearer`), pass the verified principal into every audit `actor` field. Per-actor signing of audit entries closes the impersonation gap.
- Documented in [limitations.md §5d.1](limitations.md).

### `/static/` evidence files — wrap in auth + audit
- Today: `StaticFiles(directory=settings.cache_dir)` serves SAR PNGs to anyone reaching port 8000.
- Production: replace with a custom router that (a) authenticates, (b) logs `evidence.served`, (c) optionally rate-limits. The frontend `EvidenceModal` then fetches via authenticated `axios` instead of a raw `<img src>`.

## Backup + restore

### Neo4j
```bash
# Hot backup (file-system snapshot — Neo4j must be stopped)
sudo systemctl stop neo4j
tar czf neo4j-$(date +%Y%m%d).tar.gz -C /var/lib/neo4j data/
sudo systemctl start neo4j

# Or: APOC export at runtime (no downtime)
# Cypher: CALL apoc.export.cypher.all("/var/lib/neo4j/import/full.cypher", {})
```

### Audit log
```bash
# JSONL is append-only, easy to back up incrementally
rsync -av /opt/damocles/data/audit_log.jsonl backup-host:/srv/damocles-audit/

# Daily snapshot to Cloud Storage
gsutil cp /opt/damocles/data/audit_log.jsonl gs://damocles-audit/$(date +%Y/%m/%d)/audit.jsonl
```

### SAR cache
The `data/cache/sar/*.png` files are evidence the Brief points at via `sar_tile_id`. If the cache is wiped, future EvidenceModal opens for vessels will show "No SAR tile cached". Back up if you care about historical reproducibility:
```bash
rsync -av /opt/damocles/data/cache/sar/ gs://damocles-evidence/sar/
```

## Monitoring

Minimal viable monitoring:

| Signal | How to check | Action |
| --- | --- | --- |
| Backend health | `curl https://damocles.eyp.gr/health` | Page if !ok |
| Audit chain integrity | `curl https://damocles.eyp.gr/api/audit/verify` | **Page immediately if !verified** — this is a security event |
| Neo4j liveness | `cypher-shell "RETURN 1"` | Restart neo4j unit |
| Ollama ready | `curl http://127.0.0.1:11434/api/tags` | Restart ollama unit |
| Disk usage on `/opt/damocles/data` | `df -h` | SAR cache grows ~50 MB/watch; rotate quarterly |

GCP Monitoring + Cloud Logging picks up uvicorn / nginx / systemd logs automatically once `google-cloud-logging` is configured (out of scope for the demo).

## Cost forecast

`e2-standard-4` (no GPU): ~€100/month
`n1-standard-4` + T4 GPU: ~€250/month sustained, ~€100/month if you `gcloud compute instances stop` outside demo hours

External services at runtime:
- **Sentinel Hub**: free tier (30k PU/month) covers ~2-3 demo runs/day forever
- **GDELT**: free, unlimited
- **AISStream**: free tier (1 connection)
- **Telegram**: free
- **OpenSky**: free, anonymous endpoint covers the demo

Total runtime cost: **the GCP instance only**. The "this costs zero to run" claim from the demo's [4:45] is essentially true (€100-250/mo amortised).

## What can break in production that doesn't break in dev

These are flagged in [limitations.md](limitations.md) but worth listing here:

1. **Multi-worker uvicorn breaks the in-memory event broker** ([§5c.1](limitations.md)). Either stay on `--workers 1` (fine for the demo) or swap the broker for Redis pub/sub.
2. **Hard process crash leaves Watches in `processing` forever** ([§5c.2](limitations.md)). Add a startup sweeper that marks stuck Watches as `error`.
3. **Telegram first-run interactive auth doesn't work in headless** ([§4c.1](limitations.md)). Run the auth on a VPS-with-shell once, copy the `.session` file to the prod instance, restart.
4. **Audit chain not externally anchored** ([§5d.3](limitations.md)). Add the OpenTimestamps daily-root publication.
5. **Cross-store drift between JSONL and Neo4j** ([§5d.2](limitations.md)). Build the reconcile CLI before going live.

## Smoke test on the prod instance

After every deploy:
```bash
# Backend health
curl -fsS https://damocles.eyp.gr/health | jq .

# Audit chain
curl -fsS https://damocles.eyp.gr/api/audit/verify | jq .

# Frontend serves
curl -fsS https://damocles.eyp.gr/ | grep -q "DAMOCLES" && echo OK

# Re-seed if needed (DESTRUCTIVE)
ssh damocles@damocles.eyp.gr "cd /opt/damocles && uv run python scripts/seed_neo4j.py"
```

Or run the full e2e regression remotely (requires opening a tunnel for the WS):
```bash
ssh -L 8000:127.0.0.1:8000 damocles@damocles.eyp.gr -N &
uv run python scripts/test_e2e.py    # hits localhost:8000 → tunnel → instance
```

22/22 assertions must pass. If any fail: do not start the demo.

## What's NOT covered here

- High availability / multi-region — out of scope
- Disaster recovery runbooks beyond the backup commands above
- Compliance certifications (ISO 27001, SOC 2) — production deployment by EYP would need their own
- Penetration testing
- Capacity planning beyond the single demo box

These belong in a separate operations playbook to be built post-demo.
