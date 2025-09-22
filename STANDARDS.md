# MCP Cooking Lab Notebook - Development Standards

This document defines **practical, achievable standards** for the MCP (Model Context Protocol) cooking lab notebook system. These are outcome-based requirements focused on building a maintainable, secure, and useful family-scale application.

## Core Principle

**Build useful, maintainable software.** This means creating clean, documented code that solves real problems without over-engineering. Focus on modern Python patterns, MCP protocol compliance, and family-appropriate architecture.

---

## 1. Code Quality Standards

### Code Must Be Readable and Simple
- **FastAPI Conventions**: Follow FastAPI's recommended patterns and async/await usage
- **Clear Purpose**: Each function/class has a single, obvious responsibility
- **Type Hints**: Mandatory type hints for all function signatures using Python 3.12+ features
- **Pydantic Models**: Use Pydantic v2 for data validation and serialization
- **Minimal Complexity**: Prefer simple solutions over clever ones

### Code Must Be Well-Documented
- **Docstrings**: All public functions and classes have clear docstrings
- **OpenAPI Documentation**: Auto-generated API docs with proper descriptions
- **README**: Clear setup and usage instructions
- **MCP Protocol Documentation**: Document resource and tool implementations

### Code Must Be Consistent
- **Python PEP 8**: Follow standard Python style guidelines
- **Ruff Formatting**: Use Ruff for linting and formatting (replaces Black, isort, flake8)
- **Import Organization**: Consistent import ordering and grouping
- **Async Patterns**: Consistent use of async/await for I/O operations

---

## 2. FastAPI Best Practices

### API Design Standards
- **Async Functions**: Use async def for all endpoints with I/O operations
- **Dependency Injection**: Use FastAPI's Depends() for shared logic
- **Response Models**: Separate input/output Pydantic models
- **Error Handling**: Proper HTTP status codes and structured error responses

```python
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

class AppendObservationRequest(BaseModel):
    id: str = Field(..., regex="^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$")
    note: str = Field(..., min_length=1, max_length=1000)
    grill_temp_c: Optional[int] = Field(None, ge=0, le=1000)
    internal_temp_c: Optional[int] = Field(None, ge=0, le=200)

class AppendObservationResponse(BaseModel):
    status: str
    commit_sha: Optional[str] = None
    message: str

@app.post("/mcp/append_observation", response_model=AppendObservationResponse)
async def append_observation(
    request: AppendObservationRequest,
    auth: AuthToken = Depends(verify_auth_token)
):
    try:
        result = await mcp_client.append_observation(**request.dict())
        return AppendObservationResponse(
            status="success",
            commit_sha=result.get("commit_sha"),
            message="Observation appended successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### MCP Protocol Standards
- **Resource URIs**: Follow `lab://` scheme for all resources
- **Tool Idempotency**: All tools must be idempotent with proper locking
- **Error Codes**: Use standardized error codes (E_NOT_FOUND, E_SCHEMA, etc.)
- **Protocol Compliance**: Adhere to MCP v0.1.0 specification

### Database Integration
- **SQLAlchemy Async**: Use async SQLAlchemy patterns for database operations
- **Connection Pooling**: Proper connection pool configuration
- **Transaction Management**: Explicit transaction boundaries
- **Query Optimization**: Use select_related equivalents and proper indexing

---

## 3. Frontend Standards (Astro + TypeScript)

### Astro Framework Patterns
- **Static First**: Prefer static generation over client-side rendering
- **Islands Architecture**: Use interactive components only when needed
- **File Organization**: Follow Astro's `src/` directory structure
- **Component Design**: Single responsibility with clear prop interfaces

```astro
---
// RecipeCard.astro
interface Props {
  recipe: {
    id: string;
    title: string;
    rating_10?: number;
    tags: string[];
  };
}

const { recipe } = Astro.props;
---

<div class="recipe-card">
  <h3 class="text-xl font-semibold mb-2">{recipe.title}</h3>
  <div class="flex items-center gap-2 mb-3">
    {recipe.rating_10 && (
      <span class="text-yellow-500">★ {recipe.rating_10}/10</span>
    )}
    <div class="flex gap-1">
      {recipe.tags.map(tag => (
        <span class="px-2 py-1 bg-gray-100 text-xs rounded">{tag}</span>
      ))}
    </div>
  </div>
</div>
```

