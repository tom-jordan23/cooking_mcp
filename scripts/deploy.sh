#!/bin/bash
#
# Deployment automation script for MCP Cooking Lab Notebook
# Supports multiple deployment targets and environments
#

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/tmp/cooking-mcp-deploy.log"

# Default values
DEPLOYMENT_TYPE="family"
ENVIRONMENT="production"
SKIP_BACKUP="false"
DRY_RUN="false"
VERBOSE="false"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"

    case "$level" in
        "ERROR") echo -e "${RED}ERROR: $message${NC}" >&2 ;;
        "WARN")  echo -e "${YELLOW}WARN: $message${NC}" ;;
        "INFO")  echo -e "${BLUE}INFO: $message${NC}" ;;
        "SUCCESS") echo -e "${GREEN}SUCCESS: $message${NC}" ;;
    esac
}

# Error handling
error_exit() {
    log "ERROR" "$1"
    exit 1
}

# Help function
show_help() {
    cat << EOF
MCP Cooking Lab Notebook Deployment Script

Usage: $0 [OPTIONS]

Options:
    -t, --type TYPE         Deployment type: family, production, k8s (default: family)
    -e, --env ENV          Environment: development, staging, production (default: production)
    -b, --skip-backup      Skip backup before deployment
    -d, --dry-run          Show what would be done without executing
    -v, --verbose          Enable verbose output
    -h, --help             Show this help message

Deployment Types:
    family      - Family-scale deployment with Docker Compose
    production  - Production deployment with monitoring
    k8s         - Kubernetes deployment
    railway     - Railway platform deployment

Examples:
    $0                                    # Family-scale production deployment
    $0 -t production -e staging           # Production deployment to staging
    $0 -t k8s -e production               # Kubernetes production deployment
    $0 -d -t production                   # Dry run of production deployment

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -t|--type)
                DEPLOYMENT_TYPE="$2"
                shift 2
                ;;
            -e|--env)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -b|--skip-backup)
                SKIP_BACKUP="true"
                shift
                ;;
            -d|--dry-run)
                DRY_RUN="true"
                shift
                ;;
            -v|--verbose)
                VERBOSE="true"
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                error_exit "Unknown option: $1"
                ;;
        esac
    done
}

# Validate deployment type
validate_deployment_type() {
    case "$DEPLOYMENT_TYPE" in
        family|production|k8s|railway)
            log "INFO" "Deployment type: $DEPLOYMENT_TYPE"
            ;;
        *)
            error_exit "Invalid deployment type: $DEPLOYMENT_TYPE"
            ;;
    esac
}

# Check prerequisites
check_prerequisites() {
    log "INFO" "Checking prerequisites for $DEPLOYMENT_TYPE deployment"

    # Common prerequisites
    command -v docker >/dev/null 2>&1 || error_exit "Docker is not installed"
    command -v git >/dev/null 2>&1 || error_exit "Git is not installed"

    case "$DEPLOYMENT_TYPE" in
        family|production)
            command -v docker-compose >/dev/null 2>&1 || error_exit "Docker Compose is not installed"
            ;;
        k8s)
            command -v kubectl >/dev/null 2>&1 || error_exit "kubectl is not installed"
            kubectl cluster-info >/dev/null 2>&1 || error_exit "Cannot connect to Kubernetes cluster"
            ;;
        railway)
            command -v railway >/dev/null 2>&1 || error_exit "Railway CLI is not installed"
            ;;
    esac

    log "SUCCESS" "Prerequisites check passed"
}

# Load environment configuration
load_environment() {
    local env_file="$PROJECT_ROOT/.env.$ENVIRONMENT"

    if [[ -f "$env_file" ]]; then
        log "INFO" "Loading environment from $env_file"
        set -a
        source "$env_file"
        set +a
    else
        log "WARN" "Environment file $env_file not found"
    fi
}

# Generate secrets if not present
generate_secrets() {
    log "INFO" "Checking and generating secrets"

    if [[ -z "${SECRET_KEY:-}" ]]; then
        export SECRET_KEY=$(openssl rand -hex 32)
        log "INFO" "Generated SECRET_KEY"
    fi

    if [[ -z "${JWT_SECRET_KEY:-}" ]]; then
        export JWT_SECRET_KEY=$(openssl rand -hex 32)
        log "INFO" "Generated JWT_SECRET_KEY"
    fi

    if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
        export POSTGRES_PASSWORD=$(openssl rand -hex 16)
        log "INFO" "Generated POSTGRES_PASSWORD"
    fi

    if [[ -z "${REDIS_PASSWORD:-}" ]]; then
        export REDIS_PASSWORD=$(openssl rand -hex 16)
        log "INFO" "Generated REDIS_PASSWORD"
    fi
}

# Backup existing deployment
backup_deployment() {
    if [[ "$SKIP_BACKUP" == "true" ]]; then
        log "INFO" "Skipping backup as requested"
        return
    fi

    log "INFO" "Creating backup before deployment"

    case "$DEPLOYMENT_TYPE" in
        family|production)
            if docker-compose ps | grep -q "cooking-mcp"; then
                docker-compose -f "docker-compose.${DEPLOYMENT_TYPE}.yml" exec -T db \
                    pg_dump -U "${POSTGRES_USER:-cooking_user}" "${POSTGRES_DB:-cooking_mcp}" \
                    | gzip > "backup_pre_deploy_$(date +%Y%m%d_%H%M%S).sql.gz"
                log "SUCCESS" "Database backup created"
            fi
            ;;
        k8s)
            if kubectl get namespace cooking-mcp >/dev/null 2>&1; then
                kubectl exec -n cooking-mcp deployment/postgres -- \
                    pg_dump -U "${POSTGRES_USER:-cooking_user}" "${POSTGRES_DB:-cooking_mcp}" \
                    | gzip > "k8s_backup_pre_deploy_$(date +%Y%m%d_%H%M%S).sql.gz"
                log "SUCCESS" "Kubernetes database backup created"
            fi
            ;;
    esac
}

