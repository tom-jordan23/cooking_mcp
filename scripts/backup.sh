#!/bin/bash
#
# Production backup script for MCP Cooking Lab Notebook
# Handles PostgreSQL database and Git repository backups with retention
#

set -euo pipefail

# Configuration
BACKUP_DIR="/backups"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-cooking_mcp}"
POSTGRES_USER="${POSTGRES_USER:-cooking_user}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
S3_BUCKET="${BACKUP_S3_BUCKET:-}"
NOTIFICATION_WEBHOOK="${BACKUP_NOTIFICATION_WEBHOOK:-}"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >&2
}

# Error handling
error_exit() {
    log "ERROR: $1"
    send_notification "FAILED" "$1"
    exit 1
}

# Send notification webhook
send_notification() {
    local status="$1"
    local message="$2"

    if [[ -n "$NOTIFICATION_WEBHOOK" ]]; then
        curl -X POST "$NOTIFICATION_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"text\":\"Backup $status: $message\"}" \
            --silent --fail || true
    fi
}

# Create backup directory structure
setup_backup_dir() {
    log "Setting up backup directory structure"
    mkdir -p "$BACKUP_DIR/postgres"
    mkdir -p "$BACKUP_DIR/git"
    mkdir -p "$BACKUP_DIR/logs"
}

# Backup PostgreSQL database
backup_postgres() {
    local backup_file="$BACKUP_DIR/postgres/postgres_backup_${TIMESTAMP}.sql.gz"

    log "Starting PostgreSQL backup to $backup_file"

    # Create compressed database dump
    PGPASSWORD="$PGPASSWORD" pg_dump \
        --host="$POSTGRES_HOST" \
        --port="$POSTGRES_PORT" \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --verbose \
        --no-password \
        --format=custom \
        --compress=9 \
        --file="$backup_file.custom"

    # Also create a plain SQL backup for easier restoration
    PGPASSWORD="$PGPASSWORD" pg_dump \
        --host="$POSTGRES_HOST" \
        --port="$POSTGRES_PORT" \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --verbose \
        --no-password \
        --format=plain \
        --file=- | gzip > "$backup_file"

    # Verify backup integrity
    if [[ -f "$backup_file" ]] && [[ -f "$backup_file.custom" ]]; then
        local size=$(du -h "$backup_file" | cut -f1)
        log "PostgreSQL backup completed successfully. Size: $size"
        echo "$backup_file" > "$BACKUP_DIR/postgres/latest_backup.txt"
    else
        error_exit "PostgreSQL backup failed - files not created"
    fi
}

# Backup Git repository
backup_git() {
    local backup_file="$BACKUP_DIR/git/git_backup_${TIMESTAMP}.tar.gz"

    log "Starting Git repository backup to $backup_file"

    # Create tar.gz archive of the entire notebook directory
    if [[ -d "/app/notebook" ]]; then
        tar -czf "$backup_file" -C /app notebook/ || error_exit "Git backup failed"

        local size=$(du -h "$backup_file" | cut -f1)
        log "Git repository backup completed successfully. Size: $size"
        echo "$backup_file" > "$BACKUP_DIR/git/latest_backup.txt"
    else
        log "Warning: /app/notebook directory not found, skipping Git backup"
    fi
}

# Upload to S3 if configured
upload_to_s3() {
    if [[ -n "$S3_BUCKET" ]]; then
        log "Uploading backups to S3 bucket: $S3_BUCKET"

        # Upload PostgreSQL backups
        find "$BACKUP_DIR/postgres" -name "postgres_backup_${TIMESTAMP}*" -type f | while read -r file; do
            aws s3 cp "$file" "s3://$S3_BUCKET/postgres/$(basename "$file")" \
                --storage-class STANDARD_IA || error_exit "S3 upload failed for $file"
        done

        # Upload Git backups
        find "$BACKUP_DIR/git" -name "git_backup_${TIMESTAMP}*" -type f | while read -r file; do
            aws s3 cp "$file" "s3://$S3_BUCKET/git/$(basename "$file")" \
                --storage-class STANDARD_IA || error_exit "S3 upload failed for $file"
        done

        log "S3 upload completed successfully"
    fi
}