### TypeScript Standards
- **Strict Mode**: Enable strict TypeScript configuration
- **Interface Definitions**: Define interfaces for all data structures
- **Type Safety**: Avoid `any` type, use proper type assertions
- **Generic Types**: Use generics for reusable components

### Tailwind CSS Standards
- **Utility-First**: Use Tailwind utilities for styling
- **Component Classes**: Create component classes for repeated patterns
- **Responsive Design**: Mobile-first responsive utilities
- **Design System**: Consistent spacing, colors, and typography

```css
/* Component classes for common patterns */
@layer components {
  .recipe-card {
    @apply bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow;
  }

  .btn-primary {
    @apply px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:ring-2 focus:ring-blue-500;
  }
}
```

---

## 4. Testing Standards

### FastAPI Testing
- **TestClient**: Use FastAPI's TestClient for endpoint testing
- **Async Testing**: Use pytest-asyncio for async function testing
- **Mock External Services**: Mock Slack API, Git operations, and AI services
- **Pydantic Validation**: Test model validation and serialization

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

def test_append_observation_success():
    """Test successful observation append"""
    payload = {
        "id": "2024-12-15_grilled-chicken",
        "note": "Perfect internal temperature",
        "internal_temp_c": 165
    }
    headers = {"Authorization": "Bearer test-token"}

    with patch('app.services.mcp_client.append_observation') as mock_mcp:
        mock_mcp.return_value = {"commit_sha": "abc123"}
        response = client.post("/mcp/append_observation",
                             json=payload, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "success"
```

### MCP Protocol Testing
- **Resource Contract Testing**: Validate resource URI formats and responses
- **Tool Validation**: Test tool parameter validation and execution
- **Protocol Compliance**: Ensure adherence to MCP specification
- **Error Handling**: Test all error conditions and codes

### Slack Integration Testing
- **Webhook Testing**: Test Slack webhook endpoints with proper signatures
- **Modal Handling**: Test modal submission and validation
- **Event Processing**: Test async event processing patterns
- **Rate Limiting**: Test Slack API rate limit handling

### Testing Coverage Targets
- **API Endpoints**: 85% coverage
- **MCP Protocol**: 90% coverage
- **Business Logic**: 85% coverage
- **Slack Integration**: 80% coverage

---

## 5. Security Standards (FastAPI-Focused)

### Authentication & Authorization
- **JWT Tokens**: Use RS256 with proper token validation
- **Bearer Token Auth**: Standard Authorization header pattern
- **Rate Limiting**: Redis-based sliding window rate limiting
- **Request Validation**: Pydantic models with field validators

```python
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer
import jwt

security = HTTPBearer()

async def verify_auth_token(token: str = Depends(security)):
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=["RS256"])
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

### Input Validation & Security
- **Pydantic Validation**: Comprehensive input validation with Pydantic v2
- **Path Traversal Protection**: Validate all file paths against traversal attacks
- **SQL Injection Prevention**: Use SQLAlchemy parameterized queries
- **CORS Configuration**: Properly configured CORS middleware

### Slack Integration Security
- **Signature Verification**: Validate Slack webhook signatures
- **Token Management**: Secure storage of Slack bot tokens
- **Rate Limiting**: Respect Slack API rate limits
- **Event Deduplication**: Prevent duplicate event processing

### Repository Security
- **Comprehensive .gitignore**: Prevent secrets from entering version control
- **Environment Variables**: Use .env files for configuration
- **Secret Management**: Keep API keys and tokens out of code
- **SSL Certificates**: Not stored in repository

---

## 6. Git Integration Standards

### Safe Git Operations
- **LibGit2/PyGit2**: Use Git libraries instead of shell commands
- **File Locking**: Implement proper locking for concurrent writes
- **Path Validation**: Validate all paths against traversal attacks
- **Atomic Operations**: Ensure Git operations are atomic with rollback capability

