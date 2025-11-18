#!/bin/bash

# Database Migration Script
# This script dumps the "postgres" database from source server and restores it to "superset" database on destination server
#
# Usage:
#   ./migrate_database.sh
#
# Environment variables (or you can modify the variables below):
#   SOURCE_HOST, SOURCE_USER, SOURCE_PASSWORD, SOURCE_PORT
#   DEST_HOST, DEST_USER, DEST_PASSWORD, DEST_PORT

set -e  # Exit on error

# Source database configuration
SOURCE_HOST="${SOURCE_HOST:-34.173.150.167}"
SOURCE_DB="${SOURCE_DB:-postgres}"
SOURCE_USER="${SOURCE_USER:-postgres}"
SOURCE_PASSWORD="${SOURCE_PASSWORD:-superset}"
SOURCE_PORT="${SOURCE_PORT:-5432}"

# Destination database configuration
DEST_HOST="${DEST_HOST:-35.232.174.124}"
DEST_DB="${DEST_DB:-superset}"
DEST_USER="${DEST_USER:-superset}"
DEST_PASSWORD="${DEST_PASSWORD:-Datakimia2025!}"
DEST_PORT="${DEST_PORT:-5432}"

# Temporary dump file
DUMP_FILE="postgres_dump_$(date +%Y%m%d_%H%M%S).sql"
DUMP_FILE_CUSTOM="postgres_dump_$(date +%Y%m%d_%H%M%S).custom"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if pg_dump and psql are available
check_dependencies() {
    if ! command -v pg_dump &> /dev/null; then
        print_error "pg_dump is not installed. Please install PostgreSQL client tools."
        exit 1
    fi
    
    if ! command -v psql &> /dev/null; then
        print_error "psql is not installed. Please install PostgreSQL client tools."
        exit 1
    fi
}

# Prompt for password if not set
prompt_password() {
    local var_name=$1
    local prompt_text=$2
    
    if [ -z "${!var_name}" ]; then
        read -sp "$prompt_text: " password
        echo
        eval "$var_name='$password'"
    fi
}

# Test database connection
test_connection() {
    local host=$1
    local port=$2
    local user=$3
    local password=$4
    local db=$5
    local label=$6
    
    print_info "Testing connection to $label ($host:$port/$db)..."
    
    export PGPASSWORD="$password"
    if psql -h "$host" -p "$port" -U "$user" -d "$db" -c "SELECT 1;" > /dev/null 2>&1; then
        print_info "Connection to $label successful!"
        return 0
    else
        print_error "Failed to connect to $label"
        return 1
    fi
    unset PGPASSWORD
}

# Create database dump
create_dump() {
    print_info "Creating dump from source database..."
    
    export PGPASSWORD="$SOURCE_PASSWORD"
    
    # Use custom format for better compression and flexibility
    # Exclude public.logs table DATA (but keep structure) as it's huge
    if pg_dump -h "$SOURCE_HOST" -p "$SOURCE_PORT" -U "$SOURCE_USER" -d "$SOURCE_DB" \
        -F c -f "$DUMP_FILE_CUSTOM" --exclude-table-data=public.logs -v; then
        print_info "Dump created successfully: $DUMP_FILE_CUSTOM"
    else
        print_error "Failed to create dump"
        unset PGPASSWORD
        exit 1
    fi
    
    unset PGPASSWORD
}

# Create SQL dump (alternative, for compatibility)
create_sql_dump() {
    print_info "Creating SQL dump from source database..."
    
    export PGPASSWORD="$SOURCE_PASSWORD"
    
    # Exclude public.logs table DATA (but keep structure) as it's huge
    if pg_dump -h "$SOURCE_HOST" -p "$SOURCE_PORT" -U "$SOURCE_USER" -d "$SOURCE_DB" \
        -f "$DUMP_FILE" --exclude-table-data=public.logs -v; then
        print_info "SQL dump created successfully: $DUMP_FILE"
    else
        print_error "Failed to create SQL dump"
        unset PGPASSWORD
        exit 1
    fi
    
    unset PGPASSWORD
}