# Clean up old backups
cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days"

    # Clean local PostgreSQL backups
    find "$BACKUP_DIR/postgres" -name "postgres_backup_*.sql*" -type f -mtime +$RETENTION_DAYS -delete

    # Clean local Git backups
    find "$BACKUP_DIR/git" -name "git_backup_*.tar.gz" -type f -mtime +$RETENTION_DAYS -delete

    # Clean S3 backups if configured
    if [[ -n "$S3_BUCKET" ]]; then
        local cutoff_date=$(date -d "$RETENTION_DAYS days ago" +%Y-%m-%d)
        aws s3 ls "s3://$S3_BUCKET/postgres/" | while read -r line; do
            local file_date=$(echo "$line" | awk '{print $1}')
            local file_name=$(echo "$line" | awk '{print $4}')
            if [[ "$file_date" < "$cutoff_date" ]]; then
                aws s3 rm "s3://$S3_BUCKET/postgres/$file_name"
            fi
        done

        aws s3 ls "s3://$S3_BUCKET/git/" | while read -r line; do
            local file_date=$(echo "$line" | awk '{print $1}')
            local file_name=$(echo "$line" | awk '{print $4}')
            if [[ "$file_date" < "$cutoff_date" ]]; then
                aws s3 rm "s3://$S3_BUCKET/git/$file_name"
            fi
        done
    fi

    log "Cleanup completed"
}

# Health check for backup system
health_check() {
    log "Performing backup system health check"

    # Check PostgreSQL connectivity
    PGPASSWORD="$PGPASSWORD" pg_isready \
        --host="$POSTGRES_HOST" \
        --port="$POSTGRES_PORT" \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" || error_exit "PostgreSQL health check failed"

    # Check backup directory permissions
    [[ -w "$BACKUP_DIR" ]] || error_exit "Backup directory not writable"

    # Check S3 connectivity if configured
    if [[ -n "$S3_BUCKET" ]]; then
        aws s3 ls "s3://$S3_BUCKET/" > /dev/null || error_exit "S3 connectivity check failed"
    fi

    log "Health check passed"
}

# Generate backup report
generate_report() {
    local report_file="$BACKUP_DIR/logs/backup_report_${TIMESTAMP}.txt"

    {
        echo "MCP Cooking Lab Notebook Backup Report"
        echo "======================================"
        echo "Timestamp: $(date)"
        echo "Backup ID: $TIMESTAMP"
        echo ""

        echo "PostgreSQL Backup:"
        if [[ -f "$BACKUP_DIR/postgres/latest_backup.txt" ]]; then
            local latest_pg=$(cat "$BACKUP_DIR/postgres/latest_backup.txt")
            echo "  File: $(basename "$latest_pg")"
            echo "  Size: $(du -h "$latest_pg" | cut -f1)"
            echo "  Status: SUCCESS"
        else
            echo "  Status: FAILED"
        fi
        echo ""

        echo "Git Repository Backup:"
        if [[ -f "$BACKUP_DIR/git/latest_backup.txt" ]]; then
            local latest_git=$(cat "$BACKUP_DIR/git/latest_backup.txt")
            echo "  File: $(basename "$latest_git")"
            echo "  Size: $(du -h "$latest_git" | cut -f1)"
            echo "  Status: SUCCESS"
        else
            echo "  Status: FAILED or SKIPPED"
        fi
        echo ""

        echo "Storage:"
        echo "  Local: $BACKUP_DIR"
        if [[ -n "$S3_BUCKET" ]]; then
            echo "  S3: s3://$S3_BUCKET"
        fi
        echo ""

        echo "Retention: $RETENTION_DAYS days"
    } > "$report_file"

    log "Backup report generated: $report_file"
}

# Main execution
main() {
    log "Starting MCP Cooking Lab Notebook backup process"

    # Validate required environment variables
    [[ -n "$PGPASSWORD" ]] || error_exit "PGPASSWORD environment variable is required"

    # Setup
    setup_backup_dir
    health_check

    # Perform backups
    backup_postgres
    backup_git

    # Upload to cloud storage
    upload_to_s3

    # Cleanup old backups
    cleanup_old_backups

    # Generate report
    generate_report

    log "Backup process completed successfully"
    send_notification "SUCCESS" "Backup completed for $TIMESTAMP"
}

# Run main function
main "$@"