```python
import git
from pathlib import Path
import fcntl

class GitRepository:
    def __init__(self, repo_path: str):
        self.repo = git.Repo(repo_path)
        self.repo_path = Path(repo_path)

    async def append_observation(self, entry_id: str, note: str, **kwargs):
        # Validate entry ID against path traversal
        if ".." in entry_id or "/" in entry_id:
            raise ValueError("Invalid entry ID: path traversal detected")

        entry_path = self.repo_path / "entries" / f"{entry_id}.md"

        # File locking for concurrent access
        with open(entry_path, 'a') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            # Append observation content
            f.write(f"\n- {note}\n")

        # Commit changes
        self.repo.index.add([str(entry_path)])
        commit = self.repo.index.commit(f"obs({entry_id}): {note[:50]}...")
        return {"commit_sha": commit.hexsha}
```

### Repository Structure
```
/entries/
  ├── 2024/
  │   ├── 12/
  │   │   ├── 2024-12-15_grilled-chicken.md
  │   │   └── attachments/
  └── index.json (cached entry list)
```

### Commit Standards
- **Author**: "Lab Bot <lab@family.local>"
- **Message Format**: "action(entry_id): description"
- **Metadata**: Include user attribution in commit messages
- **GPG Signing**: Optional GPG signature for commits

---

## 7. Deployment Standards (Family-Scale)

### Container Standards
- **Multi-stage Builds**: Optimize Docker images with multi-stage builds
- **Security**: Run as non-root user, no secrets in images
- **Health Checks**: Include proper health check endpoints
- **Base Images**: Use official Python 3.12-slim images

```dockerfile
FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    git \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    git \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash app
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .
RUN chown -R app:app /app
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose for Development
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/cooking_lab
      - REDIS_URL=redis://redis:6379
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./recipes:/app/recipes
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: cooking_lab
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    depends_on:
      - app

volumes:
  postgres_data:
  caddy_data:
```

### Production Deployment (Railway/Render)
- **Managed Services**: Use Railway or Render for hosting
- **Environment Variables**: Secure configuration via platform environment
- **Automatic Deployments**: Git-based deployments
- **Health Monitoring**: Platform-native health checks

---

## 8. AI Integration Standards

### LLM Integration
- **Multiple Providers**: Support OpenAI GPT-4o-mini and Anthropic Claude
- **Cost Management**: Track token usage and implement budgets
- **Error Handling**: Graceful fallback between providers
- **Response Validation**: Validate AI responses for safety and format

```python
import openai
from anthropic import Anthropic
import asyncio

class AIService:
    def __init__(self):
        self.openai_client = openai.AsyncOpenAI()
        self.anthropic_client = Anthropic()

    async def analyze_recipe(self, recipe_text: str) -> str:
        """Get recipe analysis with fallback providers"""
        try:
            # Primary: GPT-4o-mini (cost-effective)
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": f"Analyze this recipe and suggest improvements: {recipe_text}"
                }],
                max_tokens=200,
                timeout=5.0
            )
            return response.choices[0].message.content
        except Exception:
            # Fallback: Claude Haiku
            response = await self.anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": f"Analyze this recipe and suggest improvements: {recipe_text}"
                }]
            )
            return response.content[0].text
```

### Token Management
- **Usage Tracking**: Monitor token consumption per request
- **Cost Alerts**: Alert when approaching budget limits
- **Rate Limiting**: Respect API rate limits
- **Caching**: Cache AI responses when appropriate

---

## 9. Monitoring & Observability (Family-Scale)

### Health Checks
```python
from fastapi import FastAPI
from app.database import check_database_health
from app.git_ops import check_git_repository

@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    # Database health
    try:
        await check_database_health()
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        health_status["checks"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    # Git repository health
    try:
        check_git_repository()
        health_status["checks"]["git"] = "healthy"
    except Exception as e:
        health_status["checks"]["git"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    return health_status
```

