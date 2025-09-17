# Development Setup Guide

## Project Status

### ✅ Completed Components

- **Core Infrastructure**: FastAPI application with complete MCP v0.1.0 server implementation
- **Database Setup**: PostgreSQL with Alembic migrations successfully deployed
- **MCP Protocol Compliance**: All compliance tests passing
- **Docker Environment**: Multi-container setup with PostgreSQL and Redis
- **Git Repository**: Initialized with proper .gitignore and directory structure
- **Testing Framework**: Comprehensive test structure and MCP compliance validation

### 🔧 Working Components

- **API Health Checks**: Basic readiness endpoint working (port conflicts resolved)
- **MCP Server**: Resource and tool handlers implemented
- **Database Models**: SQLAlchemy models for notebook entries and feedback
- **Security Infrastructure**: Basic auth framework in place

### 🐛 Known Issues to Fix

1. **Health Endpoint**: JSON serialization issues with datetime objects in HTTPException responses
2. **Database Queries**: Async SQLAlchemy query issues (`Row` object await problems)
3. **Git Repository Structure**: Notebook directory needs to be initialized as git repo
4. **Health Checks**: Full health endpoint needs debugging for comprehensive status

## Development Environment Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- PostgreSQL client (optional, for direct DB access)

### Quick Start

1. **Clone and Setup**:
   ```bash
   cd /path/to/cooking_mcp
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Start Infrastructure**:
   ```bash
   # Start database and Redis (uses non-standard ports to avoid conflicts)
   docker compose up -d db redis
   ```

3. **Environment Configuration**:
   ```bash
   # Copy and configure environment
   cp .env.example .env
   # Edit .env with your settings (already configured for development)
   ```

4. **Database Setup**:
   ```bash
   # Run migrations
   export DATABASE_URL="postgresql+asyncpg://cooking_user:cooking_pass@localhost:5433/cooking_mcp"
   alembic upgrade head
   ```

5. **Run Application**:
   ```bash
   # Start the FastAPI server
   export DATABASE_URL="postgresql+asyncpg://cooking_user:cooking_pass@localhost:5433/cooking_mcp"
   python -m app.main
   ```

### Services and Ports

- **Application**: http://localhost:8000
- **PostgreSQL**: localhost:5433 (external), 5432 (internal)
- **Redis**: localhost:6380 (external), 6379 (internal)
- **API Documentation**: http://localhost:8000/api/docs (development only)

### Testing

```bash
# Run MCP compliance tests
python test_mcp_minimal.py     # Basic compliance
python test_mcp_compliance.py  # Comprehensive compliance

# Check API health
curl http://localhost:8000/health/ready
curl http://localhost:8000/health/live
```

### Database Management

```bash
# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Reset database (careful!)
alembic downgrade base
alembic upgrade head
```

## Project Structure

```
cooking_mcp/
├── app/                    # Main application
│   ├── models/            # SQLAlchemy models
│   ├── routers/           # FastAPI routers
│   ├── services/          # Business logic
│   └── utils/             # Utilities
├── alembic/               # Database migrations
├── notebook/              # Git-backed notebook storage
├── tests/                 # Test suite
├── logs/                  # Application logs
└── docker-compose.yml     # Development infrastructure
```

## MCP Protocol Implementation

### Resources Available

- `lab://entries` - Paginated notebook entries
- `lab://entry/{id}` - Individual notebook entry
- `lab://attachments/{id}/` - Entry attachments
- `lab://search` - Search functionality

### Tools Available

- `append_observation` - Add timestamped observations
- `update_outcomes` - Update cooking outcomes
- `create_entry` - Create new notebook entries
- `git_commit` - Commit changes to Git
- `synthesize_ics` - Generate calendar files

### API Endpoints

- `GET /health/` - Comprehensive health check
- `GET /health/ready` - Readiness probe
- `GET /health/live` - Liveness probe
- `POST /mcp/resources` - List MCP resources
- `POST /mcp/resource/{uri}` - Read specific resource
- `POST /mcp/tools` - List available tools
- `POST /mcp/tool/{name}` - Execute tool

## Next Development Steps

### Immediate Priorities

1. **Fix Health Endpoint Issues**:
   - Resolve JSON serialization for datetime objects
   - Fix async SQLAlchemy query patterns
   - Initialize notebook directory as git repository

2. **Complete Core MCP Features**:
   - Test end-to-end MCP tool operations
   - Validate notebook entry CRUD operations
   - Implement attachment handling

3. **Slack Integration**:
   - Implement Bolt framework bot
   - Create feedback collection modals
   - Set up scheduled notifications

### Medium-term Goals

1. **Multi-Channel Support**:
   - Telegram integration
   - WhatsApp Business API
   - SMS via Twilio
   - Email notifications

2. **AI/ML Features**:
   - Semantic search with embeddings
   - Recipe recommendations
   - Cooking outcome predictions
   - Natural language processing

3. **Security Hardening**:
   - Complete authentication system
   - Rate limiting implementation
   - Input validation enhancement
   - Security monitoring

### Production Readiness

1. **Monitoring & Observability**:
   - Prometheus metrics
   - Grafana dashboards
   - Structured logging
   - Performance monitoring

2. **Deployment**:
   - Kubernetes manifests
   - CI/CD pipeline
   - Environment-specific configs
   - Blue-green deployment

## Troubleshooting

### Common Issues

1. **Port Conflicts**:
   - PostgreSQL: Change from 5432 to 5433 in docker-compose.yml
   - Redis: Change from 6379 to 6380 in docker-compose.yml

2. **Database Connection Issues**:
   - Ensure Docker services are running: `docker compose ps`
   - Check environment variables: `echo $DATABASE_URL`
   - Verify network connectivity: `docker compose logs db`

3. **MCP Compliance Failures**:
   - Check model imports: `python -c "from app.models.mcp import *"`
   - Validate schemas: Run test_mcp_minimal.py for detailed output

### Logs and Debugging

- Application logs: `./logs/app.log`
- Docker logs: `docker compose logs -f [service]`
- Database logs: `docker compose logs db`
- Redis logs: `docker compose logs redis`

## Configuration

### Environment Variables

Key variables in `.env`:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://cooking_user:cooking_pass@localhost:5433/cooking_mcp

# Redis
REDIS_URL=redis://localhost:6380/0

# Application
ENVIRONMENT=development
DEBUG=true
SECRET_KEY=dev-secret-key-change-in-production

# Git
GIT_AUTHOR_NAME="Lab Bot"
GIT_AUTHOR_EMAIL="lab@cookingmcp.local"
REPO_ROOT=./notebook
```

### Docker Configuration

Services defined in `docker-compose.yml`:

- **PostgreSQL 15**: Primary database
- **Redis 7**: Caching and session storage
- **Application**: FastAPI server (when using Docker)

## Contributing

1. **Code Standards**:
   - Follow PEP 8 for Python
   - Use type hints throughout
   - Write comprehensive docstrings
   - Add tests for new features

2. **Git Workflow**:
   - Feature branches: `feature/description`
   - Commit messages: `component(scope): description`
   - Pull request reviews required

3. **Testing Requirements**:
   - Unit tests for all new functions
   - Integration tests for API endpoints
   - MCP compliance tests must pass
   - Health checks must be functional

---

**Last Updated**: September 17, 2025
**MCP Protocol Version**: v0.1.0
**Application Version**: 0.1.0