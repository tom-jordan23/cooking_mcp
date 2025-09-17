# Family Cooking Lab Notebook - Technical Specifications

## Executive Summary

A simple, family-scale MCP integration for collecting cooking feedback through Slack and storing it in a Git-backed lab notebook. Designed for 2-6 family members with minimal infrastructure requirements and easy maintenance.

**Key Features:**
- MCP protocol compliance for Claude integration
- Slack-based feedback collection
- Git repository storage with Markdown files
- Simple web interface for viewing recipes
- Optional AI-powered insights

## System Architecture

### Core Components

1. **MCP Server** - FastAPI application implementing MCP protocol
2. **Slack Bot** - Simple feedback collection via modals
3. **Web Interface** - Basic recipe viewing and editing
4. **Git Storage** - Markdown files with YAML frontmatter
5. **Optional AI** - OpenAI API for recipe insights

## Technical Requirements

### Performance (Family Scale)
- Response time: < 2 seconds for feedback submissions
- Concurrent users: 2-6 family members
- Availability: 95% uptime (some downtime for updates is fine)
- Storage: ~1GB for hundreds of recipes with photos

### Infrastructure
- Single server deployment (VPS, Raspberry Pi, or managed service)
- SQLite or small PostgreSQL database
- File-based configuration
- Automated daily backups

## Data Schema

### Recipe Entry Format
```yaml
# YAML Frontmatter
id: 2024-12-15_grilled_chicken
created_at: 2024-12-15T18:00:00Z
updated_at: 2024-12-15T20:30:00Z
title: "Grilled Chicken Thighs"
date: 2024-12-15
tags: [chicken, grill, weeknight]
gear: [recteq, thermometer]
servings: 4
dinner_time: 2024-12-15T19:00:00Z
prep_time_minutes: 15
cook_time_minutes: 25
ingredients:
  - item: "Chicken thighs"
    amount: "2 lbs"
  - item: "Salt"
    amount: "1 tsp"
protocol: |
  1. Season chicken with salt 30 minutes before cooking
  2. Preheat grill to 375°F
  3. Grill 6 minutes per side
  4. Check internal temp reaches 165°F
observations: []
outcomes:
  rating_10: null
  issues: []
  next_time: []
```

### Feedback Data
```json
{
  "entry_id": "2024-12-15_grilled_chicken",
  "who": "parent1",
  "timestamp": "2024-12-15T19:45:00Z",
  "rating_10": 8,
  "notes": "Great flavor, slightly overcooked",
  "axes": {
    "doneness": "slightly over",
    "seasoning": "perfect"
  }
}
```

## API Specifications

### MCP Server Resources
- `lab://entries` - List all recipe entries
- `lab://entry/{id}` - Get specific recipe
- `lab://search?q=...` - Simple text search

### MCP Server Tools
- `append_observation(id, note, time?, temp_c?)`
- `update_outcomes(id, rating, notes?, issues?, next_time?)`
- `create_entry(title, tags?, gear?, servings?)`
- `git_commit(message)`

### REST API (for Slack)
```
POST /api/feedback
GET /api/entry/:id
POST /api/entry
```

## Implementation

### Tech Stack (2024-2025)
- **Backend**: Python 3.12+ with FastAPI
- **Database**: SQLite (or PostgreSQL 16+ with pgvector)
- **Frontend**: Astro + Tailwind CSS + TypeScript (recommended) or simple HTML/CSS/JS
- **Slack**: Bolt framework (latest version)
- **AI**: OpenAI GPT-4o-mini + Anthropic Claude 3.5 Haiku (optional)
- **Local AI**: Ollama with Llama 3.2 for privacy/offline use

### Deployment Options

#### Option 1: Managed Services ($10-15/month) - RECOMMENDED
```yaml
Services:
  - Railway for full-stack hosting (best developer experience)
  - Vercel for Astro frontend (free tier)
  - Supabase for PostgreSQL + vector search (free tier)
  - GitHub for Git storage

Benefits: Zero maintenance, excellent developer experience, automatic scaling
Cost: $10-15/month
```

