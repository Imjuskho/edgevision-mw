# EdgeVision-MW Production Deployment Guide

**Version:** 1.0.0
**Last Updated:** 2026-07-25
**Target:** api.edgevision.mw

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Infrastructure Provisioning](#2-infrastructure-provisioning)
3. [SSL and Domain Configuration](#3-ssl-and-domain-configuration)
4. [Environment Variable Hardening](#4-environment-variable-hardening)
5. [Database Setup](#5-database-setup)
6. [Staging Deployment](#6-staging-deployment)
7. [Production Deployment](#7-production-deployment)
8. [Post-Deployment Verification](#8-post-deployment-verification)
9. [Rollback Procedure](#9-rollback-procedure)
10. [Monitoring and Alerting](#10-monitoring-and-alerting)

---

## 1. Architecture Overview

```
                    ┌─────────────────────┐
                    │   Cloudflare CDN    │
                    │   (TLS Termination) │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │   Nginx Reverse     │
                    │   Proxy (:443→8000) │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
    ┌─────────▼──────┐ ┌─────▼──────┐ ┌──────▼─────┐
    │  FastAPI App   │ │  FastAPI   │ │  FastAPI   │
    │  (uvicorn)     │ │  App       │ │  App       │
    │  :8000         │ │  :8000     │ │  :8000     │
    └─────────┬──────┘ └─────┬──────┘ └──────┬─────┘
              │               │               │
              └───────────────┼───────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
    ┌─────────▼──────┐ ┌─────▼──────┐ ┌──────▼─────┐
    │  PostgreSQL 16 │ │  Redis 7   │ │  MinIO     │
    │  (Primary)     │ │  (Cache)   │ │  (S3)      │
    └────────────────┘ └────────────┘ └────────────┘
```

**Components:**
- **FastAPI App** — Business logic, JWT auth, rate limiting
- **PostgreSQL 16** — 12 tables, append-only consent/audit, FK constraints
- **Redis 7** — Rate limiter (sliding window), Celery broker, session cache
- **MinIO** — Object storage for images, datasets, exports
- **Celery Worker** — Async tasks: batch processing, dataset builds, PII scans
- **Celery Beat** — Scheduled tasks: daily audits, heartbeat checks

---

## 2. Infrastructure Provisioning

### Option A: Hetzner Cloud (Recommended — Cost-Effective)

**Why Hetzner:** €/performance ratio is 3-5x better than AWS for this workload. EU data center in Helsinki has <150ms latency to Lilongwe via submarine cable.

#### 2.1 Terraform Configuration

Create `infrastructure/hetzner/main.tf`:

```hcl
terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
  }
  backend "s3" {
    endpoints = { s3 = "https://fsn1.your-objectstorage.com" }
    bucket    = "edgevision-terraform-state"
    key       = "production/terraform.tfstate"
    region    = "fsn1"
    skip_metadata_api_check     = true
    skip_credentials_validation = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

# --- Variables ---
variable "hcloud_token" {
  type      = string
  sensitive = true
}

variable "ssh_public_key" {
  type = string
}

variable "domain" {
  default = "edgevision.mw"
}

# --- SSH Key ---
resource "hcloud_ssh_key" "deploy" {
  name       = "edgevision-deploy"
  public_key = var.ssh_public_key
}

# --- Firewall ---
resource "hcloud_firewall" "edgevision" {
  name = "edgevision-fw"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "8000"
    source_ips = []  # Internal only
  }
}

# --- Server ---
resource "hcloud_server" "app" {
  name        = "edgevision-prod"
  server_type = "cax31"       # 8 vCPU, 16GB RAM, ARM64 — enough for all services
  image       = "ubuntu-24.04"
  location    = "fsn1"
  ssh_keys    = [hcloud_ssh_key.deploy.id]
  firewall_ids = [hcloud_firewall.edgevision.id]
  user_data   = file("${path.module}/cloud-init.yaml")

  labels = {
    environment = "production"
    project     = "edgevision"
  }
}

# --- Volume (PostgreSQL data) ---
resource "hcloud_volume" "pg_data" {
  name     = "edgevision-pg-data"
  size     = 100            # 100GB SSD
  server_id = hcloud_server.app.id
  location  = "fsn1"
  automount = false
}

# --- Outputs ---
output "server_ip" {
  value = hcloud_server.app.ipv4_address
}

output "server_ipv6" {
  value = hcloud_server.app.ipv6_address
}
```

Create `infrastructure/hetzner/cloud-init.yaml`:

```yaml
#cloud-config
package_update: true
package_upgrade: true
packages:
  - docker.io
  - docker-compose-plugin
  - certbot
  - nginx
  - ufw
  - fail2ban
  - postgresql-client-16

users:
  - name: deploy
    groups: docker, sudo
    shell: /bin/bash
    ssh_authorized_keys:
      - ssh-ed25519 AAAA... your-deploy-key

write_files:
  - path: /etc/docker/daemon.json
    content: |
      {
        "log-driver": "json-file",
        "log-opts": { "max-size": "10m", "max-file": "3" },
        "storage-driver": "overlay2"
      }

runcmd:
  - systemctl enable docker
  - ufw allow 22,80,443/tcp
  - ufw --force enable
  - systemctl enable fail2ban
```

#### 2.2 Provisioning Steps

```bash
# 1. Initialize Terraform
cd infrastructure/hetzner
terraform init

# 2. Set secrets (NEVER commit these)
export HCLOUD_TOKEN="your-hetzner-api-token"
export TF_VAR_hcloud_token="$HCLOUD_TOKEN"
export TF_VAR_ssh_public_key="$(cat ~/.ssh/id_ed25519.pub)"

# 3. Plan and apply
terraform plan -out=tfplan
terraform apply tfplan

# 4. Record the IP
terraform output server_ip
# => "203.0.113.42"
```

### Option B: AWS (For Compliance Requirements)

If the buyer requires AWS (e.g., GovCloud, specific regions):

```hcl
# infrastructure/aws/main.tf — abbreviated
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "edgevision-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["eu-west-1a"]
  private_subnets = ["10.0.1.0/24"]
  public_subnets  = ["10.0.101.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true  # Cost optimization
}

module "ecs" {
  source = "./modules/ecs"
  # Fargate for zero-ops, or EC2 for GPU (PII model)
}
```

**Cost comparison:**
| Resource | Hetzner (cax31) | AWS (m7g.xlarge) |
|----------|-----------------|-------------------|
| Compute | €47.49/mo | ~$140/mo |
| Storage | €4.49/mo (100GB) | ~$12/mo (gp3) |
| Network | Included (20TB) | ~$9/mo (data transfer) |
| **Total** | **~€52/mo** | **~$161/mo** |

---

## 3. SSL and Domain Configuration

### 3.1 DNS Setup

Configure at your registrar (Cloudflare recommended):

```
Type    Name              Content              Proxy
A       edgevision.mw     203.0.113.42         Proxied
CNAME   api.edgevision.mw 203.0.113.42         Proxied
CNAME   *.edgevision.mw   203.0.113.42         Proxied
```

### 3.2 Nginx Configuration

```nginx
# /etc/nginx/sites-available/edgevision

# HTTP → HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name edgevision.mw api.edgevision.mw;
    return 301 https://$host$request_uri;
}

# HTTPS — API
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name api.edgevision.mw;

    ssl_certificate     /etc/letsencrypt/live/api.edgevision.mw/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.edgevision.mw/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 1d;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Security headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;
    limit_req_status 429;

    location / {
        limit_req zone=api burst=50 nodelay;

        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 10s;
        proxy_read_timeout 30s;
        proxy_send_timeout 30s;
    }

    # Health check — no rate limit
    location /health {
        limit_req off;
        proxy_pass http://127.0.0.1:8000;
    }

    # MinIO console (internal only)
    location /storage/ {
        internal;
        proxy_pass http://127.0.0.1:9001/;
    }
}
```

### 3.3 SSL Certificate (Let's Encrypt)

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate (first time)
sudo certbot certonly --nginx \
  -d api.edgevision.mw \
  -d edgevision.mw \
  --email ops@edgevision.mw \
  --agree-tos \
  --no-eff-email

# Auto-renewal (certbot installs a systemd timer)
sudo systemctl status certbot.timer

# Test renewal
sudo certbot renew --dry-run
```

### 3.4 If Using Cloudflare Proxy

When Cloudflare proxies DNS, TLS terminates at Cloudflare edge. In that case:

1. Set SSL mode to **Full (Strict)** in Cloudflare dashboard
2. Use a Cloudflare Origin Certificate (valid 15 years) instead of Let's Encrypt
3. Generate in Cloudflare dashboard → SSL/TLS → Origin Server → Create Certificate
4. Copy the certificate and key to `/etc/ssl/cloudflare/`
5. Nginx `ssl_certificate` points to the origin cert

---

## 4. Environment Variable Hardening

### 4.1 Secrets Management

**NEVER commit these to the repository.** Use one of:

| Method | When to Use |
|--------|-------------|
| `.env` file (on server only) | Single-server deployments |
| Docker secrets | Swarm/compose with secrets support |
| HashiCorp Vault | Multi-server, enterprise |
| Hetzner Cloud Labels + sops | Hetzner-native |

### 4.2 Production `.env` Template

Create `/opt/edgevision/.env` on the production server:

```bash
# === APPLICATION ===
APP_NAME=EdgeVision-MW
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=$(openssl rand -hex 32)

# === CORS (locked to your domain) ===
CORS_ORIGINS=["https://edgevision.mw","https://api.edgevision.mw"]

# === DATABASE ===
DATABASE_URL=postgresql+asyncpg://edgevision:$(openssl rand -hex 24)@postgres:5432/edgevision_mw
POSTGRES_USER=edgevision
POSTGRES_PASSWORD=$(openssl rand -hex 24)
POSTGRES_DB=edgevision_mw
POSTGRES_HOST_AUTH_METHOD=trust

# === REDIS ===
REDIS_URL=redis://redis:6379/0
REDIS_PASSWORD=$(openssl rand -hex 16)

# === JWT ===
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_ALGORITHM=EdDSA
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# === MINIO ===
MINIO_ROOT_USER=edgevision-minio
MINIO_ROOT_PASSWORD=$(openssl rand -hex 20)
MINIO_BUCKET=edgevision-data
MINIO_ENDPOINT=minio:9000

# === CELERY ===
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# === NODE AUTH ===
NODE_PUBLIC_KEY_ED25519=<base64-encoded-public-key>

# === WEBHOOKS ===
WEBHOOK_TIMEOUT_SECONDS=10
WEBHOOK_MAX_RETRIES=3

# === LOGGING ===
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### 4.3 Generate All Secrets at Once

```bash
#!/bin/bash
# generate-secrets.sh — Run once, save output to server .env

echo "# === Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "APP_SECRET_KEY=$(openssl rand -hex 32)"
echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
echo "REDIS_PASSWORD=$(openssl rand -hex 16)"
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)"
echo "MINIO_ROOT_PASSWORD=$(openssl rand -hex 20)"
```

### 4.4 Git Pre-Commit Hook

Add to `.git/hooks/pre-commit` to prevent accidental secret commits:

```bash
#!/bin/bash
# Block commits that look like secrets
if git diff --cached --name-only | xargs grep -lE '(password|secret|api_key|token)\s*=\s*["\x27][A-Za-z0-9+/]{16,}' 2>/dev/null; then
    echo "ERROR: Possible secret detected in staged files. Aborting commit."
    exit 1
fi
```

### 4.5 `.gitignore` Entries

```gitignore
.env
.env.*
!.env.example
*.pem
*.key
infrastructure/hetzner/*.tfstate
infrastructure/hetzner/.terraform/
```

---

## 5. Database Setup

### 5.1 PostgreSQL Volume Mount

```bash
# Create dedicated volume for PostgreSQL data
# On Hetzner, the cloud-init mounts /dev/sdb to /mnt/pgdata
sudo mkdir -p /mnt/pgdata
sudo mkfs.ext4 /dev/sdb
sudo mount /dev/sdb /mnt/pgdata
sudo mkdir -p /mnt/pgdata/postgres

# Add to /etc/fstab for persistence
echo '/dev/sdb /mnt/pgdata ext4 defaults,noatime 0 2' | sudo tee -a /etc/fstab
```

### 5.2 Update docker-compose.yml for Production

```yaml
# docker-compose.prod.yml
services:
  postgres:
    volumes:
      - /mnt/pgdata/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: "2"

  app:
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 2G
          cpus: "2"
    environment:
      - APP_ENV=production
      - APP_DEBUG=false

  redis:
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data

  minio:
    volumes:
      - minio-data:/data
    command: server /data --console-address ":9001"

volumes:
  redis-data:
  minio-data:
```

### 5.3 Database Initialization

```bash
# On first deploy, run migrations
docker compose -f docker-compose.prod.yml exec app alembic upgrade head

# Verify tables
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U edgevision -d edgevision_mw -c "\dt"
```

---

## 6. Staging Deployment

Deploy to staging first. Staging mirrors production exactly but with smaller resources.

### 6.1 Staging Server

```bash
# Hetzner: create a cax21 (4 vCPU, 8GB RAM) for staging
# Same cloud-init, different environment variables

# SSH into staging
ssh deploy@<staging-ip>

# Clone the repo
git clone https://github.com/your-org/edgevision-mw.git /opt/edgevision
cd /opt/edgevision

# Create staging .env
cp .env.example .env.staging
# Edit with staging secrets (different from production)

# Start services
docker compose -f docker-compose.prod.yml --env-file .env.staging up -d

# Run migrations
docker compose exec app alembic upgrade head

# Verify
curl -s https://staging.edgevision.mw/health | python3 -m json.tool
```

### 6.2 Staging Verification Checklist

```bash
# Run these commands against staging before promoting to production

# 1. Health check
curl -sf https://staging.edgevision.mw/health || echo "FAIL: health"

# 2. Register a test user
curl -sf -X POST https://staging.edgevision.mw/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"Test123!@#","full_name":"Test User"}'

# 3. Login and get JWT
TOKEN=$(curl -sf -X POST https://staging.edgevision.mw/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"Test123!@#"}' | jq -r .access_token)

# 4. Hit /me
curl -sf https://staging.edgevision.mw/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"

# 5. Run full test suite
docker compose exec app python -m pytest tests/ -v

# 6. Check Docker logs for errors
docker compose logs --tail=100 app | grep -i error
docker compose logs --tail=100 postgres | grep -i error
```

---

## 7. Production Deployment

### 7.1 Deployment Steps

```bash
# 1. SSH into production server
ssh deploy@api.edgevision.mw

# 2. Pull latest code
cd /opt/edgevision
git fetch origin main
git checkout main

# 3. Build new image
docker compose -f docker-compose.prod.yml build --no-cache app

# 4. Run database migrations (before restarting app)
docker compose -f docker-compose.prod.yml exec app alembic upgrade head

# 5. Rolling restart (zero-downtime with replicas: 2)
docker compose -f docker-compose.prod.yml up -d --force-recreate --no-deps app

# 6. Wait for health check
sleep 10
curl -sf https://api.edgevision.mw/health

# 7. Verify Celery worker restarted
docker compose -f docker-compose.prod.yml logs --tail=20 celery_worker
```

### 7.2 Zero-Downtime Deployment Script

Create `scripts/deploy.sh`:

```bash
#!/bin/bash
set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
HEALTH_URL="https://api.edgevision.mw/health"
MAX_WAIT=60

echo "=== EdgeVision-MW Deploy $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# 1. Pull latest
git fetch origin main
git checkout main

# 2. Build
docker compose -f $COMPOSE_FILE build --no-cache app

# 3. Migrate
echo "Running migrations..."
docker compose -f $COMPOSE_FILE run --rm app alembic upgrade head

# 4. Rolling restart
echo "Restarting app servers..."
docker compose -f $COMPOSE_FILE up -d --force-recreate --no-deps app

# 5. Health check with timeout
echo "Waiting for health check..."
elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
    if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
        echo "✓ Health check passed (${elapsed}s)"
        exit 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

echo "✗ Health check failed after ${MAX_WAIT}s"
echo "Rolling back..."
docker compose -f $COMPOSE_FILE rollback app 2>/dev/null || \
  docker compose -f $COMPOSE_FILE up -d --force-recreate --no-deps app
exit 1
```

```bash
chmod +x scripts/deploy.sh
```

### 7.3 Post-Deploy Smoke Test

```bash
# Quick smoke test after every deploy
set -e

BASE="https://api.edgevision.mw"
echo "Smoke test: $BASE"

# Health
curl -sf "$BASE/health" | jq -e '.status == "ok"' || exit 1
echo "✓ health"

# Auth flow
TOKEN=$(curl -sf -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"ops@edgevision.mw","password":"'"$SMOKE_TEST_PASSWORD"'"}' \
  | jq -r '.access_token')

curl -sf "$BASE/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | jq -e '.email' || exit 1
echo "✓ auth"

# Fleet
curl -sf "$BASE/api/v1/fleet/" -H "Authorization: Bearer $TOKEN" | jq -e '.nodes | length >= 0' || exit 1
echo "✓ fleet"

echo "All smoke tests passed."
```

---

## 8. Post-Deployment Verification

### 8.1 Database Integrity

```sql
-- Check all tables exist
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;

-- Verify indexes (should show composite indexes from migration 0004)
SELECT indexname, tablename FROM pg_indexes
WHERE indexname LIKE 'ix_%'
ORDER BY tablename, indexname;

-- Check consent_ledger triggers
SELECT triggername FROM pg_trigger
WHERE tgrelid = 'consent_ledger'::regclass;

-- Check no orphaned FKs
SELECT conname FROM pg_constraint
WHERE contype = 'f' AND conrelid = 'annotations'::regclass;
```

### 8.2 API Endpoint Verification

```bash
# Test every endpoint category
TOKEN="<admin-jwt>"

# Fleet
curl -sf -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/fleet/"

# Ingestion (requires node auth)
curl -sf -H "X-Node-ID: test" -H "X-Node-Signature: test" \
  -X POST "$BASE/api/v1/ingest/batch" -d '{"batch_id":"test"}'

# Catalog
curl -sf -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/catalog/datasets"

# Compliance
curl -sf -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/consent/audit"

# Billing
curl -sf -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/billing/exports"
```

---

## 9. Rollback Procedure

### 9.1 Application Rollback

```bash
# List recent images
docker images edgevision-mw-app --format "{{.Tag}} {{.CreatedAt}}"

# Rollback to previous version
PREVIOUS_TAG="2026-07-24-abc1234"
docker compose -f docker-compose.prod.yml pull app:$PREVIOUS_TAG
docker compose -f docker-compose.prod.yml up -d --force-recreate --no-deps app
```

### 9.2 Database Rollback

**Only if migration caused issues.** Migrations are designed to be forward-only.

```bash
# Downgrade one migration
docker compose -f docker-compose.prod.yml exec app alembic downgrade -1

# If you need to rollback a specific migration, create a new forward migration
# that undoes the changes, then deploy that instead.
```

---

## 10. Monitoring and Alerting

### 10.1 Health Check Monitoring

```bash
# Simple cron job for uptime monitoring
# /etc/cron.d/edgevision-health

*/5 * * * * deploy curl -sf https://api.edgevision.mw/health > /dev/null 2>&1 || \
  /usr/bin/systemctl restart docker-compose-edgevision
```

### 10.2 Log Monitoring

```bash
# View real-time logs
docker compose -f docker-compose.prod.yml logs -f app

# Search for errors
docker compose logs app 2>&1 | grep -i "error\|exception\|traceback" | tail -50

# Structured log query (logs are JSON)
docker compose logs app 2>&1 | jq 'select(.level == "ERROR")'
```

### 10.3 Disk Usage Alerts

```bash
# Alert if disk > 80%
DISK_PCT=$(df /mnt/pgdata | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$DISK_PCT" -gt 80 ]; then
    echo "CRITICAL: PostgreSQL disk usage at ${DISK_PCT}%" | \
      mail -s "EdgeVision Disk Alert" ops@edgevision.mw
fi
```

### 10.4 Recommended Monitoring Stack

| Tool | Purpose | Cost |
|------|---------|------|
| UptimeRobot | External health check | Free (50 monitors) |
| Netdata | Server metrics | Free (self-hosted) |
| Grafana + Prometheus | Dashboards | Free (self-hosted) |
| Sentry | Error tracking | Free tier (5K events/mo) |

---

## Appendix A: Docker Compose Production Checklist

- [ ] `.env` file created with production secrets
- [ ] PostgreSQL volume mounted to persistent storage
- [ ] Redis password configured
- [ ] MinIO data volume mounted
- [ ] Health checks passing on all services
- [ ] SSL certificate valid and auto-renewing
- [ ] Nginx configured with rate limiting
- [ ] UFW firewall enabled (22, 80, 443 only)
- [ ] Fail2ban configured for SSH and Nginx
- [ ] Backups scheduled (pg_dump daily, MinIO replication)
- [ ] DNS records pointing to server IP
- [ ] Cloudflare proxy enabled (optional)
- [ ] Monitoring configured (UptimeRobot + Netdata)
- [ ] Deployment script tested on staging
- [ ] Rollback procedure documented and tested

## Appendix B: Backup Strategy

```bash
#!/bin/bash
# /opt/edgevision/scripts/backup.sh — Run daily via cron

BACKUP_DIR="/mnt/backups/edgevision/$(date +%Y-%m-%d)"
mkdir -p "$BACKUP_DIR"

# PostgreSQL dump
docker compose exec -T postgres pg_dump -U edgevision edgevision_mw | \
  gzip > "$BACKUP_DIR/postgres.sql.gz"

# MinIO bucket
docker compose exec -T minio mc mirror /data "$BACKUP_DIR/minio/" --quiet 2>/dev/null

# Retain 30 days
find /mnt/backups/edgevision -maxdepth 1 -mtime +30 -exec rm -rf {} +

echo "Backup complete: $BACKUP_DIR"
```

```bash
# /etc/cron.d/edgevision-backup
0 2 * * * deploy /opt/edgevision/scripts/backup.sh >> /var/log/edgevision-backup.log 2>&1
```
