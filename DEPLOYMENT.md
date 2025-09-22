# MCP Cooking Lab Notebook - Comprehensive Deployment Guide

This guide provides complete deployment instructions for the MCP Cooking Lab Notebook system across multiple deployment strategies, from cost-effective family-scale to enterprise production environments with full observability.

## Table of Contents

1. [Quick Start Options](#quick-start-options)
2. [System Requirements](#system-requirements)
3. [Family-Scale Deployment (Railway/VPS)](#family-scale-deployment)
4. [Production Docker Compose](#production-docker-compose)
5. [Enterprise Kubernetes Deployment](#enterprise-kubernetes-deployment)
6. [Environment Configuration](#environment-configuration)
7. [Security Configuration](#security-configuration)
8. [Monitoring and Observability](#monitoring-and-observability)
9. [Backup and Recovery](#backup-and-recovery)
10. [SSL/TLS Configuration](#ssltls-configuration)
11. [CI/CD Pipeline Setup](#cicd-pipeline-setup)
12. [Troubleshooting Guide](#troubleshooting-guide)
13. [Migration and Upgrades](#migration-and-upgrades)

## Quick Start Options

Choose your deployment strategy based on your needs:

| Strategy | Cost/Month | Complexity | Use Case |
|----------|------------|------------|----------|
| **Render** | $7-21 | ⭐ | Family use, automatic scaling |
| **Railway** | $6-18 | ⭐ | Family use, quick setup |
| **VPS Docker** | $10-30 | ⭐⭐ | Self-hosted, single server |
| **Production Docker** | $50-200 | ⭐⭐⭐ | Small business, monitoring |
| **Kubernetes** | $100-500+ | ⭐⭐⭐⭐⭐ | Enterprise, high availability |

### 30-Second Render Deploy

```bash
# 1. Clone repository
git clone https://github.com/your-org/cooking_mcp.git
cd cooking_mcp

# 2. Deploy to Render
# Connect your GitHub repo at https://render.com
# Use the included render.yaml for automatic setup

# 3. Configure Slack tokens in Render dashboard
# SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET required
```

### 30-Second Railway Deploy

```bash
# 1. Clone repository
git clone https://github.com/your-org/cooking_mcp.git
cd cooking_mcp

# 2. Deploy to Railway
curl -fsSL https://railway.app/install.sh | sh
railway login
railway up --service app

# 3. Configure environment variables in Railway dashboard
railway open
```

### 5-Minute Docker Compose

```bash
# 1. Quick setup with family configuration
./scripts/deploy.sh --type family --env production

# 2. Access application
open http://localhost:8080
```

## System Requirements

### Minimum Requirements (Family Scale)

| Component | Specification |
|-----------|---------------|
| **CPU** | 1 core, 2.0 GHz |
| **RAM** | 2 GB (1 GB for app, 1 GB for database) |
| **Storage** | 20 GB SSD |
| **Network** | 1 Mbps upload (for Git sync) |
| **OS** | Linux, macOS, Windows with Docker |

### Recommended Requirements (Production)

| Component | Specification |
|-----------|---------------|
| **CPU** | 4 cores, 3.0 GHz |
| **RAM** | 8 GB (4 GB for app, 4 GB for services) |
| **Storage** | 100 GB SSD (with backups) |
| **Network** | 10 Mbps symmetric |
| **OS** | Ubuntu 22.04 LTS or CentOS 8+ |

### Enterprise Requirements (Kubernetes)

| Component | Specification |
|-----------|---------------|
| **Nodes** | 3+ nodes (HA setup) |
| **CPU** | 8+ cores per node |
| **RAM** | 16 GB per node |
| **Storage** | 500 GB NVMe with replication |
| **Network** | 100 Mbps with load balancing |

## Family-Scale Deployment

### Option 1: Render (Recommended)

Render provides automatic scaling, built-in PostgreSQL and Redis, with a simple configuration-as-code approach.

#### Step 1: Repository Setup

```bash
# Clone and prepare the repository
git clone https://github.com/your-org/cooking_mcp.git
cd cooking_mcp

# The render.yaml file is already included for automatic setup
```

#### Step 2: Deploy to Render

1. **Connect GitHub Repository**:
   - Go to [render.com](https://render.com) and sign up/login
   - Click "New" → "Blueprint"
   - Connect your GitHub account and select the cooking_mcp repository
   - Render will automatically detect the `render.yaml` file

2. **Configure Environment Variables**:
   - In the Render dashboard, go to your web service
   - Navigate to "Environment" tab
   - Add the required Slack configuration:
     ```
     SLACK_BOT_TOKEN=xoxb-your-bot-token-here
     SLACK_SIGNING_SECRET=your-signing-secret-here
     ```

3. **Deploy**:
   - Click "Manual Deploy" or push to your main branch
   - Render will automatically create:
     - Web service (your application)
     - PostgreSQL database
     - Redis instance
   - All services are automatically connected

#### Step 3: Configure Domain (Optional)

```bash
# In Render dashboard:
# 1. Go to your web service
# 2. Click "Settings" → "Custom Domains"
# 3. Add your domain (SSL is automatic)
```

#### Step 4: Slack Webhook Setup

```bash
# Get your Render app URL
# https://your-app-name.onrender.com

# Configure in Slack App settings:
# Request URL: https://your-app-name.onrender.com/slack/events
```

### Option 2: Railway Platform

Railway provides the simplest deployment with automatic scaling and built-in monitoring.

#### Step 1: Prepare Repository

```bash
# Clone and prepare the repository
git clone https://github.com/your-org/cooking_mcp.git
cd cooking_mcp

# Copy Railway environment template
cp .env.railway .env.production
```

#### Step 2: Configure Environment

Edit `.env.production` with your settings:

```bash
# Required settings for Railway
DATABASE_URL=postgresql://username:password@hostname:5432/database
REDIS_URL=redis://hostname:6379/0

# Slack integration
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret

# Generate secure secrets
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)

# Multi-channel notifications (optional)
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

#### Step 3: Deploy to Railway

```bash
# Install Railway CLI
curl -fsSL https://railway.app/install.sh | sh

# Login and deploy
railway login
railway up --service app

# Add PostgreSQL and Redis services
railway add --service postgres
railway add --service redis

# Set environment variables
railway variables set --file .env.production
```

#### Step 4: Configure Domain (Optional)

```bash
# Add custom domain in Railway dashboard
railway domain add your-domain.com

# Or use Railway subdomain
railway domain
```

### Option 2: VPS with Docker Compose

Deploy on any VPS provider (DigitalOcean, Linode, AWS EC2, etc.).

#### Step 1: Server Setup

```bash
# Connect to your VPS
ssh root@your-server-ip

# Update system
apt update && apt upgrade -y

# Install Docker and Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Create application user
useradd -m -s /bin/bash cooking
usermod -aG docker cooking
```

#### Step 2: Deploy Application

```bash
# Switch to application user
su - cooking

# Clone repository
git clone https://github.com/your-org/cooking_mcp.git
cd cooking_mcp

# Configure environment
cp .env.example .env.production
nano .env.production  # Edit with your settings

# Deploy with family configuration
./scripts/deploy.sh --type family --env production
```

#### Step 3: Setup Reverse Proxy (Nginx)

```bash
# Install Nginx
sudo apt install nginx -y

# Create site configuration
sudo tee /etc/nginx/sites-available/cooking-mcp << EOF
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/cooking-mcp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### Step 4: SSL Certificate with Let's Encrypt

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured automatically
sudo systemctl status certbot.timer
```

## Production Docker Compose

For production environments with comprehensive monitoring and backup capabilities.

### Step 1: Production Server Setup

```bash
# Enhanced server configuration
# Increase file limits
echo 'fs.file-max = 65536' >> /etc/sysctl.conf

# Configure Docker daemon
sudo tee /etc/docker/daemon.json << EOF
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2"
}
EOF

sudo systemctl restart docker
```

### Step 2: Production Deployment

```bash
# Deploy with production configuration
./scripts/deploy.sh --type production --env production

# Verify deployment
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs
```

### Step 3: Monitoring Stack

The production deployment includes:

- **Prometheus**: Metrics collection (http://your-domain:9090)
- **Grafana**: Dashboards and alerting (http://your-domain:3000)
- **AlertManager**: Alert routing (http://your-domain:9093)
- **Jaeger**: Distributed tracing (http://your-domain:16686)

```bash
# Access Grafana (admin/admin by default)
open http://your-domain:3000

# Import provided dashboards
# - Application metrics dashboard
# - Infrastructure monitoring dashboard
# - Business metrics dashboard
```

## Enterprise Kubernetes Deployment

For high-availability, scalable production environments.

### Prerequisites

```bash
# Kubernetes cluster (1.25+)
kubectl version --client

# Helm (3.0+)
helm version

# Ingress controller (nginx recommended)
helm upgrade --install ingress-nginx ingress-nginx \
  --repo https://kubernetes.github.io/ingress-nginx \
  --namespace ingress-nginx --create-namespace
```

### Step 1: Namespace and Secrets

```bash
# Create namespace
kubectl create namespace cooking-mcp

# Create secrets
kubectl create secret generic cooking-mcp-secrets \
  --from-env-file=.env.production \
  --namespace cooking-mcp

# Create TLS secret (if using custom domain)
kubectl create secret tls cooking-mcp-tls \
  --cert=path/to/tls.crt \
  --key=path/to/tls.key \
  --namespace cooking-mcp
```

### Step 2: Deploy Infrastructure Services

```bash
# Deploy PostgreSQL with persistence
kubectl apply -f k8s/base/postgres.yaml

# Deploy Redis
kubectl apply -f k8s/base/redis.yaml

# Wait for services to be ready
kubectl wait --for=condition=ready pod -l app=postgres -n cooking-mcp --timeout=300s
kubectl wait --for=condition=ready pod -l app=redis -n cooking-mcp --timeout=300s
```

### Step 3: Deploy Application

```bash
# Deploy application
kubectl apply -f k8s/base/app.yaml

# Deploy ingress
kubectl apply -f k8s/base/ingress.yaml

# Check rollout status
kubectl rollout status deployment/cooking-mcp-app -n cooking-mcp

# Get external IP
kubectl get ingress -n cooking-mcp
```

### Step 4: Monitoring and Observability

```bash
# Deploy Prometheus stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --values monitoring/prometheus-values.yaml

# Deploy application monitoring
kubectl apply -f monitoring/servicemonitor.yaml
kubectl apply -f monitoring/alerts.yaml
```

## Environment Configuration

### Configuration Management

The system uses environment-specific configuration files:

```
.env.development    # Local development
.env.staging       # Staging environment
.env.production    # Production environment
.env.render        # Render-specific settings
.env.railway       # Railway-specific settings
```

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@host:5432/db` |
| `REDIS_URL` | Redis connection string | `redis://host:6379/0` |
| `SECRET_KEY` | Application secret (32+ chars) | `your-secure-secret-key-here` |
| `SLACK_BOT_TOKEN` | Slack bot token | `xoxb-...` |
| `SLACK_SIGNING_SECRET` | Slack signing secret | `abc123...` |

### Optional Integrations

| Variable | Service | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram | Bot token for notifications |
| `TWILIO_ACCOUNT_SID` | Twilio | SMS/WhatsApp integration |
| `OPENAI_API_KEY` | OpenAI | AI-powered insights |
| `AWS_ACCESS_KEY_ID` | AWS | Backup to S3 |

### Environment Validation

```bash
# Validate configuration
python -c "from app.utils.config import validate_environment; validate_environment()"

# Test database connection
python -c "from app.models import test_connection; asyncio.run(test_connection())"

# Test Redis connection
python -c "from app.utils.redis import test_redis; asyncio.run(test_redis())"
```

## Security Configuration

### SSL/TLS Setup

#### Let's Encrypt with Certbot

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com

# Automatic renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

#### Custom SSL Certificate

```bash
# For custom certificates
sudo cp your-cert.crt /etc/ssl/certs/cooking-mcp.crt
sudo cp your-key.key /etc/ssl/private/cooking-mcp.key
sudo chmod 644 /etc/ssl/certs/cooking-mcp.crt
sudo chmod 600 /etc/ssl/private/cooking-mcp.key
```

### Security Headers

Production deployments automatically include:

- HTTPS enforcement
- HSTS headers
- X-Frame-Options
- X-Content-Type-Options
- X-XSS-Protection
- Content Security Policy

### Firewall Configuration

```bash
# UFW firewall setup
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw --force enable

# Fail2ban for brute force protection
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

## Monitoring and Observability

### Application Metrics

The system exposes metrics at `/metrics` endpoint:

- Request count and latency
- Database connection pool stats
- Background task status
- Business metrics (feedback submissions, etc.)

### Health Checks

Multiple health check endpoints:

- `/health` - Basic health status
- `/health/detailed` - Comprehensive health check
- `/health/dependencies` - External service status

### Log Management

#### Structured Logging

```bash
# View application logs
docker-compose logs -f app

# Search logs
docker-compose logs app | grep ERROR

# Export logs
docker-compose logs --no-color app > cooking-mcp.log
```

#### Log Aggregation (Production)

```yaml
# Add to docker-compose.prod.yml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
    labels: "service=cooking-mcp"
```

### Alerting Rules

Prometheus alerting rules included:

- High error rate (>5% for 5 minutes)
- High response time (>2s 95th percentile)
- Database connection failures
- Disk space usage (>80%)
- Memory usage (>90%)

## Backup and Recovery

### Automated Backups

#### Database Backups

```bash
# Manual backup
./scripts/backup.sh --type database --retention 30

# Scheduled backups (cron)
0 2 * * * /path/to/cooking_mcp/scripts/backup.sh --type full --quiet
```

#### Git Repository Backups

```bash
# Backup notebook repository
./scripts/backup.sh --type git-repo --destination s3://your-bucket/backups/
```

### Disaster Recovery

#### Database Recovery

```bash
# Restore from backup
pg_restore -h localhost -U cooking_user -d cooking_mcp backup_file.sql

# Or using script
./scripts/restore.sh --type database --file backup_20231201_020000.sql.gz
```

#### Full System Recovery

```bash
# Complete system restore
./scripts/restore.sh --type full --backup-id 20231201_020000
```

### Backup Verification

```bash
# Test backup integrity
./scripts/backup.sh --verify --file backup_20231201_020000.sql.gz

# Automated backup testing
./scripts/test-backup-restore.sh
```

## CI/CD Pipeline Setup

### GitHub Actions Configuration

The repository includes a comprehensive CI/CD pipeline:

1. **Code Quality**: Linting, formatting, type checking
2. **Security Scanning**: Dependency vulnerabilities, secrets detection
3. **Testing**: Unit tests, integration tests, end-to-end tests
4. **Container Building**: Multi-architecture Docker images
5. **Deployment**: Automated deployment to staging/production

### Required Secrets

Add these secrets to your GitHub repository:

| Secret | Description |
|--------|-------------|
| `DOCKER_REGISTRY_TOKEN` | Container registry access |
| `RAILWAY_TOKEN` | Railway deployment token |
| `AWS_ACCESS_KEY_ID` | AWS credentials for backups |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `SLACK_WEBHOOK_URL` | Deployment notifications |

### Manual Deployment

```bash
# Deploy to staging
git push origin develop

# Deploy to production
git tag v1.0.0
git push origin v1.0.0
```

## Troubleshooting Guide

### Common Issues

#### Application Won't Start

```bash
# Check logs
docker-compose logs app

# Common fixes:
# 1. Database connection issues
docker-compose up db
psql $DATABASE_URL -c "SELECT 1"

# 2. Missing environment variables
./scripts/check-config.sh

# 3. Port conflicts
netstat -tulpn | grep :8080
```

#### Database Connection Errors

```bash
# Test database connectivity
docker-compose exec db psql -U cooking_user -d cooking_mcp -c "SELECT 1"

# Reset database
docker-compose down -v
docker-compose up db
alembic upgrade head
```

#### Slack Integration Issues

```bash
# Verify Slack configuration
curl -X POST https://slack.com/api/auth.test \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"

# Check webhook URL
ngrok http 8080  # For local testing
```

#### Performance Issues

```bash
# Monitor resource usage
docker stats

# Check database performance
docker-compose exec db psql -U cooking_user -d cooking_mcp \
  -c "SELECT * FROM pg_stat_activity"

# Enable query logging
# Set ENABLE_QUERY_LOGGING=true in environment
```

### Debug Mode

```bash
# Enable debug mode
export DEBUG=true
export LOG_LEVEL=DEBUG

# Run with development server
python -m uvicorn app.main:app --reload --log-level debug
```

### Support and Logs

```bash
# Generate support bundle
./scripts/support-bundle.sh

# This creates:
# - Application logs
# - System information
# - Configuration (sanitized)
# - Performance metrics
```

## Migration and Upgrades

### Version Upgrades

```bash
# 1. Backup current deployment
./scripts/backup.sh --type full

# 2. Update code
git pull origin main

# 3. Update dependencies
pip install -r requirements.txt

# 4. Run database migrations
alembic upgrade head

# 5. Restart services
docker-compose restart
```

### Zero-Downtime Deployment

```bash
# For production environments
./scripts/deploy.sh --type production --strategy blue-green
```

### Configuration Migration

```bash
# Migrate configuration between versions
./scripts/migrate-config.sh --from v1.0 --to v2.0
```

## Performance Optimization

### Database Optimization

```sql
-- Add indexes for common queries
CREATE INDEX CONCURRENTLY idx_entries_created_at ON entries(created_at);
CREATE INDEX CONCURRENTLY idx_feedback_entry_id ON feedback(entry_id);

-- Analyze query performance
EXPLAIN ANALYZE SELECT * FROM entries WHERE created_at > NOW() - INTERVAL '7 days';
```

### Caching Strategy

```bash
# Enable Redis caching
export ENABLE_RESPONSE_CACHING=true
export CACHE_TTL=3600

# Cache configuration
export REDIS_MAX_CONNECTIONS=100
export CACHE_MAX_SIZE=1000
```

### Resource Limits

```yaml
# Docker Compose resource limits
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

---

## Support

- **Documentation**: [GitHub Wiki](https://github.com/your-org/cooking_mcp/wiki)
- **Issues**: [GitHub Issues](https://github.com/your-org/cooking_mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/cooking_mcp/discussions)
- **Slack**: [Community Slack](https://cooking-mcp.slack.com)

For enterprise support and custom deployments, contact: support@cooking-mcp.com