# Production Deployment Checklist

## CRITICAL (Must fix before prod)

- [x] **Hardcoded secret key** - `backend/app/config.py`
  - FIXED: Validates at startup, exits if SECRET_KEY is placeholder in production

- [x] **No file upload size limits** - `photos.py`, `nutrition.py`, `import_router.py`
  - FIXED: Added max_image_size (50MB) and max_csv_size (10MB) to config

- [x] **SQLite in production** - `config.py`
  - FIXED: Warns at startup if using SQLite in production mode

- [x] **CSV content-type not validated** - `import_router.py`
  - FIXED: Added content_type validation for CSV files

- [x] **Temp files not cleaned up** - `nutrition.py`, `export.py`
  - FIXED: Added proper cleanup with try/finally and BackgroundTasks

- [ ] **No rate limiting** - Entire app
  - TODO: Add slowapi middleware (not critical for initial deploy with limited users)

## MEDIUM (Should fix soon)

- [x] **Debug logging with user data** - `import_router.py`
  - FIXED: Removed all debug logger.info calls

- [x] **Console.log in frontend** - `ImportModal.svelte`
  - FIXED: Removed console.log statements

- [x] **DB connection pool config** - `database.py`
  - FIXED: Added pool_recycle, pool_pre_ping, pool_size, max_overflow for PostgreSQL

- [ ] **No CSRF protection** - `auth.py`, `main.py`
  - TODO: Add CSRF middleware for state-changing operations

- [ ] **OAuth redirect not validated** - `auth.py`
  - TODO: Validate redirect_uri against whitelist

- [ ] **No user feedback on errors** - Frontend
  - TODO: Add toast notifications

- [ ] **No migration verification** - `railway.json`
  - TODO: Verify alembic revision at startup

## NICE-TO-HAVE (Post-launch)

- [ ] Automated tests
- [ ] API versioning
- [ ] Error tracking (Sentry)
- [ ] Email notifications
- [ ] Full-text search
- [ ] PDF export
- [ ] Data retention policy

## Quick Deploy Checklist

1. Generate new SECRET_KEY: `openssl rand -hex 32`
2. Set DATABASE_URL to PostgreSQL
3. Configure Google OAuth with production domain
4. Update CORS_ORIGINS to production domain
5. Set up persistent storage for photos
6. Enable Railway logging

## What Was Fixed

### config.py
- Added `max_image_size` and `max_csv_size` settings
- Added `validate_production()` method that checks for placeholder secret key
- Exits with error if SECRET_KEY not set in production

### database.py
- Added PostgreSQL connection pool settings: `pool_recycle`, `pool_pre_ping`, `pool_size`, `max_overflow`

### import_router.py
- Added file size validation
- Added CSV content-type validation
- Removed all debug logging

### photos.py
- Added file size validation for image uploads

### nutrition.py
- Added file size validation for image uploads
- Fixed temp file cleanup with proper error handling

### export.py
- Added BackgroundTasks to clean up temp files after response

### ImportModal.svelte
- Removed console.log statements
