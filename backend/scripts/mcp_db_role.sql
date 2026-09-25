-- Least-privilege Postgres role for the MCP connector service.
--
-- WHY THIS EXISTS. The MCP container is the only Askesis process that faces the
-- public internet. The Docker network split stops it reaching the app over
-- HTTP, but the database is a deliberate bridge between them -- and with the
-- app's own role that bridge is READ-WRITE. A remote-code-execution bug in the
-- internet-facing container (a starlette / h11 / python-multipart parsing flaw)
-- would then allow:
--
--     UPDATE users SET password_hash = '<attacker bcrypt>';   -- account takeover
--     UPDATE users SET password_hash = NULL;                  -- re-arms the
--                                    -- unauthenticated /auth/set-initial-password
--
-- followed by a normal login to the real app. `bcrypt` is already in the image.
-- Without this role every other control guards a door beside an open window.
--
-- THE RULE: the MCP role may read the health data it serves, may write only its
-- own OAuth bookkeeping, and may NOT write to `users` under any circumstance.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- Run once, on the server, as the database owner:
--
--     docker compose exec -T db psql -U askesis -d askesis \
--       -v mcp_password="$(openssl rand -hex 24)" \
--       < backend/scripts/mcp_db_role.sql
--
-- Put that same password in .env as MCP_DATABASE_URL (see .env.example).
-- Re-running is safe: the role is created only if missing, and grants are
-- idempotent. Changing the password later is a plain ALTER ROLE.
-- ─────────────────────────────────────────────────────────────────────────────

\set ON_ERROR_STOP on

-- 1. The role. NOLOGIN would defeat the point; no CREATEDB/CREATEROLE/SUPERUSER.
--
-- Built with \gexec rather than a DO block: psql does NOT substitute :vars
-- inside dollar-quoted bodies, so the obvious DO $$ ... :mcp_password ... $$
-- fails with `syntax error at or near ":"`. format(%L) quotes the password
-- safely; :'mcp_password' passes it in as a literal.
SELECT format('CREATE ROLE askesis_mcp LOGIN PASSWORD %L', :'mcp_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'askesis_mcp')
\gexec

SELECT format('ALTER ROLE askesis_mcp LOGIN PASSWORD %L', :'mcp_password')
\gexec

GRANT CONNECT ON DATABASE askesis TO askesis_mcp;
GRANT USAGE   ON SCHEMA public    TO askesis_mcp;

-- 2. Read-only: the health data the tools serve.
--
-- `food_items` is here because meals load it through
-- selectinload(MealFoodItem.food_item) -- it is not imported by name anywhere in
-- mcp_server/, so it is the one easy to miss, and omitting it fails only at
-- runtime on a meal query.
GRANT SELECT ON
    users,
    user_settings,
    daily_logs,
    daily_nutrition,
    meals,
    meal_food_items,
    food_items,
    activities,
    body_measurements,
    training_plans,
    planned_workouts,
    -- Strength logging. `exercise_catalog` is the shared movement library and
    -- `exercise_sets` holds the per-set rows reached through `exercises`; both
    -- are needed by get_activity and get_exercise_history. Relationship targets
    -- count, not just tables named directly in a tool.
    exercise_catalog,
    -- `exercises` is the join between an activity and its sets. Every tool that
    -- reads a workout goes through it, and it was previously listed as
    -- deliberately withheld -- which quietly broke `get_activity` from the day
    -- this role was introduced. Relationship targets are not optional.
    exercises,
    exercise_sets
TO askesis_mcp;

-- NOTE: table-level SELECT on `users`, not column-level, and that is deliberate.
-- The SQLAlchemy ORM emits every mapped column for `db.query(User)`, so a
-- column-level grant would have to track models.py exactly and would break the
-- service at runtime the next time a column is added. The property that actually
-- matters -- no write path to password_hash -- is enforced below by the absence
-- of any INSERT/UPDATE/DELETE grant, which does not have that fragility.

-- 3. Read-write: the connector's own OAuth bookkeeping, and nothing else.
GRANT SELECT, INSERT, UPDATE, DELETE ON
    mcp_clients,
    mcp_auth_codes,
    mcp_grants
TO askesis_mcp;

-- Serial primary keys need the sequence too, or every INSERT fails.
GRANT USAGE, SELECT ON SEQUENCE
    mcp_clients_id_seq,
    mcp_auth_codes_id_seq,
    mcp_grants_id_seq
TO askesis_mcp;

-- 4. Deliberately NOT granted, listed so the omissions read as decisions:
--      report_tokens   -- unhashed share credentials
--      data_shares     -- cross-user grants; the MCP identity is the OAuth
--                         subject alone and must never widen through sharing
--      progress_photos -- image paths; the tools expose no photos
--      meal_templates, workout_templates, routine_exercises
--                      -- routines are a plan, not history; no tool reads them
--    No ALTER DEFAULT PRIVILEGES either: a table added by a future migration is
--    unreadable until someone grants it here, on purpose. Fail closed.

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Verify. Every line below must print the stated expectation.
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '== writable tables (expect exactly the three mcp_* tables) =='
SELECT table_name, string_agg(privilege_type, ',' ORDER BY privilege_type) AS privs
FROM information_schema.table_privileges
WHERE grantee = 'askesis_mcp' AND privilege_type <> 'SELECT'
GROUP BY table_name
ORDER BY table_name;

\echo ''
\echo '== can it write to users? (expect f -- this is the whole point) =='
SELECT has_table_privilege('askesis_mcp', 'users', 'UPDATE') AS can_update_users,
       has_table_privilege('askesis_mcp', 'users', 'INSERT') AS can_insert_users,
       has_table_privilege('askesis_mcp', 'users', 'DELETE') AS can_delete_users;

\echo ''
\echo '== can it read what it must? (expect all t) =='
SELECT has_table_privilege('askesis_mcp', 'users',            'SELECT') AS users,
       has_table_privilege('askesis_mcp', 'daily_logs',       'SELECT') AS daily_logs,
       has_table_privilege('askesis_mcp', 'food_items',       'SELECT') AS food_items,
       has_table_privilege('askesis_mcp', 'activities',       'SELECT') AS activities,
       has_table_privilege('askesis_mcp', 'exercise_catalog', 'SELECT') AS exercise_catalog,
       has_table_privilege('askesis_mcp', 'exercises',        'SELECT') AS exercises,
       has_table_privilege('askesis_mcp', 'exercise_sets',    'SELECT') AS exercise_sets;

\echo ''
\echo '== and it still cannot WRITE the training data (expect all f) =='
SELECT has_table_privilege('askesis_mcp', 'exercise_sets',    'UPDATE') AS write_sets,
       has_table_privilege('askesis_mcp', 'exercise_catalog', 'UPDATE') AS write_catalog,
       has_table_privilege('askesis_mcp', 'activities',       'UPDATE') AS write_activities;

\echo ''
\echo '== tables it must NOT see at all (expect all f) =='
SELECT has_table_privilege('askesis_mcp', 'report_tokens',   'SELECT') AS report_tokens,
       has_table_privilege('askesis_mcp', 'data_shares',     'SELECT') AS data_shares,
       has_table_privilege('askesis_mcp', 'progress_photos', 'SELECT') AS progress_photos;
