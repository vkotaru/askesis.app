from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import get_settings

settings = get_settings()

# Configure engine based on database type
is_sqlite = settings.database_url.startswith("sqlite")

if is_sqlite:
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},  # SQLite specific
    )

    # Enable WAL mode for better concurrent access (SQLite only)
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        # Let SQLAlchemy own the transaction, not pysqlite. The driver's legacy
        # mode delays BEGIN until the first INSERT/UPDATE, so a SAVEPOINT issued
        # before any write (`Session.begin_nested()`, which mfp_ingest uses per
        # meal) opens its own implicit transaction and RELEASE then COMMITS it
        # -- a dry run's rollback silently kept the rows. This is the recipe
        # from SQLAlchemy's SQLite dialect docs ("Serializable isolation /
        # Savepoints / Transactional DDL"); Postgres needs none of it.
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def begin_sqlite_transaction(conn):
        conn.exec_driver_sql("BEGIN")
else:
    # PostgreSQL with connection pool settings
    engine = create_engine(
        settings.database_url,
        pool_recycle=3600,  # Recycle connections after 1 hour
        pool_pre_ping=True,  # Verify connections before use
        pool_size=5,  # Base pool size
        max_overflow=10,  # Allow up to 15 total connections
    )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
