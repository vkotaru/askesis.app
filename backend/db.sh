#!/bin/bash
# Database migration helper script for Askesis
# Usage: ./db.sh <command> [args]

set -e

# Ensure we're in the backend directory
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

case "$1" in
    migrate)
        # Apply all pending migrations
        echo "Applying migrations..."
        alembic upgrade head
        echo "Done!"
        ;;

    rollback)
        # Rollback last migration
        echo "Rolling back last migration..."
        alembic downgrade -1
        echo "Done!"
        ;;

    rollback-all)
        # Rollback all migrations
        echo "Rolling back all migrations..."
        alembic downgrade base
        echo "Done!"
        ;;

    status)
        # Show current migration status
        echo "Current migration status:"
        alembic current
        echo ""
        echo "Migration history:"
        alembic history
        ;;

    new)
        # Create a new migration
        if [ -z "$2" ]; then
            echo "Usage: ./db.sh new <migration_name>"
            echo "Example: ./db.sh new add_user_avatar"
            exit 1
        fi
        echo "Creating new migration: $2"
        alembic revision --autogenerate -m "$2"
        echo "Done! Review the migration file before applying."
        ;;

    upgrade)
        # Upgrade to specific revision
        if [ -z "$2" ]; then
            echo "Usage: ./db.sh upgrade <revision>"
            echo "Example: ./db.sh upgrade abc123"
            exit 1
        fi
        echo "Upgrading to revision: $2"
        alembic upgrade "$2"
        echo "Done!"
        ;;

    downgrade)
        # Downgrade to specific revision
        if [ -z "$2" ]; then
            echo "Usage: ./db.sh downgrade <revision>"
            echo "Example: ./db.sh downgrade abc123"
            exit 1
        fi
        echo "Downgrading to revision: $2"
        alembic downgrade "$2"
        echo "Done!"
        ;;

    stamp)
        # Mark database at specific revision without running migrations
        if [ -z "$2" ]; then
            echo "Usage: ./db.sh stamp <revision>"
            echo "Example: ./db.sh stamp head"
            exit 1
        fi
        echo "Stamping database at revision: $2"
        alembic stamp "$2"
        echo "Done!"
        ;;

    fresh)
        # Drop all tables and re-apply all migrations
        echo "WARNING: This will delete all data!"
        read -p "Are you sure? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Rolling back all migrations..."
            alembic downgrade base
            echo "Applying all migrations..."
            alembic upgrade head
            echo "Done!"
        else
            echo "Cancelled."
        fi
        ;;

    *)
        echo "Askesis Database Migration Tool"
        echo ""
        echo "Usage: ./db.sh <command> [args]"
        echo ""
        echo "Commands:"
        echo "  migrate        Apply all pending migrations"
        echo "  rollback       Rollback the last migration"
        echo "  rollback-all   Rollback all migrations"
        echo "  status         Show current migration status and history"
        echo "  new <name>     Create a new auto-generated migration"
        echo "  upgrade <rev>  Upgrade to a specific revision"
        echo "  downgrade <rev> Downgrade to a specific revision"
        echo "  stamp <rev>    Mark database at revision without running migrations"
        echo "  fresh          Drop all tables and re-run all migrations (DESTRUCTIVE)"
        echo ""
        echo "Examples:"
        echo "  ./db.sh migrate                 # Apply pending migrations"
        echo "  ./db.sh new add_user_roles      # Create new migration"
        echo "  ./db.sh status                  # Check current state"
        exit 1
        ;;
esac
