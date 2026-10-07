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
-- THE RULE: the MCP role may read the health data it serves, may write its own
-- OAuth bookkeeping and the PLANNING tables (the exercise library, routines and
-- the target columns on user_settings), and may NOT write to `users` or to any
-- record of what actually happened -- activities, exercise_sets, daily_logs,
-- measurements -- under any circumstance.
--
-- The line is "what you intend" versus "what you did". An assistant may change
-- the plan; it may not rewrite the history. `users` stays unreachable either
-- way, which is the threat the paragraph above is about.
--
-- ONE DELIBERATE EXCEPTION (log_day_nutrition, app/intake_log.py): INSERT and
-- UPDATE, never DELETE, on `meals` and `daily_nutrition`, so a screenshot of
-- another food tracker can be logged from a chat. Itemised foods
-- (`meal_food_items`) stay read-only. The worst a compromised container can do
-- with this is overwrite calorie and macro numbers -- it still cannot touch an
-- account, delete a row, or reach any other history table.
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

-- 3. Read-write: the planning tables.
--
-- Table-level, not column-level, following the same reasoning as `users` above:
-- a column list would have to track models.py exactly and would break at
-- runtime the next time a column is added. For `user_settings` that means the
-- role can also write the presentation columns (theme, font) -- unwanted but
-- harmless, and the alternative is a grant that silently breaks on the next
-- migration.
--
-- `exercise_catalog` gets no DELETE: removing a movement is an `is_archived`
-- flag, because logged sessions reference the row. `routine_exercises` does
-- need DELETE, for the replace-all when a routine's movement list changes --
-- not for deleting routines, which no tool can do.
GRANT INSERT, UPDATE ON
    exercise_catalog,
    user_settings
TO askesis_mcp;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    workout_templates,
    routine_exercises
TO askesis_mcp;

GRANT USAGE, SELECT ON SEQUENCE
    exercise_catalog_id_seq,
    user_settings_id_seq,
    workout_templates_id_seq,
    routine_exercises_id_seq
TO askesis_mcp;

-- 3b. Insert/update, NO delete: one day's intake. See ONE DELIBERATE EXCEPTION
--     at the top. A meal's soft delete is a `deleted_at` UPDATE, which this
--     grant would technically allow; intake_log.py has no code path that sets
--     it, and no tool exposes one.
GRANT INSERT, UPDATE ON
    meals,
    daily_nutrition
TO askesis_mcp;

GRANT USAGE, SELECT ON SEQUENCE
    meals_id_seq,
    daily_nutrition_id_seq
TO askesis_mcp;

-- 4. Read-write: the connector's own OAuth bookkeeping.
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

-- 5. Deliberately NOT granted, listed so the omissions read as decisions:
--      report_tokens   -- unhashed share credentials
--      data_shares     -- cross-user grants; the MCP identity is the OAuth
--                         subject alone and must never widen through sharing
--      progress_photos -- image paths; the tools expose no photos
--      meal_templates  -- no tool reads or writes them
--    And SELECT-only, deliberately, on everything else that records what
--    happened: activities, exercises, exercise_sets, daily_logs,
--    meal_food_items, body_measurements, training_plans, planned_workouts.
--    No ALTER DEFAULT PRIVILEGES either: a table added by a future migration is
--    unreadable until someone grants it here, on purpose. Fail closed.

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Verify. The DO block ASSERTS; the SELECTs below it are for reading.
--
-- The assertions are the point. `\set ON_ERROR_STOP on` aborts on a SQL error,
-- not on a result of `f` -- so a block of bare `SELECT has_table_privilege(...)`
-- prints the wrong answer and still exits 0. An operator running this as
-- `psql < file` acts on the exit code, and it never came. RAISE EXCEPTION is
-- what turns "self-verifying" from a description into a fact.
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '== writable tables (expect: the three mcp_*, exercise_catalog, user_settings,'
\echo '   workout_templates, routine_exercises, and only INSERT,UPDATE on meals and'
\echo '   daily_nutrition -- and NOTHING else) =='
SELECT table_name, string_agg(privilege_type, ',' ORDER BY privilege_type) AS privs
FROM information_schema.table_privileges
WHERE grantee = 'askesis_mcp' AND privilege_type <> 'SELECT'
GROUP BY table_name
ORDER BY table_name;

DO $$
DECLARE
    -- Everything that records what actually happened. The role may read these
    -- and must never write them; this is the "plans, not history" line.
    history text[] := ARRAY[
        'activities', 'exercises', 'exercise_sets', 'daily_logs',
        'meal_food_items', 'body_measurements',
        'training_plans', 'planned_workouts'
    ];
    -- The one exception: insert/update, never delete.
    intake text[] := ARRAY['meals', 'daily_nutrition'];
    -- The planning tables the write tools need.
    planning text[] := ARRAY[
        'exercise_catalog', 'user_settings', 'workout_templates',
        'routine_exercises'
    ];
    t text;
    priv text;