# Deploy family-scale configuration
deploy_family() {
    log "INFO" "Deploying family-scale configuration"

    local compose_file="docker-compose.family.yml"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "INFO" "DRY RUN: Would execute: docker-compose -f $compose_file up -d"
        return
    fi

    # Pull latest images
    docker-compose -f "$compose_file" pull

    # Build and deploy
    docker-compose -f "$compose_file" up -d --build

    # Wait for services to be ready
    log "INFO" "Waiting for services to be ready..."
    sleep 30

    # Run database migrations
    docker-compose -f "$compose_file" exec app alembic upgrade head

    # Health check
    if curl -f http://localhost:${APP_PORT:-8080}/health >/dev/null 2>&1; then
        log "SUCCESS" "Family-scale deployment completed successfully"
    else
        error_exit "Health check failed after deployment"
    fi
}

# Deploy production configuration
deploy_production() {
    log "INFO" "Deploying production configuration"

    local compose_file="docker-compose.prod.yml"
    local monitoring_profile=""

    if [[ "${ENABLE_MONITORING:-true}" == "true" ]]; then
        monitoring_profile="--profile monitoring"
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log "INFO" "DRY RUN: Would execute: docker-compose -f $compose_file $monitoring_profile up -d"
        return
    fi

    # Pull latest images
    docker-compose -f "$compose_file" pull

    # Deploy with monitoring if enabled
    docker-compose -f "$compose_file" $monitoring_profile up -d --build

    # Wait for services
    log "INFO" "Waiting for services to be ready..."
    sleep 60

    # Run database migrations
    docker-compose -f "$compose_file" exec app alembic upgrade head

    # Health checks
    local health_url="https://${DOMAIN:-localhost}/health"
    if curl -f "$health_url" >/dev/null 2>&1; then
        log "SUCCESS" "Production deployment completed successfully"
    else
        error_exit "Health check failed at $health_url"
    fi
}

# Deploy to Kubernetes
deploy_k8s() {
    log "INFO" "Deploying to Kubernetes"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "INFO" "DRY RUN: Would apply Kubernetes manifests"
        kubectl apply --dry-run=client -f k8s/base/
        return
    fi

    # Apply configurations in order
    kubectl apply -f k8s/base/namespace.yaml
    kubectl apply -f k8s/base/configmap.yaml
    kubectl apply -f k8s/base/secret.yaml
    kubectl apply -f k8s/base/postgres.yaml
    kubectl apply -f k8s/base/redis.yaml

    # Wait for database to be ready
    log "INFO" "Waiting for database to be ready..."
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=postgres -n cooking-mcp --timeout=300s

    # Deploy application
    kubectl apply -f k8s/base/app.yaml
    kubectl apply -f k8s/base/ingress.yaml

    # Wait for deployment
    kubectl rollout status deployment/cooking-mcp-app -n cooking-mcp --timeout=300s

    # Run database migrations
    kubectl exec -n cooking-mcp deployment/cooking-mcp-app -- alembic upgrade head

    log "SUCCESS" "Kubernetes deployment completed successfully"
}

# Deploy to Railway
deploy_railway() {
    log "INFO" "Deploying to Railway"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "INFO" "DRY RUN: Would execute: railway up"
        return
    fi

    # Login to Railway
    railway login

    # Deploy application
    railway up --service app

    log "SUCCESS" "Railway deployment completed successfully"
}

# Post-deployment tasks
post_deployment() {
    log "INFO" "Running post-deployment tasks"

    case "$DEPLOYMENT_TYPE" in
        family|production)
            # Show service status
            docker-compose -f "docker-compose.${DEPLOYMENT_TYPE}.yml" ps

            # Show logs
            if [[ "$VERBOSE" == "true" ]]; then
                docker-compose -f "docker-compose.${DEPLOYMENT_TYPE}.yml" logs --tail=50
            fi
            ;;
        k8s)
            # Show pod status
            kubectl get pods -n cooking-mcp

            # Show service status
            kubectl get svc -n cooking-mcp

            # Show ingress
            kubectl get ingress -n cooking-mcp
            ;;
        railway)
            # Show Railway status
            railway status
            ;;
    esac

    log "SUCCESS" "Post-deployment tasks completed"
}

# Main deployment function
main() {
    log "INFO" "Starting MCP Cooking Lab Notebook deployment"
    log "INFO" "Deployment type: $DEPLOYMENT_TYPE, Environment: $ENVIRONMENT"

    # Change to project directory
    cd "$PROJECT_ROOT"

    # Validate and prepare
    validate_deployment_type
    check_prerequisites
    load_environment
    generate_secrets

    # Backup existing deployment
    backup_deployment

    # Deploy based on type
    case "$DEPLOYMENT_TYPE" in
        family)
            deploy_family
            ;;
        production)
            deploy_production
            ;;
        k8s)
            deploy_k8s
            ;;
        railway)
            deploy_railway
            ;;
    esac

    # Post-deployment tasks
    post_deployment

    log "SUCCESS" "Deployment completed successfully!"
    log "INFO" "Deployment log available at: $LOG_FILE"
}

# Parse arguments and run main function
parse_args "$@"
main