#### Option 2: Single VPS ($5/month)
```yaml
Infrastructure:
  - Hetzner VPS (2GB RAM, 40GB SSD) - €4.50/month
  - Docker Compose deployment
  - PostgreSQL 16 with pgvector
  - Caddy reverse proxy (automatic HTTPS)
  - Automated backups to GitHub + cloud storage

Benefits: Full control, lowest cost, better performance
Cost: ~$5/month
```

#### Option 3: Self-Hosted ($0/month)
```yaml
Hardware:
  - Raspberry Pi 4 or home server
  - Docker Compose
  - Local SQLite
  - Tailscale for remote access
  - Cloud backup (Google Drive/Dropbox)

Benefits: No monthly cost, complete privacy
Cost: Hardware only
```

### Docker Compose Example
```yaml
version: '3.8'
services:
  mcp-server:
    build: ./mcp-server
    ports:
      - "8080:8080"
    volumes:
      - ./recipes:/app/recipes
      - ./data:/app/data
    environment:
      - DATABASE_URL=sqlite:///app/data/cooking.db
      - GIT_REPO_PATH=/app/recipes

  slack-bot:
    build: ./slack-bot
    environment:
      - SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
      - MCP_SERVER_URL=http://mcp-server:8080
    depends_on:
      - mcp-server

  web:
    build: ./web
    ports:
      - "3000:3000"
    environment:
      - API_URL=http://mcp-server:8080
    depends_on:
      - mcp-server

  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    environment:
      - DOMAIN=${DOMAIN}
    depends_on:
      - mcp-server
      - web

volumes:
  caddy_data:
```

## Security (Family Appropriate)

### Essential Security
- HTTPS with Let's Encrypt certificates
- Basic authentication (family password or individual accounts)
- Input validation and sanitization
- Regular automated backups
- Keep dependencies updated

### Authentication Options
```python
# Simple family authentication
FAMILY_USERS = {
    "parent1": "simple_password",
    "parent2": "simple_password",
    "kid1": {"password": "kid_password", "role": "readonly"}
}

# Or single family password
FAMILY_PASSWORD = "our_cooking_password_2024"

# Or Slack-only authentication
# Users must be in family Slack workspace
```

## Slack Integration

### Bot Setup
1. Create Slack app with bot permissions: `chat:write`, `commands`
2. Add slash command: `/cook-feedback`
3. Configure interactive components

### Feedback Flow
1. User runs `/cook-feedback grilled_chicken`
2. Bot shows modal with rating and notes fields
3. User submits feedback
4. Bot updates recipe via MCP server
5. Bot confirms with link to updated recipe

### Modal Example
```json
{
  "type": "modal",
  "title": "Grilled Chicken Feedback",
  "blocks": [
    {
      "type": "input",
      "label": "Rating (1-10)",
      "element": {"type": "number_input", "min_value": 1, "max_value": 10}
    },
    {
      "type": "input",
      "label": "Notes",
      "element": {"type": "plain_text_input", "multiline": true}
    }
  ]
}
```

## Optional AI Features

### Modern AI Integration (2024-2025)
```python
import openai
from anthropic import Anthropic

async def get_recipe_insights(recipe_text):
    """Get cooking insights using modern, cost-effective models"""

    # Primary: GPT-4o-mini (very cost-effective at $0.15/1M tokens)
    try:
        client = openai.AsyncOpenAI()
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": f"Analyze this recipe and suggest one improvement: {recipe_text}"
            }],
            max_tokens=100
        )
        return response.choices[0].message.content
    except Exception:
        # Fallback: Anthropic Claude Haiku (faster, good for simple tasks)
        client = Anthropic()
        response = await client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": f"Analyze this recipe and suggest one improvement: {recipe_text}"
            }]
        )
        return response.content[0].text

# Cost: ~$1-3/month for family usage with GPT-4o-mini
```

## Development Plan

### Phase 1: Core MCP Server (Week 1)
- [ ] MCP protocol implementation
- [ ] Git repository operations
- [ ] Basic recipe CRUD
- [ ] Simple REST API

### Phase 2: Slack Integration (Week 2)
- [ ] Slack bot setup
- [ ] Feedback collection modal
- [ ] Integration with MCP server
- [ ] Error handling

### Phase 3: Web Interface (Week 3)
- [ ] Recipe listing page
- [ ] Individual recipe view
- [ ] Basic editing capability
- [ ] Search functionality

