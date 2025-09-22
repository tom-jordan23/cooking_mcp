#!/bin/bash
#
# Family-scale backup script for MCP Cooking Lab Notebook
# Simplified backup for small deployments with local storage
#

set -euo pipefail

# Configuration
BACKUP_DIR="/backups"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-cooking_mcp}"
POSTGRES_USER="${POSTGRES_USER:-cooking_user}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Error handling
error_exit() {
    log "ERROR: $1"
    exit 1
}

# Create backup directory
setup_backup_dir() {
    log "Setting up backup directory"
    mkdir -p "$BACKUP_DIR/postgres"
    mkdir -p "$BACKUP_DIR/git"
}

# Simple PostgreSQL backup
backup_postgres() {
    local backup_file="$BACKUP_DIR/postgres/backup_${TIMESTAMP}.sql.gz"

    log "Starting PostgreSQL backup"

    # Create simple compressed SQL dump
    PGPASSWORD="$PGPASSWORD" pg_dump \
        --host="$POSTGRES_HOST" \
        --port="$POSTGRES_PORT" \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --no-password \
        --file=- | gzip > "$backup_file"

    if [[ -f "$backup_file" ]]; then
        local size=$(du -h "$backup_file" | cut -f1)
        log "PostgreSQL backup completed. Size: $size"
    else
        error_exit "PostgreSQL backup failed"
    fi
}

# Simple Git repository backup
backup_git() {
    local backup_file="$BACKUP_DIR/git/notebook_${TIMESTAMP}.tar.gz"

    log "Starting Git repository backup"

    if [[ -d "/app/notebook" ]]; then
        tar -czf "$backup_file" -C /app notebook/
        local size=$(du -h "$backup_file" | cut -f1)
        log "Git repository backup completed. Size: $size"
    else
        log "Warning: /app/notebook directory not found"
    fi
}

# Clean up old backups
cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days"

    find "$BACKUP_DIR/postgres" -name "backup_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
    find "$BACKUP_DIR/git" -name "notebook_*.tar.gz" -type f -mtime +$RETENTION_DAYS -delete 2>/dev/null || true

    log "Cleanup completed"
}

# Main execution
main() {
    log "Starting family-scale backup"

    [[ -n "$PGPASSWORD" ]] || error_exit "PGPASSWORD environment variable is required"

    setup_backup_dir
    backup_postgres
    backup_git
    cleanup_old_backups

    log "Backup completed successfully"
}

# Run main function
main "$@"