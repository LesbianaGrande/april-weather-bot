import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base
from config.settings import DB_PATH

def get_engine():
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    return create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

_engine = None
_SessionLocal = None

def init_db():
    global _engine, _SessionLocal
    _engine = get_engine()
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)

def get_session():
    return _SessionLocal()

@contextmanager
def get_db_session():
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