BEGIN
    -- users: no write, ever. The reason this role exists.
    FOREACH priv IN ARRAY ARRAY['INSERT', 'UPDATE', 'DELETE'] LOOP
        IF has_table_privilege('askesis_mcp', 'users', priv) THEN
            RAISE EXCEPTION 'askesis_mcp can % users -- the one thing this role must never allow', priv;
        END IF;
    END LOOP;

    FOREACH t IN ARRAY history LOOP
        IF NOT has_table_privilege('askesis_mcp', t, 'SELECT') THEN
            RAISE EXCEPTION 'askesis_mcp cannot read %, which its tools serve', t;
        END IF;
        FOREACH priv IN ARRAY ARRAY['INSERT', 'UPDATE', 'DELETE'] LOOP
            IF has_table_privilege('askesis_mcp', t, priv) THEN
                RAISE EXCEPTION 'askesis_mcp can % % -- that is logged history, not a plan', priv, t;
            END IF;
        END LOOP;
    END LOOP;

    FOREACH t IN ARRAY intake LOOP
        FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE'] LOOP
            IF NOT has_table_privilege('askesis_mcp', t, priv) THEN
                RAISE EXCEPTION 'askesis_mcp cannot % %; log_day_nutrition will fail at runtime', priv, t;
            END IF;
        END LOOP;
        IF has_table_privilege('askesis_mcp', t, 'DELETE') THEN
            RAISE EXCEPTION 'askesis_mcp can DELETE from % -- intake is insert/update only', t;
        END IF;
    END LOOP;

    FOREACH t IN ARRAY planning LOOP
        IF NOT has_table_privilege('askesis_mcp', t, 'UPDATE') THEN
            RAISE EXCEPTION 'askesis_mcp cannot write %; the write tools will fail at runtime', t;
        END IF;
    END LOOP;

    -- Archiving is a flag, so the library is never deleted from.
    IF has_table_privilege('askesis_mcp', 'exercise_catalog', 'DELETE') THEN
        RAISE EXCEPTION 'askesis_mcp can DELETE from exercise_catalog; archiving is an is_archived flag';
    END IF;

    -- Never visible at all.
    FOREACH t IN ARRAY ARRAY['report_tokens', 'data_shares', 'progress_photos'] LOOP
        IF has_table_privilege('askesis_mcp', t, 'SELECT') THEN
            RAISE EXCEPTION 'askesis_mcp can read %, which no tool exposes', t;
        END IF;
    END LOOP;

    RAISE NOTICE 'grants verified: plans writable, intake insert/update only, other history read-only, users untouchable';
END $$;

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
\echo '== it CAN write the planning tables (expect all t) =='
SELECT has_table_privilege('askesis_mcp', 'exercise_catalog',  'UPDATE') AS catalog,
       has_table_privilege('askesis_mcp', 'workout_templates', 'INSERT') AS routines,
       has_table_privilege('askesis_mcp', 'routine_exercises', 'DELETE') AS routine_ex,
       has_table_privilege('askesis_mcp', 'user_settings',     'UPDATE') AS settings;

\echo ''
\echo '== it still cannot write what actually HAPPENED (expect all f) =='
\echo '   -- this is the line that separates changing a plan from rewriting history'
SELECT has_table_privilege('askesis_mcp', 'activities',        'UPDATE') AS activities,
       has_table_privilege('askesis_mcp', 'exercise_sets',     'UPDATE') AS sets,
       has_table_privilege('askesis_mcp', 'daily_logs',        'UPDATE') AS daily_logs,
       has_table_privilege('askesis_mcp', 'meals',             'DELETE') AS delete_meals,
       has_table_privilege('askesis_mcp', 'body_measurements', 'UPDATE') AS measurements;

\echo ''
\echo '== and it cannot DELETE from the library (archiving is a flag) (expect f) =='
SELECT has_table_privilege('askesis_mcp', 'exercise_catalog', 'DELETE') AS delete_catalog;

\echo ''
\echo '== tables it must NOT see at all (expect all f) =='
SELECT has_table_privilege('askesis_mcp', 'report_tokens',   'SELECT') AS report_tokens,
       has_table_privilege('askesis_mcp', 'data_shares',     'SELECT') AS data_shares,
       has_table_privilege('askesis_mcp', 'progress_photos', 'SELECT') AS progress_photos;
