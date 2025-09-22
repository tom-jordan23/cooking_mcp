# Cooking Lab Notebook MCP Integration

A production-ready Model Context Protocol (MCP) server for managing cooking experiments and feedback collection through multiple channels including Slack and various messaging platforms.

## Overview

This system enables structured cooking experiment tracking with post-cook feedback collection through Slack and other messaging channels. All data is stored in a Git-backed lab notebook using the MCP protocol for standardized access.

### Key Features

- **MCP Protocol Compliance**: Standard resource and tool interfaces for notebook operations
- **Multi-Channel Feedback**: Collect feedback via Slack, Telegram, WhatsApp, SMS, Signal, and Email
- **Structured Data**: YAML frontmatter with Markdown content for recipes and experiments
- **Git-Backed Storage**: Version-controlled notebook entries with full history
- **AI-Enhanced Insights**: Natural language processing and recipe recommendations
- **Real-Time Notifications**: Scheduled feedback prompts after cooking sessions
- **Enterprise Security**: Zero-trust architecture with comprehensive monitoring

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Git
- PostgreSQL (for production)
- Redis (for caching and rate limiting)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd cooking_mcp
   ```

2. **Set up Python environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Install Node.js dependencies (for Slack app)**
   ```bash
   cd slack-app
   npm install
   cd ..
   ```

4. **Set up the database**
   ```bash
   # For development with SQLite (default)
   export DATABASE_URL="sqlite:///./lab_notebook.db"

   # For production with PostgreSQL
   export DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/cooking_mcp"

   # Run migrations
   alembic upgrade head
   ```

5. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

6. **Start the development services**
   ```bash
   # Start MCP server (stdio mode for development)
   python -m cooking_mcp.server

   # In another terminal, start the REST bridge
   python -m cooking_mcp.bridge

   # In another terminal, start the Slack app
   cd slack-app && npm run dev

   # In another terminal, start the multi-channel notifier
   python -m cooking_mcp.notifier
   ```

### Using Docker Compose (Recommended for Development)

1. **Start all services**
   ```bash
   docker-compose up -d
   ```

2. **View logs**
   ```bash
   docker-compose logs -f
   ```

3. **Stop services**
   ```bash
   docker-compose down
   ```

### Deploy to Render (Quick Production Deployment)

Render provides an easy way to deploy the system to production with minimal configuration.

#### Prerequisites
- Render account (free tier available)
- GitHub repository with your code
- Environment variables configured

#### Deployment Steps

1. **Prepare your repository**
   ```bash
   # Ensure you have a requirements.txt in the root
   # Ensure you have a Dockerfile or use Render's auto-detect
   git add .
   git commit -m "Prepare for Render deployment"
   git push origin main
   ```

2. **Create services on Render**

   **Web Service (MCP Bridge):**
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Configure:
     - **Name**: `cooking-mcp-bridge`
     - **Environment**: `Python 3.11+`
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `python -m cooking_mcp.bridge`
     - **Port**: `8080`

   **Background Worker (Notifier):**
   - Click "New +" → "Background Worker"
   - Connect same repository
   - Configure:
     - **Name**: `cooking-mcp-notifier`
     - **Environment**: `Python 3.11+`
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `python -m cooking_mcp.notifier`

3. **Set up PostgreSQL database**
   - Click "New +" → "PostgreSQL"
   - Configure:
     - **Name**: `cooking-mcp-db`
     - **Plan**: Free tier for development
   - Copy the connection string for environment variables

4. **Configure environment variables**

   For each service, add these environment variables:
   ```bash
   # Database
   DATABASE_URL=postgresql://[from Render PostgreSQL service]

   # MCP Configuration
   LAB_MCP_TOKEN=your-secure-random-token
   REPO_ROOT=/opt/render/project/src/notebook
   GIT_AUTHOR=Lab Bot
   GIT_EMAIL=lab@yourdomain.com

   # Slack (if using)
   SLACK_BOT_TOKEN=xoxb-your-bot-token
   SLACK_SIGNING_SECRET=your-signing-secret

   # Other provider tokens as needed
   TELEGRAM_BOT_TOKEN=your-telegram-token
   TWILIO_SID=your-twilio-sid
   TWILIO_TOKEN=your-twilio-token
   ```

5. **Deploy and verify**
   - Services will auto-deploy on git push
   - Check logs in Render dashboard
   - Test API endpoints: `https://your-service.onrender.com/health`

#### Render Configuration Files

Create these files in your repository root for easier deployment:

**render.yaml** (Blueprint for easy setup):
```yaml
services:
  - type: web
    name: cooking-mcp-bridge
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python -m cooking_mcp.bridge
    envVars:
      - key: PORT
        value: 8080
      - key: DATABASE_URL
        fromDatabase:
          name: cooking-mcp-db
          property: connectionString

  - type: worker
    name: cooking-mcp-notifier
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python -m cooking_mcp.notifier
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: cooking-mcp-db
          property: connectionString

databases:
  - name: cooking-mcp-db
    databaseName: cooking_mcp
    user: cooking_user
```

**Dockerfile** (if you prefer Docker deployment):
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8080

CMD ["python", "-m", "cooking_mcp.bridge"]
```

#### Post-Deployment Setup

1. **Run database migrations**
   ```bash
   # Use Render shell access or create a migration job
   alembic upgrade head
   ```

2. **Configure webhook URLs**
   - Update Slack app webhook URL to: `https://your-service.onrender.com/slack/events`
   - Update any other webhook configurations

