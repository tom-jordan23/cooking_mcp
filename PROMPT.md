# MCP Cooking Lab Notebook - Structured Development Process

This document provides a comprehensive, methodical development process for building the MCP (Model Context Protocol) cooking lab notebook system. It incorporates all standards from `STANDARDS.md` and ensures systematic development with proper validation at each step.

## Overview

The development process is designed to:
- **Work methodically** through each component with proper validation
- **Use all agents** for their specialized expertise
- **Resolve errors immediately** before proceeding
- **Confirm functionality** at each stage
- **Follow standards** from STANDARDS.md consistently
- **Build incrementally** with working software at each phase

---

## Development Phases

### Phase 1: Foundation & Core Infrastructure (Week 1)
- MCP Server core implementation
- Basic FastAPI application structure
- Git repository operations
- Database setup and models
- Authentication framework

### Phase 2: MCP Protocol Implementation (Week 2)
- MCP resources (lab://entries, lab://entry/{id}, lab://search)
- MCP tools (append_observation, update_outcomes, create_entry)
- Protocol compliance validation
- Error handling and status codes

### Phase 3: Slack Integration (Week 3)
- Slack Bolt framework setup
- Modal-based feedback collection
- Webhook endpoint implementation
- Event processing and scheduling

### Phase 4: Frontend Interface (Week 4)
- Astro framework setup
- Recipe viewing and editing interfaces
- TypeScript components
- Responsive design with Tailwind CSS

### Phase 5: Integration & Testing (Week 5)
- End-to-end workflow testing
- Performance optimization
- Security validation
- Deployment preparation

### Phase 6: Deployment & Polish (Week 6)
- Production deployment setup
- Monitoring and observability
- Documentation completion
- Final testing and validation

---

## Structured Development Process

### Step Format

Each development step follows this structure:

```markdown
## Step X.Y: [Task Name]

### 🎯 Objective
Clear description of what this step achieves

### 📋 Requirements
- Specific deliverables
- Success criteria
- Dependencies

### 🔧 Implementation Tasks
1. Detailed task list
2. With specific agents assigned
3. Including validation steps

### ✅ Validation Checklist
- [ ] Functional requirements met
- [ ] Standards compliance verified
- [ ] Tests passing
- [ ] No errors or warnings
- [ ] Documentation updated

### 🚀 Agent Assignments
- **Agent Type**: Specific responsibilities
- **Validation**: How success is confirmed

### 🔍 Review & Sign-off
- Code review completed
- Standards verification
- Functionality confirmed
- Ready for next step
```

---

## Phase 1: Foundation & Core Infrastructure

### Step 1.1: Project Setup & Environment

#### 🎯 Objective
Establish the project foundation with proper tooling, dependencies, and development environment.

#### 📋 Requirements
- Python 3.12+ development environment
- FastAPI project structure
- Development dependencies configured
- Git repository initialized with proper .gitignore
- Docker development environment ready

#### 🔧 Implementation Tasks

1. **Initialize Project Structure**
   ```bash
   mkdir cooking_mcp
   cd cooking_mcp
   git init
   ```

2. **Create Core Directory Structure**
   ```
   cooking_mcp/
   ├── app/
   │   ├── __init__.py
   │   ├── main.py
   │   ├── models/
   │   ├── services/
   │   ├── routers/
   │   └── utils/
   ├── tests/
   ├── docs/
   ├── docker/
   ├── requirements.txt
   ├── requirements-dev.txt
   ├── pyproject.toml
   ├── Dockerfile
   ├── docker-compose.yml
   └── .env.example
   ```

3. **Setup Dependencies**
   ```bash
   # requirements.txt
   fastapi[all]==0.115.0
   uvicorn[standard]==0.24.0
   pydantic==2.9.0
   sqlalchemy[asyncio]==2.0.0
   asyncpg==0.29.0
   alembic==1.13.0
   redis==5.0.0
   gitpython==3.1.40
   structlog==23.2.0
   python-multipart==0.0.6
   python-jose[cryptography]==3.3.0
   python-dotenv==1.0.0

   # requirements-dev.txt
   pytest==7.4.0
   pytest-asyncio==0.21.0
   pytest-cov==4.1.0
   httpx==0.27.0
   ruff==0.1.7
   mypy==1.7.0
   pre-commit==3.6.0
   ```

4. **Configure Development Tools**
   ```toml
   # pyproject.toml
   [tool.ruff]
   target-version = "py312"
   line-length = 88
   select = ["E", "F", "I", "N", "W", "UP"]

   [tool.mypy]
   python_version = "3.12"
   strict = true
   warn_return_any = true
   warn_unused_configs = true
   ```

#### ✅ Validation Checklist
- [ ] Python 3.12+ installed and verified
- [ ] All dependencies install without errors
- [ ] Directory structure created correctly
- [ ] Git repository initialized with comprehensive .gitignore
- [ ] Development tools (ruff, mypy) run without errors
- [ ] Docker environment builds successfully

#### 🚀 Agent Assignments
- **DevOps Engineer**: Docker setup, dependency management, build verification
- **General Purpose**: Project structure, configuration files, tool setup

#### 🔍 Review & Sign-off
- All tools run without errors
- Project structure follows Python/FastAPI conventions
- .gitignore prevents secrets from being committed
- Ready for core application development

---

### Step 1.2: FastAPI Core Application

#### 🎯 Objective
Create the foundational FastAPI application with proper async patterns, logging, and health checks.

#### 📋 Requirements
- FastAPI application with async support
- Structured logging configured
- Health check endpoint implemented
- Basic error handling middleware
- CORS and security middleware configured

#### 🔧 Implementation Tasks

1. **Create Main Application**
   ```python
   # app/main.py
   from fastapi import FastAPI, HTTPException
   from fastapi.middleware.cors import CORSMiddleware
   from fastapi.middleware.trustedhost import TrustedHostMiddleware
   import structlog
   from datetime import datetime

   # Configure structured logging
   structlog.configure(
       processors=[
           structlog.stdlib.filter_by_level,
           structlog.stdlib.add_logger_name,
           structlog.stdlib.add_log_level,
           structlog.processors.TimeStamper(fmt="iso"),
           structlog.processors.JSONRenderer()
       ],
       context_class=dict,
       logger_factory=structlog.stdlib.LoggerFactory(),
       wrapper_class=structlog.stdlib.BoundLogger,
       cache_logger_on_first_use=True,
   )

   logger = structlog.get_logger()

   app = FastAPI(
       title="MCP Cooking Lab Notebook",
       description="Family cooking lab notebook with MCP protocol support",
       version="0.1.0",
       docs_url="/docs",
       redoc_url="/redoc"
   )

   # Add security middleware
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["http://localhost:3000"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )

   app.add_middleware(
       TrustedHostMiddleware,
       allowed_hosts=["localhost", "*.railway.app"]
   )

   @app.get("/health")
   async def health_check():
       """Health check endpoint"""
       return {
           "status": "healthy",
           "timestamp": datetime.utcnow().isoformat(),
           "service": "mcp-cooking-lab"
       }

   @app.get("/")
   async def root():
       """Root endpoint"""
       return {"message": "MCP Cooking Lab Notebook API"}

   if __name__ == "__main__":
       import uvicorn
       uvicorn.run(app, host="0.0.0.0", port=8000)
   ```

2. **Create Configuration Management**
   ```python
   # app/config.py
   from pydantic_settings import BaseSettings
   from typing import Optional

   class Settings(BaseSettings):
       # Database
       database_url: str = "sqlite:///./cooking_lab.db"

       # Redis
       redis_url: str = "redis://localhost:6379"

       # Git Repository
       git_repo_path: str = "./notebook"
       git_author_name: str = "Lab Bot"
       git_author_email: str = "lab@family.local"

       # Authentication
       secret_key: str
       algorithm: str = "HS256"
       access_token_expire_minutes: int = 30

       # Slack
       slack_bot_token: Optional[str] = None
       slack_signing_secret: Optional[str] = None

       # AI Services
       openai_api_key: Optional[str] = None
       anthropic_api_key: Optional[str] = None

       class Config:
           env_file = ".env"

   settings = Settings()
   ```

3. **Create Error Handling**
   ```python
   # app/exceptions.py
   from fastapi import HTTPException, Request
   from fastapi.responses import JSONResponse
   import structlog

   logger = structlog.get_logger()

   class MCPError(Exception):
       """Base MCP protocol error"""
       def __init__(self, code: str, message: str, details: dict = None):
           self.code = code
           self.message = message
           self.details = details or {}
           super().__init__(message)

   class EntryNotFoundError(MCPError):
       def __init__(self, entry_id: str):
           super().__init__(
               code="E_NOT_FOUND",
               message=f"Entry not found: {entry_id}",
               details={"entry_id": entry_id}
           )

   class SchemaValidationError(MCPError):
       def __init__(self, message: str, field: str = None):
           super().__init__(
               code="E_SCHEMA",
               message=f"Schema validation error: {message}",
               details={"field": field} if field else {}
           )

   async def mcp_exception_handler(request: Request, exc: MCPError):
       """Handle MCP protocol exceptions"""
       logger.error("MCP error occurred",
                   code=exc.code,
                   message=exc.message,
                   details=exc.details,
                   path=request.url.path)

       status_code = 400 if exc.code == "E_SCHEMA" else 404 if exc.code == "E_NOT_FOUND" else 500

       return JSONResponse(
           status_code=status_code,
           content={
               "status": "error",
               "code": exc.code,
               "message": exc.message,
               "details": exc.details
           }
       )

   async def general_exception_handler(request: Request, exc: Exception):
       """Handle general exceptions"""
       logger.error("Unexpected error occurred",
                   error=str(exc),
                   error_type=type(exc).__name__,
                   path=request.url.path)

       return JSONResponse(
           status_code=500,
           content={
               "status": "error",
               "code": "E_INTERNAL",
               "message": "Internal server error"
           }
       )
   ```

#### ✅ Validation Checklist
- [ ] FastAPI application starts successfully
- [ ] Health check endpoint responds correctly
- [ ] Structured logging outputs JSON format
- [ ] CORS middleware configured properly
- [ ] Error handling returns proper JSON responses
- [ ] OpenAPI documentation accessible at /docs
- [ ] All type hints pass mypy validation
- [ ] Ruff linting passes without errors

#### 🚀 Agent Assignments
- **AI Engineer**: FastAPI setup, async patterns, middleware configuration
- **Security Engineer**: Security middleware, error handling, input validation patterns

#### 🔍 Review & Sign-off
- Application starts without errors
- All endpoints respond correctly
- Error handling returns structured responses
- Security middleware configured appropriately
- Code follows STANDARDS.md conventions

---

### Step 1.3: Database Models & Setup

#### 🎯 Objective
Implement SQLAlchemy async database models and connection management for the cooking lab notebook.

#### 📋 Requirements
- SQLAlchemy async models for recipes and feedback
- Database connection management with proper pooling
- Alembic migrations setup
- Database initialization and health checks

#### 🔧 Implementation Tasks

1. **Create Database Models**
   ```python
   # app/models/database.py
   from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
   from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
   from sqlalchemy import String, Text, DateTime, Integer, JSON, Index
   from datetime import datetime
   from typing import Optional, Dict, Any
   from app.config import settings

   class Base(DeclarativeBase):
       pass

   # Create async engine
   engine = create_async_engine(
       settings.database_url,
       echo=settings.debug if hasattr(settings, 'debug') else False,
       pool_size=5,
       max_overflow=10
   )

   async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

   class NotebookEntry(Base):
       __tablename__ = "notebook_entries"

       id: Mapped[str] = mapped_column(String(100), primary_key=True)
       title: Mapped[str] = mapped_column(String(200), nullable=False)
       content: Mapped[str] = mapped_column(Text, nullable=False)
       created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
       updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
       metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

       __table_args__ = (
           Index('idx_created_at', 'created_at'),
           Index('idx_title', 'title'),
       )

   class FeedbackEntry(Base):
       __tablename__ = "feedback_entries"

       id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
       entry_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
       who: Mapped[str] = mapped_column(String(100), nullable=False)
       timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
       rating_10: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
       notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
       axes: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON, nullable=True)
       metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

       __table_args__ = (
           Index('idx_entry_id_timestamp', 'entry_id', 'timestamp'),
       )

   # Database dependency
   async def get_database_session() -> AsyncSession:
       async with async_session_maker() as session:
           try:
               yield session
           finally:
               await session.close()

   async def init_database():
       """Initialize database tables"""
       async with engine.begin() as conn:
           await conn.run_sync(Base.metadata.create_all)

   async def check_database_health():
       """Check database connectivity"""
       async with async_session_maker() as session:
           await session.execute("SELECT 1")
   ```

2. **Create Pydantic Models**
   ```python
   # app/models/schemas.py
   from pydantic import BaseModel, Field, validator
   from datetime import datetime
   from typing import Optional, Dict, Any, List
   import re

   class EntryCreateRequest(BaseModel):
       title: str = Field(..., min_length=1, max_length=200)
       tags: Optional[List[str]] = Field(default_factory=list)
       gear: Optional[List[str]] = Field(default_factory=list)
       servings: Optional[int] = Field(None, ge=1, le=50)
       dinner_time: Optional[datetime] = None

   class AppendObservationRequest(BaseModel):
       id: str = Field(..., regex=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$")
       note: str = Field(..., min_length=1, max_length=1000)
       time: Optional[datetime] = None
       grill_temp_c: Optional[int] = Field(None, ge=0, le=1000)
       internal_temp_c: Optional[int] = Field(None, ge=0, le=200)

       @validator('id')
       def validate_entry_id(cls, v):
           if not re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$", v):
               raise ValueError("Invalid entry ID format")
           return v

   class UpdateOutcomesRequest(BaseModel):
       id: str = Field(..., regex=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$")
       rating_10: Optional[int] = Field(None, ge=1, le=10)
       issues: Optional[List[str]] = Field(default_factory=list)
       next_time: Optional[List[str]] = Field(default_factory=list)
       notes: Optional[str] = Field(None, max_length=2000)

   class FeedbackSubmissionRequest(BaseModel):
       entry_id: str = Field(..., regex=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$")
       who: str = Field(..., min_length=1, max_length=100)
       rating_10: Optional[int] = Field(None, ge=1, le=10)
       notes: Optional[str] = Field(None, max_length=1000)
       axes: Optional[Dict[str, str]] = Field(default_factory=dict)
       metrics: Optional[Dict[str, Any]] = Field(default_factory=dict)

   class StandardResponse(BaseModel):
       status: str
       message: str
       data: Optional[Dict[str, Any]] = None

   class ErrorResponse(BaseModel):
       status: str = "error"
       code: str
       message: str
       details: Optional[Dict[str, Any]] = None
   ```

3. **Setup Alembic Migrations**
   ```bash
   # Initialize Alembic
   alembic init alembic
   ```

   ```python
   # alembic/env.py (update target_metadata)
   from app.models.database import Base
   target_metadata = Base.metadata
   ```

   ```ini
   # alembic.ini (update sqlalchemy.url)
   sqlalchemy.url = sqlite:///./cooking_lab.db
   ```

#### ✅ Validation Checklist
- [ ] Database models created with proper relationships
- [ ] SQLAlchemy async patterns implemented correctly
- [ ] Pydantic models validate input properly
- [ ] Alembic migrations setup and working
- [ ] Database health check function works
- [ ] Connection pooling configured appropriately
- [ ] All models pass type checking
- [ ] Migration creates tables successfully

#### 🚀 Agent Assignments
- **AI Engineer**: SQLAlchemy models, async patterns, database configuration
- **General Purpose**: Pydantic schemas, validation, Alembic setup

#### 🔍 Review & Sign-off
- Database connection established successfully
- Models created and migrations run cleanly
- Pydantic validation working correctly
- Health check confirms database connectivity
- All code follows async patterns properly

---

### Step 1.4: Git Repository Operations

#### 🎯 Objective
Implement safe, atomic Git operations for managing the cooking lab notebook repository with proper locking and security.

#### 📋 Requirements
- Safe Git operations using GitPython library
- File locking for concurrent access
- Path traversal protection
- Atomic commit operations
- Repository initialization and validation

#### 🔧 Implementation Tasks

1. **Create Git Repository Service**
   ```python
   # app/services/git_repository.py
   import git
   import fcntl
   import os
   from pathlib import Path
   from datetime import datetime
   from typing import Optional, Dict, Any
   from contextlib import asynccontextmanager
   import structlog
   import tempfile
   import yaml

   logger = structlog.get_logger()

   class GitRepositoryService:
       def __init__(self, repo_path: str, author_name: str, author_email: str):
           self.repo_path = Path(repo_path)
           self.author_name = author_name
           self.author_email = author_email
           self.repo: Optional[git.Repo] = None
           self._init_repository()

       def _init_repository(self):
           """Initialize or open the Git repository"""
           try:
               if self.repo_path.exists() and (self.repo_path / ".git").exists():
                   self.repo = git.Repo(self.repo_path)
                   logger.info("Opened existing repository", path=str(self.repo_path))
               else:
                   self.repo_path.mkdir(parents=True, exist_ok=True)
                   self.repo = git.Repo.init(self.repo_path)

                   # Create initial directory structure
                   (self.repo_path / "entries").mkdir(exist_ok=True)
                   (self.repo_path / "attachments").mkdir(exist_ok=True)

                   # Create initial .gitignore
                   gitignore_content = """# Temporary files
   *.tmp
   *.swp
   .DS_Store

   # IDE files
   .vscode/
   .idea/
   """
                   (self.repo_path / ".gitignore").write_text(gitignore_content)

                   # Initial commit
                   self.repo.index.add([".gitignore", "entries/.gitkeep", "attachments/.gitkeep"])
                   self.repo.index.commit(
                       "Initial notebook repository setup",
                       author=git.Actor(self.author_name, self.author_email)
                   )

                   logger.info("Initialized new repository", path=str(self.repo_path))

           except Exception as e:
               logger.error("Failed to initialize repository", error=str(e))
               raise

       def _validate_entry_id(self, entry_id: str) -> None:
           """Validate entry ID against path traversal attacks"""
           if ".." in entry_id or "/" in entry_id or "\\" in entry_id:
               raise ValueError(f"Invalid entry ID: path traversal detected in '{entry_id}'")

           if not entry_id.replace("-", "").replace("_", "").isalnum():
               raise ValueError(f"Invalid entry ID: contains invalid characters '{entry_id}'")

       def get_entry_path(self, entry_id: str) -> Path:
           """Get the file path for an entry"""
           self._validate_entry_id(entry_id)

           # Extract date components for directory structure
           date_part = entry_id[:10]  # YYYY-MM-DD
           year = date_part[:4]
           month = date_part[5:7]

           entry_dir = self.repo_path / "entries" / year / month
           entry_dir.mkdir(parents=True, exist_ok=True)

           return entry_dir / f"{entry_id}.md"

       @asynccontextmanager
       async def _file_lock(self, file_path: Path):
           """Context manager for file locking"""
           lock_file = file_path.with_suffix(f"{file_path.suffix}.lock")

           try:
               # Create lock file
               with open(lock_file, 'w') as f:
                   fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                   yield
           except BlockingIOError:
               raise RuntimeError(f"Entry is currently being modified: {file_path.name}")
           finally:
               # Remove lock file
               if lock_file.exists():
                   lock_file.unlink()

       async def create_entry(self, entry_id: str, title: str, **metadata) -> Dict[str, str]:
           """Create a new notebook entry"""
           self._validate_entry_id(entry_id)
           entry_path = self.get_entry_path(entry_id)

           if entry_path.exists():
               raise ValueError(f"Entry already exists: {entry_id}")

           # Prepare entry content
           entry_metadata = {
               "id": entry_id,
               "title": title,
               "created_at": datetime.utcnow().isoformat(),
               "updated_at": datetime.utcnow().isoformat(),
               **metadata
           }

           content = f"""---
   {yaml.dump(entry_metadata, default_flow_style=False)}---

   # {title}

   ## Protocol

   ## Observations

   ## Outcomes
   """

           async with self._file_lock(entry_path):
               entry_path.write_text(content, encoding='utf-8')

           # Commit the new entry
           commit_sha = await self._commit_changes(
               f"create({entry_id}): {title}",
               [str(entry_path.relative_to(self.repo_path))]
           )

           logger.info("Created new entry", entry_id=entry_id, commit_sha=commit_sha)

           return {
               "status": "created",
               "entry_id": entry_id,
               "commit_sha": commit_sha,
               "path": str(entry_path.relative_to(self.repo_path))
           }

       async def append_observation(self, entry_id: str, note: str,
                                  timestamp: Optional[datetime] = None,
                                  **kwargs) -> Dict[str, str]:
           """Append an observation to an existing entry"""
           self._validate_entry_id(entry_id)
           entry_path = self.get_entry_path(entry_id)

           if not entry_path.exists():
               raise ValueError(f"Entry not found: {entry_id}")

           if timestamp is None:
               timestamp = datetime.utcnow()

           # Format observation
           observation = f"- **{timestamp.strftime('%H:%M')}**: {note}"

           # Add additional metrics if provided
           if kwargs:
               metrics = []
               for key, value in kwargs.items():
                   if value is not None:
                       metrics.append(f"{key}: {value}")
               if metrics:
                   observation += f" ({', '.join(metrics)})"

           observation += "\n"

           async with self._file_lock(entry_path):
               content = entry_path.read_text(encoding='utf-8')

               # Find the Observations section
               if "## Observations" in content:
                   # Append to existing observations
                   content = content.replace("## Observations\n", f"## Observations\n{observation}")
               else:
                   # Add observations section if it doesn't exist
                   content += f"\n## Observations\n{observation}"

               # Update the updated_at timestamp in frontmatter
               if content.startswith("---\n"):
                   try:
                       parts = content.split("---\n", 2)
                       if len(parts) >= 3:
                           frontmatter = yaml.safe_load(parts[1])
                           frontmatter["updated_at"] = datetime.utcnow().isoformat()
                           parts[1] = yaml.dump(frontmatter, default_flow_style=False)
                           content = "---\n".join(parts)
                   except Exception as e:
                       logger.warning("Failed to update frontmatter", error=str(e))

               entry_path.write_text(content, encoding='utf-8')

           # Commit the changes
           commit_sha = await self._commit_changes(
               f"obs({entry_id}): {note[:50]}{'...' if len(note) > 50 else ''}",
               [str(entry_path.relative_to(self.repo_path))]
           )

           logger.info("Appended observation",
                      entry_id=entry_id,
                      note_length=len(note),
                      commit_sha=commit_sha)

           return {
               "status": "appended",
               "entry_id": entry_id,
               "commit_sha": commit_sha
           }

       async def _commit_changes(self, message: str, files: list[str]) -> str:
           """Commit changes to the repository"""
           try:
               # Add files to index
               self.repo.index.add(files)

               # Create commit
               commit = self.repo.index.commit(
                   message,
                   author=git.Actor(self.author_name, self.author_email)
               )

               return commit.hexsha

           except Exception as e:
               logger.error("Failed to commit changes", error=str(e), files=files)
               raise

       def check_repository_health(self) -> Dict[str, Any]:
           """Check repository health"""
           try:
               status = {
                   "healthy": True,
                   "path": str(self.repo_path),
                   "exists": self.repo_path.exists(),
                   "is_git_repo": (self.repo_path / ".git").exists(),
                   "writable": os.access(self.repo_path, os.W_OK)
               }

               if self.repo:
                   try:
                       latest_commit = self.repo.head.commit
                       status["latest_commit"] = latest_commit.hexsha[:8]
                       status["commit_count"] = len(list(self.repo.iter_commits()))
                   except Exception as e:
                       status["git_error"] = str(e)

               return status

           except Exception as e:
               return {
                   "healthy": False,
                   "error": str(e)
               }
   ```

2. **Create Git Service Integration**
   ```python
   # app/services/__init__.py
   from app.services.git_repository import GitRepositoryService
   from app.config import settings

   # Initialize git service
   git_service = GitRepositoryService(
       repo_path=settings.git_repo_path,
       author_name=settings.git_author_name,
       author_email=settings.git_author_email
   )

   async def get_git_service() -> GitRepositoryService:
       """Dependency to get git service"""
       return git_service
   ```

3. **Add Git Health Check to Main App**
   ```python
   # Update app/main.py health check
   from app.services import git_service

   @app.get("/health")
   async def health_check():
       """Enhanced health check with git repository status"""
       health_status = {
           "status": "healthy",
           "timestamp": datetime.utcnow().isoformat(),
           "service": "mcp-cooking-lab",
           "checks": {}
       }

       # Git repository health
       try:
           git_health = git_service.check_repository_health()
           health_status["checks"]["git"] = git_health
           if not git_health.get("healthy", False):
               health_status["status"] = "unhealthy"
       except Exception as e:
           health_status["checks"]["git"] = {"healthy": False, "error": str(e)}
           health_status["status"] = "unhealthy"

       return health_status
   ```

#### ✅ Validation Checklist
- [ ] Git repository initializes correctly
- [ ] File locking prevents concurrent access issues
- [ ] Path traversal protection blocks malicious paths
- [ ] Atomic commits work properly
- [ ] Entry creation and observation appending functional
- [ ] Repository health check returns accurate status
- [ ] All Git operations are properly logged
- [ ] Error handling covers edge cases

#### 🚀 Agent Assignments
- **Security Engineer**: Path validation, file locking, security considerations
- **DevOps Engineer**: Git operations, repository management, error handling

#### 🔍 Review & Sign-off
- Repository operations work without errors
- Security measures prevent path traversal
- Concurrent access properly handled
- All operations properly logged
- Health checks confirm repository status

---

### Step 1.5: Authentication Framework

#### 🎯 Objective
Implement JWT-based authentication suitable for family-scale usage with proper token validation and security middleware.

#### 📋 Requirements
- JWT token generation and validation
- Family-appropriate authentication flow
- Security middleware for API endpoints
- Token refresh mechanisms
- Rate limiting implementation

#### 🔧 Implementation Tasks

1. **Create Authentication Service**
   ```python
   # app/services/auth.py
   from datetime import datetime, timedelta
   from typing import Optional, Dict, Any
   from jose import JWTError, jwt
   from passlib.context import CryptContext
   from fastapi import HTTPException, Depends, status
   from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
   import structlog
   from app.config import settings

   logger = structlog.get_logger()

   # Password hashing
   pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

   # JWT token handler
   security = HTTPBearer()

   class AuthService:
       def __init__(self):
           self.secret_key = settings.secret_key
           self.algorithm = settings.algorithm
           self.access_token_expire_minutes = settings.access_token_expire_minutes

       def verify_password(self, plain_password: str, hashed_password: str) -> bool:
           """Verify a password against its hash"""
           return pwd_context.verify(plain_password, hashed_password)

       def get_password_hash(self, password: str) -> str:
           """Hash a password"""
           return pwd_context.hash(password)

       def create_access_token(self, data: Dict[str, Any],
                             expires_delta: Optional[timedelta] = None) -> str:
           """Create a JWT access token"""
           to_encode = data.copy()

           if expires_delta:
               expire = datetime.utcnow() + expires_delta
           else:
               expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)

           to_encode.update({"exp": expire})

           encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

           logger.info("Created access token",
                      user=data.get("sub"),
                      expires=expire.isoformat())

           return encoded_jwt

       def verify_token(self, token: str) -> Dict[str, Any]:
           """Verify and decode a JWT token"""
           try:
               payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
               username: str = payload.get("sub")

               if username is None:
                   raise HTTPException(
                       status_code=status.HTTP_401_UNAUTHORIZED,
                       detail="Invalid token: missing subject",
                       headers={"WWW-Authenticate": "Bearer"},
                   )

               return payload

           except JWTError as e:
               logger.warning("Token verification failed", error=str(e))
               raise HTTPException(
                   status_code=status.HTTP_401_UNAUTHORIZED,
                   detail="Invalid token",
                   headers={"WWW-Authenticate": "Bearer"},
               )

       def authenticate_family_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
           """Authenticate a family user (simplified for family use)"""
           # Simple family authentication - in production, use proper user database
           family_users = {
               "parent1": {
                   "username": "parent1",
                   "password_hash": self.get_password_hash("family_password_2024"),
                   "role": "admin",
                   "display_name": "Parent 1"
               },
               "parent2": {
                   "username": "parent2",
                   "password_hash": self.get_password_hash("family_password_2024"),
                   "role": "admin",
                   "display_name": "Parent 2"
               },
               "kid1": {
                   "username": "kid1",
                   "password_hash": self.get_password_hash("kid_password_2024"),
                   "role": "viewer",
                   "display_name": "Kid 1"
               }
           }

           user = family_users.get(username)
           if user and self.verify_password(password, user["password_hash"]):
               return {
                   "username": user["username"],
                   "role": user["role"],
                   "display_name": user["display_name"]
               }

           return None

   # Initialize auth service
   auth_service = AuthService()

   async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
       """Get current authenticated user"""
       return auth_service.verify_token(credentials.credentials)

   async def get_current_admin_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
       """Get current user if they have admin privileges"""
       if current_user.get("role") != "admin":
           raise HTTPException(
               status_code=status.HTTP_403_FORBIDDEN,
               detail="Admin privileges required"
           )
       return current_user
   ```

2. **Create Authentication Routes**
   ```python
   # app/routers/auth.py
   from fastapi import APIRouter, HTTPException, Depends, status
   from fastapi.security import OAuth2PasswordRequestForm
   from pydantic import BaseModel
   from datetime import timedelta
   from app.services.auth import auth_service
   import structlog

   logger = structlog.get_logger()

   router = APIRouter(prefix="/auth", tags=["authentication"])

   class Token(BaseModel):
       access_token: str
       token_type: str
       expires_in: int
       user_info: dict

   @router.post("/login", response_model=Token)
   async def login(form_data: OAuth2PasswordRequestForm = Depends()):
       """Authenticate user and return access token"""
       user = auth_service.authenticate_family_user(
           form_data.username,
           form_data.password
       )

       if not user:
           logger.warning("Failed login attempt", username=form_data.username)
           raise HTTPException(
               status_code=status.HTTP_401_UNAUTHORIZED,
               detail="Incorrect username or password",
               headers={"WWW-Authenticate": "Bearer"},
           )

       access_token_expires = timedelta(minutes=auth_service.access_token_expire_minutes)
       access_token = auth_service.create_access_token(
           data={"sub": user["username"], "role": user["role"]},
           expires_delta=access_token_expires
       )

       logger.info("Successful login", username=user["username"], role=user["role"])

       return {
           "access_token": access_token,
           "token_type": "bearer",
           "expires_in": auth_service.access_token_expire_minutes * 60,
           "user_info": {
               "username": user["username"],
               "display_name": user["display_name"],
               "role": user["role"]
           }
       }

   @router.get("/me")
   async def get_current_user_info(current_user: dict = Depends(get_current_user)):
       """Get current user information"""
       return {
           "username": current_user.get("sub"),
           "role": current_user.get("role"),
           "authenticated": True
       }
   ```

3. **Add Rate Limiting**
   ```python
   # app/middleware/rate_limiting.py
   import time
   from collections import defaultdict
   from fastapi import Request, HTTPException, status
   from fastapi.responses import JSONResponse
   import structlog

   logger = structlog.get_logger()

   class RateLimiter:
       def __init__(self, requests_per_minute: int = 60):
           self.requests_per_minute = requests_per_minute
           self.requests = defaultdict(list)

       def is_allowed(self, client_ip: str) -> bool:
           """Check if request is allowed based on rate limit"""
           now = time.time()
           minute_ago = now - 60

           # Clean old requests
           self.requests[client_ip] = [
               req_time for req_time in self.requests[client_ip]
               if req_time > minute_ago
           ]

           # Check current request count
           if len(self.requests[client_ip]) >= self.requests_per_minute:
               logger.warning("Rate limit exceeded",
                            client_ip=client_ip,
                            requests=len(self.requests[client_ip]))
               return False

           # Add current request
           self.requests[client_ip].append(now)
           return True

   # Global rate limiter
   rate_limiter = RateLimiter()

   async def rate_limit_middleware(request: Request, call_next):
       """Rate limiting middleware"""
       client_ip = request.client.host

       if not rate_limiter.is_allowed(client_ip):
           return JSONResponse(
               status_code=status.HTTP_429_TOO_MANY_REQUESTS,
               content={
                   "status": "error",
                   "code": "E_RATE_LIMIT",
                   "message": "Rate limit exceeded. Please try again later."
               }
           )

       response = await call_next(request)
       return response
   ```

4. **Integrate Authentication into Main App**
   ```python
   # Update app/main.py
   from app.routers import auth
   from app.middleware.rate_limiting import rate_limit_middleware

   # Add rate limiting middleware
   app.middleware("http")(rate_limit_middleware)

   # Include auth router
   app.include_router(auth.router)

   # Protected endpoint example
   from app.services.auth import get_current_user

   @app.get("/protected")
   async def protected_endpoint(current_user: dict = Depends(get_current_user)):
       """Example protected endpoint"""
       return {
           "message": "This is a protected endpoint",
           "user": current_user.get("sub"),
           "role": current_user.get("role")
       }
   ```

#### ✅ Validation Checklist
- [ ] JWT token creation and validation working
- [ ] Family user authentication functional
- [ ] Protected endpoints require valid tokens
- [ ] Rate limiting prevents abuse
- [ ] Token expiration handled properly
- [ ] Admin role restrictions enforced
- [ ] Authentication errors handled gracefully
- [ ] Security headers properly set

#### 🚀 Agent Assignments
- **Security Engineer**: JWT implementation, rate limiting, security middleware
- **AI Engineer**: Authentication flow, token management, API integration

#### 🔍 Review & Sign-off
- Authentication flow works end-to-end
- Token validation properly protects endpoints
- Rate limiting prevents abuse
- Family-appropriate security measures in place
- All security requirements from STANDARDS.md met

---

## Phase 1 Summary

At the end of Phase 1, you should have:

1. ✅ **Working FastAPI Application**
   - Async-first architecture
   - Proper error handling and logging
   - Health check endpoints

2. ✅ **Database Foundation**
   - SQLAlchemy async models
   - Pydantic validation schemas
   - Migration system setup

3. ✅ **Git Repository Operations**
   - Safe, atomic Git operations
   - Path traversal protection
   - File locking for concurrency

4. ✅ **Authentication System**
   - JWT-based authentication
   - Family-appropriate user management
   - Rate limiting and security middleware

5. ✅ **Development Environment**
   - Docker development setup
   - Proper tooling configuration
   - Testing framework ready

### Phase 1 Final Validation

Before proceeding to Phase 2, confirm:

- [ ] All services start without errors
- [ ] Health checks return positive status
- [ ] Authentication flow works completely
- [ ] Git operations create and modify entries
- [ ] Database operations function correctly
- [ ] All tests pass
- [ ] Code follows STANDARDS.md completely
- [ ] No security vulnerabilities identified

---

## Continuation

This document will continue with Phases 2-6, each following the same structured approach:

- **Phase 2**: MCP Protocol Implementation
- **Phase 3**: Slack Integration
- **Phase 4**: Frontend Interface
- **Phase 5**: Integration & Testing
- **Phase 6**: Deployment & Polish

Each phase will include detailed steps with agent assignments, validation checklists, and sign-off requirements to ensure methodical development and proper functionality validation.

The process ensures that errors are resolved immediately, functionality is confirmed at each step, and all development follows the standards established in STANDARDS.md.