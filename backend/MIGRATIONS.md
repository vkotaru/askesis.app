# Database Migrations

Askesis uses [Alembic](https://alembic.sqlalchemy.org/) for database schema migrations.

## Quick Start

```bash
# Apply all pending migrations
./db.sh migrate

# Check migration status
./db.sh status

# Create a new migration after modifying models
./db.sh new your_migration_name
```

## Deployment Workflow

When deploying a new version:

1. **Before starting the server**, run migrations:
   ```bash
   cd backend
   ./db.sh migrate
   ```

2. **Start the server** as usual:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

## Development Workflow

### Making Schema Changes

1. **Modify models** in `app/models.py`

2. **Generate a migration**:
   ```bash
   ./db.sh new add_user_avatar
   ```

3. **Review the generated migration** in `migrations/versions/`

4. **Apply the migration**:
   ```bash
   ./db.sh migrate
   ```

### Common Commands

| Command | Description |
|---------|-------------|
| `./db.sh migrate` | Apply all pending migrations |
| `./db.sh rollback` | Rollback the last migration |
| `./db.sh status` | Show current state and history |
| `./db.sh new <name>` | Create a new migration |

## Migration Files

Migrations are stored in `migrations/versions/` with timestamps:
```
migrations/
├── env.py           # Alembic environment config
├── script.py.mako   # Migration template
└── versions/        # Migration files
    └── 20260302_1651_c01286a36ee9_initial_schema.py
```

## Important Notes

### SQLite Limitations

SQLite has limited ALTER TABLE support. Alembic uses "batch mode" to work around this:
- Columns can be added
- Tables can be created/dropped
- For complex changes (renaming columns, changing types), Alembic recreates the table

### Production Database

For production deployments:

1. **Always backup** before running migrations
2. **Test migrations** on a copy of production data first
3. **Never run `./db.sh fresh`** in production (deletes all data)

### Existing Database Setup

If setting up Alembic on an existing database:
```bash
# Mark the database at the current schema version
./db.sh stamp head
```

## Troubleshooting

### Migration fails with "Table already exists"

If tables already exist from a previous `create_all`:
```bash
./db.sh stamp head
```

### Out of sync with migration history

Check current state:
```bash
./db.sh status
```

If needed, stamp to match actual database state:
```bash
./db.sh stamp <revision>
```

### Need to start fresh (development only)

```bash
./db.sh fresh  # WARNING: Deletes all data
```
