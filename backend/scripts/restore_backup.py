#!/usr/bin/env python3
"""Restore database from JSON backup file.

Usage:
    python scripts/restore_backup.py path/to/askesis_backup.json
"""

import json
import sys
from datetime import datetime, date
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.database import SessionLocal


def parse_value(value, col_name: str):
    """Convert JSON values back to Python types."""
    if value is None:
        return None

    # Handle date/datetime strings
    if isinstance(value, str):
        # Try datetime first
        if "T" in value and len(value) >= 19:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        # Try date
        if len(value) == 10 and value.count("-") == 2:
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass

    return value


def restore_backup(backup_path: str, clear_existing: bool = False):
    """Restore database from JSON backup."""
    with open(backup_path, "r") as f:
        backup_data = json.load(f)

    print(f"Backup version: {backup_data.get('version')}")
    print(f"Created at: {backup_data.get('created_at')}")
    print(f"Tables: {list(backup_data['tables'].keys())}")

    db = SessionLocal()

    try:
        for table_name, table_data in backup_data["tables"].items():
            columns = table_data["columns"]
            rows = table_data["rows"]

            if not rows:
                print(f"Skipping {table_name} (empty)")
                continue

            if clear_existing:
                db.execute(text(f'DELETE FROM "{table_name}"'))
                print(f"Cleared {table_name}")

            # Build INSERT statement
            col_list = ", ".join(f'"{c}"' for c in columns)
            placeholders = ", ".join(f":{c}" for c in columns)
            insert_sql = (
                f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'
            )

            inserted = 0
            skipped = 0

            for row in rows:
                # Parse values
                parsed_row = {col: parse_value(row.get(col), col) for col in columns}

                try:
                    db.execute(text(insert_sql), parsed_row)
                    inserted += 1
                except Exception as e:
                    if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                        skipped += 1
                        db.rollback()
                    else:
                        print(f"Error inserting into {table_name}: {e}")
                        db.rollback()
                        skipped += 1

            db.commit()
            print(f"Restored {table_name}: {inserted} inserted, {skipped} skipped")

        print("\nRestore complete!")

    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/restore_backup.py <backup_file.json> [--clear]")
        sys.exit(1)

    backup_file = sys.argv[1]
    clear = "--clear" in sys.argv

    if clear:
        confirm = input(
            "This will DELETE existing data before restore. Continue? (yes/no): "
        )
        if confirm.lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    restore_backup(backup_file, clear_existing=clear)
