"""Database lifecycle and session helpers."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Order, PaymentAttempt, Product

SEED_PRODUCTS = (
    {"sku": "SKU-001", "name": "Mechanical Keyboard", "price_cents": 7999, "stock": 20},
    {"sku": "SKU-002", "name": "Wireless Mouse", "price_cents": 3999, "stock": 30},
    {"sku": "SKU-003", "name": "USB-C Dock", "price_cents": 12999, "stock": 10},
)


class Database:
    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._enable_sqlite_foreign_keys)
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
        )

    @staticmethod
    def _enable_sqlite_foreign_keys(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    def init_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        with self.session() as session:
            if session.scalar(select(Product.id).limit(1)) is None:
                self._seed(session)
                session.commit()

    def session(self) -> Session:
        return self._session_factory()

    def reset(self) -> None:
        with self.session() as session:
            session.execute(delete(PaymentAttempt))
            session.execute(delete(Order))
            session.execute(delete(Product))
            self._seed(session)
            session.commit()

    @staticmethod
    def _seed(session: Session) -> None:
        for item in SEED_PRODUCTS:
            session.add(Product(currency="USD", **item))

    def dispose(self) -> None:
        self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.database.session() as session:
        yield session