### Phase 4: Polish & Deploy (Week 4)
- [ ] Deployment configuration
- [ ] Backup automation
- [ ] Documentation
- [ ] Optional AI features

## Configuration

### Environment Variables (Updated for 2024-2025)
```bash
# MCP Server
DATABASE_URL=postgresql://user:pass@localhost:5432/cooking_lab
# Or for SQLite: sqlite:///data/cooking.db
GIT_REPO_PATH=/app/recipes
GIT_AUTHOR_NAME="Family Cook Bot"
GIT_AUTHOR_EMAIL="cook@family.local"

# Slack
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_SIGNING_SECRET=your-secret
SLACK_APP_TOKEN=xapp-your-token  # For Socket Mode

# AI (Multiple providers for redundancy)
OPENAI_API_KEY=sk-your-key
ANTHROPIC_API_KEY=sk-ant-your-key
AI_PRIMARY_MODEL=gpt-4o-mini  # Cost-effective choice
AI_FALLBACK_MODEL=claude-3-haiku-20240307

# Authentication
FAMILY_PASSWORD=your_family_password
# or
AUTH_TYPE=slack_only

# Deployment
DOMAIN=cookinglab.yourdomain.com
ENVIRONMENT=production
```

## Backup Strategy

### Automated Daily Backup
```bash
#!/bin/bash
# backup.sh - runs daily via cron

# Backup Git repository
cd /app/recipes && git push origin main

# Backup database
sqlite3 /app/data/cooking.db ".backup /tmp/cooking_backup.db"
# Upload to cloud storage (S3, Google Drive, etc.)

# Backup configuration
tar -czf /tmp/config_backup.tar.gz /app/config/
```

## Monitoring (Simple)

### Basic Health Checks
```python
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "git_repo": check_git_status(),
        "database": check_database(),
        "last_backup": get_last_backup_time()
    }
```

### Optional: Simple Alerting
- Email notification on errors
- Slack message for system issues
- Weekly summary of activity

## Cost Breakdown (2024-2025 Updated Pricing)

### Option 1: Managed Services (Railway - Recommended)
- Hosting: $5-10/month (Railway)
- Database: $5/month (Railway PostgreSQL with pgvector)
- AI calls: $1-3/month (GPT-4o-mini)
- **Total: $11-18/month**

### Option 2: Budget Managed (Supabase)
- Database: Free tier (Supabase PostgreSQL with pgvector)
- Frontend: Free (Vercel)
- API: $5/month (Railway or Render)
- AI calls: $1-3/month (GPT-4o-mini)
- **Total: $6-8/month**

### Option 3: VPS (Best Value)
- Server: €4.5/month (~$5) (Hetzner VPS)
- AI calls: $1-3/month (GPT-4o-mini)
- **Total: $6-8/month**

### Option 4: Self-Hosted
- Hardware: $100-200 one-time (Raspberry Pi 5 setup)
- AI calls: $1-3/month (or free with local Ollama)
- **Total: $1-3/month ongoing**

## Maintenance

### Weekly (5 minutes)
- Check backup status
- Review error logs
- Update dependencies if needed

### Monthly (15 minutes)
- Review storage usage
- Check SSL certificate renewal
- Backup configuration files

### Quarterly (30 minutes)
- Full system update
- Review and clean old logs
- Test disaster recovery

## Conclusion

This family-scale specification provides all the core functionality of the enterprise version while being:
- **90% less complex** to implement and maintain
- **95% less expensive** to operate ($6-18/month vs $1000+/month)
- **Actually appropriate** for 2-6 family members
- **Modern and future-proof** with 2024-2025 technology stack
- **Easy to self-host** or deploy to managed services

The system uses contemporary tools like Astro, GPT-4o-mini, and Railway for excellent developer experience while maintaining simplicity. It will handle hundreds of recipes, daily feedback collection, and provide a great experience for family cooking documentation without enterprise overhead.

## Key Technology Updates for 2024-2025
- **Python 3.12+** for better performance
- **Astro + Tailwind** for modern, fast frontend
- **GPT-4o-mini** for cost-effective AI (10x cheaper than GPT-4)
- **Railway + Caddy** for easy deployment with automatic HTTPS
- **PostgreSQL 16 with pgvector** for unified data and vector storage
- **Contemporary deployment patterns** following current best practices