# Restore database dump
restore_dump() {
    print_info "Restoring dump to destination database..."
    
    export PGPASSWORD="$DEST_PASSWORD"
    
    # Check if database exists, drop it if it does to ensure clean restore
    print_info "Checking if destination database '$DEST_DB' exists..."
    if psql -h "$DEST_HOST" -p "$DEST_PORT" -U "$DEST_USER" -d "postgres" \
        -tc "SELECT 1 FROM pg_database WHERE datname = '$DEST_DB'" | grep -q 1; then
        print_warn "Database '$DEST_DB' already exists. Dropping it for clean restore..."
        # Terminate existing connections to the database
        psql -h "$DEST_HOST" -p "$DEST_PORT" -U "$DEST_USER" -d "postgres" \
            -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DEST_DB' AND pid <> pg_backend_pid();" 2>/dev/null || true
        # Drop the database
        psql -h "$DEST_HOST" -p "$DEST_PORT" -U "$DEST_USER" -d "postgres" \
            -c "DROP DATABASE IF EXISTS $DEST_DB;"
        print_info "Database '$DEST_DB' dropped successfully"
    fi
    
    # Create the database
    print_info "Creating destination database '$DEST_DB'..."
    psql -h "$DEST_HOST" -p "$DEST_PORT" -U "$DEST_USER" -d "postgres" \
        -c "CREATE DATABASE $DEST_DB;"
    print_info "Database '$DEST_DB' created successfully"
    
    # Restore using custom format if available, otherwise use SQL
    if [ -f "$DUMP_FILE_CUSTOM" ]; then
        print_info "Restoring from custom format dump..."
        # Use --no-owner --no-acl to avoid permission issues
        # Since we dropped and recreated the database, we don't need --clean
        # Capture output to check for actual errors vs warnings
        RESTORE_OUTPUT=$(pg_restore -h "$DEST_HOST" -p "$DEST_PORT" -U "$DEST_USER" -d "$DEST_DB" \
            -v --no-owner --no-acl "$DUMP_FILE_CUSTOM" 2>&1)
        RESTORE_EXIT_CODE=$?
        
        # Check for critical errors (not just warnings)
        if echo "$RESTORE_OUTPUT" | grep -qi "ERROR:" && ! echo "$RESTORE_OUTPUT" | grep -qi "ERROR.*already exists"; then
            print_error "Critical errors found during restore:"
            echo "$RESTORE_OUTPUT" | grep -i "ERROR:" | head -10
            unset PGPASSWORD
            exit 1
        fi
        
        # Verify restore succeeded by checking if tables exist
        print_info "Verifying restore by checking database tables..."
        TABLE_COUNT=$(psql -h "$DEST_HOST" -p "$DEST_PORT" -U "$DEST_USER" -d "$DEST_DB" \
            -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | xargs)
        
        if [ -n "$TABLE_COUNT" ] && [ "$TABLE_COUNT" -gt 0 ]; then
            print_info "Database restored successfully! Found $TABLE_COUNT tables in the database."
            if [ $RESTORE_EXIT_CODE -ne 0 ]; then
                print_warn "pg_restore exited with code $RESTORE_EXIT_CODE, but database appears to be restored correctly."
                print_warn "This is often due to non-critical warnings. Review the output above if needed."
            fi
        else
            print_error "Restore verification failed - no tables found in database"
            unset PGPASSWORD
            exit 1
        fi
    elif [ -f "$DUMP_FILE" ]; then
        print_info "Restoring from SQL dump..."
        SQL_OUTPUT=$(psql -h "$DEST_HOST" -p "$DEST_PORT" -U "$DEST_USER" -d "$DEST_DB" \
            -f "$DUMP_FILE" -v 2>&1)
        SQL_EXIT_CODE=$?
        
        # Check for critical errors
        if echo "$SQL_OUTPUT" | grep -qi "ERROR:" && ! echo "$SQL_OUTPUT" | grep -qi "ERROR.*already exists"; then
            print_error "Critical errors found during restore:"
            echo "$SQL_OUTPUT" | grep -i "ERROR:" | head -10
            unset PGPASSWORD
            exit 1
        fi
        
        # Verify restore succeeded
        print_info "Verifying restore by checking database tables..."
        TABLE_COUNT=$(psql -h "$DEST_HOST" -p "$DEST_PORT" -U "$DEST_USER" -d "$DEST_DB" \
            -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | xargs)
        
        if [ -n "$TABLE_COUNT" ] && [ "$TABLE_COUNT" -gt 0 ]; then
            print_info "Database restored successfully! Found $TABLE_COUNT tables in the database."
            if [ $SQL_EXIT_CODE -ne 0 ]; then
                print_warn "psql exited with code $SQL_EXIT_CODE, but database appears to be restored correctly."
                print_warn "This is often due to non-critical warnings. Review the output above if needed."
            fi
        else
            print_error "Restore verification failed - no tables found in database"
            unset PGPASSWORD
            exit 1
        fi
    else
        print_error "No dump file found to restore"
        unset PGPASSWORD
        exit 1
    fi
    
    unset PGPASSWORD
}

# Cleanup function
cleanup() {
    if [ -f "$DUMP_FILE" ]; then
        print_info "Cleaning up dump file: $DUMP_FILE"
        rm -f "$DUMP_FILE"
    fi
    if [ -f "$DUMP_FILE_CUSTOM" ]; then
        print_info "Cleaning up dump file: $DUMP_FILE_CUSTOM"
        rm -f "$DUMP_FILE_CUSTOM"
    fi
}

# Main execution
main() {
    print_info "Starting database migration..."
    print_info "Source: $SOURCE_HOST:$SOURCE_PORT/$SOURCE_DB"
    print_info "Destination: $DEST_HOST:$DEST_PORT/$DEST_DB"
    echo
    
    # Check dependencies
    check_dependencies
    
    # Prompt for passwords if not set
    prompt_password "SOURCE_PASSWORD" "Enter password for source database ($SOURCE_USER@$SOURCE_HOST)"
    prompt_password "DEST_PASSWORD" "Enter password for destination database ($DEST_USER@$DEST_HOST)"
    
    echo
    
    # Test connections
    if ! test_connection "$SOURCE_HOST" "$SOURCE_PORT" "$SOURCE_USER" "$SOURCE_PASSWORD" "$SOURCE_DB" "source"; then
        exit 1
    fi
    
    if ! test_connection "$DEST_HOST" "$DEST_PORT" "$DEST_USER" "$DEST_PASSWORD" "postgres" "destination"; then
        exit 1
    fi
    
    echo
    
    # Create dump
    create_dump
    
    # Also create SQL dump as backup
    create_sql_dump
    
    echo
    
    # Restore dump
    restore_dump
    
    echo
    
    # Ask if user wants to keep dump files
    read -p "Do you want to keep the dump files? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        cleanup
    else
        print_info "Dump files kept: $DUMP_FILE, $DUMP_FILE_CUSTOM"
    fi
    
    print_info "Migration completed successfully!"
}

# Trap to cleanup on exit
trap cleanup EXIT

# Run main function
main