3. **Test the deployment**
   ```bash
   curl https://your-service.onrender.com/health
   curl -X POST https://your-service.onrender.com/mcp/create_entry \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"title": "Test Recipe", "tags": ["test"]}'
   ```

#### Monitoring and Maintenance

- **Logs**: Available in Render dashboard
- **Metrics**: Built-in CPU/memory monitoring
- **Auto-scaling**: Available on paid plans
- **Custom domains**: Available with SSL certificates
- **Database backups**: Automatic on paid PostgreSQL plans

#### Cost Optimization

- **Free tier**: Suitable for development and light usage
- **Starter plan**: $7/month for production workloads
- **Database**: Free PostgreSQL for development, $7/month for production
- **Sleep mode**: Free services sleep after 15 minutes of inactivity

## Architecture

### Core Components

- **MCP Server**: Implements MCP protocol for notebook operations
- **REST Bridge**: HTTP API façade over MCP tools for non-MCP clients
- **Slack App**: Bot for collecting structured feedback via modals
- **Multi-Channel Notifier**: Cross-platform message delivery and response processing
- **Web Interface**: Optional fallback for feedback collection

### Data Flow

1. Cook dinner and record basic recipe information
2. System schedules feedback notification for 45 minutes after dinner time
3. Notification sent via Slack and/or spouse's preferred messaging channel
4. Structured feedback collected and normalized
5. Data written to Git-backed notebook via MCP tools
6. AI analysis generates insights and recommendations

## Configuration

### Required Environment Variables

```bash
# MCP Bridge
LAB_MCP_TOKEN=your-secret-token
REPO_ROOT=/path/to/notebook
GIT_AUTHOR="Lab Bot"
GIT_EMAIL="lab@example.com"

# Database
DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/cooking_mcp"

# Slack (optional)
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret

# Additional providers as needed
TELEGRAM_BOT_TOKEN=your-telegram-token
TWILIO_SID=your-twilio-sid
# ... etc
```

### Slack Integration Setup

1. Create a new Slack app at https://api.slack.com/apps
2. Enable the following bot scopes:
   - `chat:write`
   - `commands`
   - `im:write`
   - `users:read`
3. Install the app to your workspace
4. Copy the bot token and signing secret to your environment variables
5. Set up the slash command `/cook-feedback` pointing to your bridge URL

## Usage

### Creating a Recipe Entry

```bash
# Via MCP tool
create_entry(title="Grilled Ribeye", tags=["beef", "grilling"], gear=["recteq"], dinner_time="2024-01-15T18:30:00Z")
```

### Adding Observations During Cooking

```bash
# Via MCP tool
append_observation(id="2024-01-15_grilled-ribeye", note="Internal temp reached 125°F", grill_temp_c=220, internal_temp_c=52)
```

### Collecting Feedback via Slack

```bash
/cook-feedback 2024-01-15_grilled-ribeye
```

This opens a modal to collect structured feedback on doneness, seasoning, and other factors.

### Updating Final Outcomes

```bash
# Via MCP tool
update_outcomes(id="2024-01-15_grilled-ribeye", outcomes={
  "rating_10": 8,
  "issues": ["slightly overcooked"],
  "fixes_next_time": ["pull at 120°F instead of 125°F"]
})
```

## API Reference

### MCP Resources

- `lab://entries` - Paginated entry index
- `lab://entry/{id}` - Full entry content
- `lab://search?q=...` - Semantic search

### MCP Tools

- `create_entry(title, tags, gear, dinner_time?)`
- `append_observation(id, note, time?, grill_temp_c?, internal_temp_c?)`
- `update_outcomes(id, outcomes)`
- `git_commit(message)`

### REST API

- `POST /mcp/create_entry` - Create new recipe entry
- `POST /mcp/append_observation` - Add cooking observation
- `POST /mcp/update_outcomes` - Update final results
- `GET /mcp/entry/{id}` - Retrieve entry data

## Development

### Running Tests

```bash
# Python tests
pytest

# Node.js tests
cd slack-app && npm test
```

### Code Quality

```bash
# Python formatting and linting
black .
pylint cooking_mcp/

# Node.js formatting and linting
cd slack-app && npm run lint
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head
```

## Deployment

### Production Environment

See `CLAUDE.md` for comprehensive deployment specifications including:

- Kubernetes orchestration
- Security configuration
- Monitoring and observability
- Disaster recovery procedures

### Quick Production Setup

1. Set up Kubernetes cluster
2. Configure secrets and ConfigMaps
3. Deploy using provided Helm charts
4. Set up monitoring and alerting
5. Configure backup procedures

## Troubleshooting

### Common Issues

**MCP Server not responding**
- Check if the server is running in stdio mode
- Verify environment variables are set correctly
- Check logs for initialization errors

**Slack app not receiving events**
- Verify webhook URL is accessible from internet
- Check signing secret configuration
- Ensure bot has required permissions

**Database connection issues**
- Verify DATABASE_URL format
- Check database server is running
- Ensure migrations are up to date

### Logs

```bash
# View all service logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f mcp-server
docker-compose logs -f slack-app
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## License

[Specify your license here]

## Support

For issues and questions, please check the troubleshooting section above or create an issue in the repository.