from sqlalchemy.orm import Session, sessionmaker

SessionLocal = sessionmaker()


def get_session() -> Session:
    return SessionLocal()