### Structured Logging
```python
import structlog
import logging

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Usage in application
async def append_observation(entry_id: str, note: str):
    logger.info("Appending observation",
               entry_id=entry_id,
               note_length=len(note),
               user_id=current_user.id)
```

### Simple Metrics (Optional)
- **Platform Metrics**: Use Railway/Render built-in monitoring
- **Application Metrics**: Basic counters for key operations
- **Error Tracking**: Simple error reporting (Sentry free tier)
- **Log Analysis**: Basic log aggregation and search

---

## 10. Development Workflow

### Version Control
- **Git**: Use Git for version control with clear commit messages
- **Branching**: Simple branching strategy (main + feature branches)
- **Commit Messages**: Format: "type(scope): description"
- **Repository Security**: Comprehensive .gitignore file

### Code Review Standards
- **Peer Review**: Review significant changes for security and functionality
- **Automated Checks**: Run linting, type checking, and tests
- **Security Review**: Check for exposed secrets or security issues
- **Performance Review**: Ensure changes don't degrade performance

### CI/CD Pipeline
```yaml
# .github/workflows/test.yml
name: Test Suite
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Lint with Ruff
        run: ruff check .

      - name: Type check with mypy
        run: mypy app/

      - name: Test with pytest
        run: pytest --cov=app --cov-report=xml
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## 11. Verification Checklist

Before considering work complete:

### ✅ Functionality
- [ ] All FastAPI endpoints work correctly
- [ ] MCP protocol compliance validated
- [ ] Slack integration functions properly
- [ ] Git operations are atomic and safe
- [ ] AI integrations respond within SLA

### ✅ Code Quality
- [ ] Code follows FastAPI and Python conventions
- [ ] Type hints are complete and accurate
- [ ] Pydantic models validate correctly
- [ ] Async patterns used consistently
- [ ] Error handling is comprehensive

### ✅ Security
- [ ] JWT authentication works properly
- [ ] Input validation prevents injection attacks
- [ ] Path traversal protection implemented
- [ ] Slack webhook signatures verified
- [ ] No secrets committed to repository

### ✅ Testing
- [ ] Unit tests pass with >80% coverage
- [ ] Integration tests validate workflows
- [ ] MCP protocol compliance tested
- [ ] Slack integration tested with mocks
- [ ] Error conditions handled gracefully

### ✅ Deployment
- [ ] Docker image builds successfully
- [ ] Health checks respond correctly
- [ ] Environment variables configured
- [ ] Railway/Render deployment works
- [ ] Git repository accessible

### ✅ Documentation
- [ ] OpenAPI documentation is complete
- [ ] README includes setup instructions
- [ ] Complex business logic documented
- [ ] MCP protocol implementation documented

---

## What Makes This Different

### Family-Scale Focus
- **Trusted Users**: 2-6 family members, not public internet users
- **Predictable Usage**: Known usage patterns and simple workflows
- **Appropriate Security**: Security measures proportional to family use
- **Direct Support**: Can provide direct user support when needed

### Modern Technology Stack
- **FastAPI**: Async-first Python web framework with automatic API docs
- **MCP Protocol**: Future-proof integration with Claude and other AI tools
- **Astro**: Modern static site generator with island architecture
- **Managed Deployment**: Railway/Render for zero-ops deployment

### Practical Implementation
- **Working Software**: Prefer working features over perfect architecture
- **Iterative Improvement**: Get basic functionality working, then enhance
- **Cost-Effective**: Optimize for family budget (~$10-20/month)
- **Maintainable**: Single person can maintain and extend the system

### Work Tracking
- **Progress Tracking**: You will record your progress in DEVELOPMENT.md without fail.
- **Duplicative Work**: If you have to repeat work because you did not track it, that work should not be charged
---

## Non-Compliance

Work that does not meet these standards should be revised before:
- Merging to main branch
- Deploying to production
- Marking tasks as complete

These standards are **practical and achievable** for a family-scale MCP application. They focus on creating maintainable, secure, and useful software with modern Python patterns and appropriate complexity for the use case.

Remember: You're building a useful family tool for cooking documentation, not an enterprise SaaS product. Keep it simple, keep it working, and keep it maintainable.