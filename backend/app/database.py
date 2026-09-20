from contextlib import contextmanager
from threading import Lock
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings

class Base(DeclarativeBase):
    pass

settings = get_settings()
# Local development keeps the original SQLite workflow. Vercel uses a hosted
# PostgreSQL-compatible URL and never treats the deployment filesystem as the
# source of truth.
settings.initialize_directories()
if settings.serverless and not settings.database_url:
    raise RuntimeError("DATABASE_URL is required when QHEALTH_SERVERLESS=true; refusing ephemeral SQLite persistence.")
if settings.serverless and settings.storage_backend != "s3":
    raise RuntimeError("QHEALTH_STORAGE_BACKEND=s3 is required when QHEALTH_SERVERLESS=true.")
if settings.database_url:
    database_url = settings.database_url
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    if database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=1,
        max_overflow=2,
    )
else:
    engine = create_engine(
        f"sqlite:///{settings.root / 'data' / 'qhealth.sqlite3'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
_init_lock = Lock()
_initialized = False

@contextmanager
def session_scope():
    ensure_initialized()
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

def init_db():
    global _initialized
    from .storage import entities  # Register all tables.
    with _init_lock:
        if not _initialized:
            Base.metadata.create_all(engine)
            _initialized = True

def ensure_initialized():
    """Create the small registry schema lazily on the first DB-backed request.

    Keeping this out of FastAPI lifespan means /api/health can answer during a
    cold start without requiring a database round trip.
    """
    if not _initialized:
        init_db()
