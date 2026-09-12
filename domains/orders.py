from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
import secrets
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    CheckConstraint,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ArgumentError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from sqlalchemy.pool import StaticPool


MAX_ORDER_ITEM_QUANTITY = 999
VALID_EMAIL_STATUSES = frozenset({"pending", "sent", "failed"})
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MONETARY_KEYS = frozenset(
    {
        "amount",
        "amounts",
        "cost",
        "costs",
        "currencies",
        "currency",
        "discount",
        "discounts",
        "linetotal",
        "msrp",
        "price",
        "prices",
        "retailprice",
        "shippingcost",
        "subtotal",
        "tax",
        "taxes",
        "total",
        "totalamount",
        "unitprice",
        "wholesaleprice",
    }
)


class DatabaseConfigurationError(RuntimeError):
    """Raised when durable database configuration is missing or invalid."""


class OrderPersistenceError(RuntimeError):
    """Raised when an order cannot be safely persisted or retrieved."""


class IdempotencyConflictError(OrderPersistenceError):
    """Raised when an idempotency key is reused for a different order."""


class OrderValidationError(ValueError):
    """Raised when an order payload fails server-side validation."""


class Base(DeclarativeBase):
    pass


class OrderRecord(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("total_distinct_items > 0", name="ck_orders_distinct_items_positive"),
        CheckConstraint("total_quantity > 0", name="ck_orders_total_quantity_positive"),
        CheckConstraint("email_status IN ('pending', 'sent', 'failed')", name="ck_orders_email_status"),
        UniqueConstraint("id", name="uq_orders_id"),
        UniqueConstraint("order_number", name="uq_orders_order_number"),
        UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),
        UniqueConstraint("access_token", name="uq_orders_access_token"),
    )

    internal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), nullable=False)
    order_number: Mapped[str | None] = mapped_column(String(24), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    access_token: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="submitted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    address_line_1: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    address_line_2: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    city: Mapped[str] = mapped_column(String(160), nullable=False)
    state: Mapped[str] = mapped_column(String(160), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    country: Mapped[str] = mapped_column(String(160), nullable=False)
    country_key: Mapped[str] = mapped_column(String(8), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    order_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    total_distinct_items: Mapped[int] = mapped_column(Integer, nullable=False)
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    email_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    email_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    csv_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    csv_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    items: Mapped[list[OrderItemRecord]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItemRecord.position",
    )


class OrderItemRecord(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0 AND quantity <= 999", name="ck_order_items_quantity"),
        CheckConstraint("position > 0", name="ck_order_items_position_positive"),
        UniqueConstraint("order_id", "position", name="uq_order_items_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.internal_id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    sku: Mapped[str] = mapped_column(String(120), nullable=False)
    product_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    variant: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    collection: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    image: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    item_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    order: Mapped[OrderRecord] = relationship(back_populates="items")


@dataclass(frozen=True)
class SavedOrderItem:
    sku: str
    product_name: str
    description: str
    variant: str
    collection: str
    quantity: int
    notes: str
    image: str
    metadata: dict[str, Any]

    @property
    def code(self) -> str:
        return self.sku

    @property
    def name(self) -> str:
        return self.product_name

    @property
    def qty(self) -> int:
        return self.quantity

    def as_order_row(self) -> dict[str, Any]:
        return {
            "code": self.sku,
            "name": self.product_name,
            "description": self.description,
            "variant": self.variant,
            "collection": self.collection,
            "quantity": self.quantity,
            "notes": self.notes,
            "image": self.image,
        }


@dataclass(frozen=True)
class SavedOrder:
    id: str
    order_number: str
    access_token: str
    status: str
    created_at: datetime
    submitted_at: datetime
    customer: dict[str, str]
    items: tuple[SavedOrderItem, ...]
    metadata: dict[str, Any]
    total_distinct_items: int
    total_quantity: int
    email_status: str
    email_attempted_at: datetime | None
    email_sent_at: datetime | None
    email_error: str | None
    csv_text: str | None
    csv_filename: str | None

    @property
    def order_id(self) -> str:
        return self.order_number

    @property
    def order_rows(self) -> list[dict[str, Any]]:
        return [item.as_order_row() for item in self.items]


@dataclass(frozen=True)
class CreateOrderResult:
    order: SavedOrder
    created: bool


def _normalized_database_url(value: str, *, allow_sqlite_for_tests: bool = False) -> str:
    url = str(value or "").strip()
    if not url:
        raise DatabaseConfigurationError("DATABASE_URL is required for order persistence.")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgresql+psycopg://"):
        return url
    if allow_sqlite_for_tests and url.startswith("sqlite+pysqlite://"):
        return url
    raise DatabaseConfigurationError(
        "DATABASE_URL must use PostgreSQL; sqlite+pysqlite is accepted only when explicitly configured for tests."
    )


def create_database_engine(database_url: str, *, allow_sqlite_for_tests: bool = False) -> Engine:
    url = _normalized_database_url(database_url, allow_sqlite_for_tests=allow_sqlite_for_tests)
    try:
        if url.startswith("sqlite+pysqlite://"):
            sqlite_options: dict[str, Any] = {
                "future": True,
                "connect_args": {"check_same_thread": False},
                "hide_parameters": True,
            }
            if url == "sqlite+pysqlite:///:memory:":
                sqlite_options["poolclass"] = StaticPool
            engine = create_engine(url, **sqlite_options)
        else:
            engine = create_engine(
                url,
                future=True,
                pool_size=1,
                max_overflow=0,
                pool_timeout=5,
                pool_pre_ping=True,
                pool_recycle=300,
                connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
                hide_parameters=True,
            )
    except (ArgumentError, TypeError, ValueError):
        raise DatabaseConfigurationError("DATABASE_URL is invalid.") from None

    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def database_url_from_env() -> str:
    return _normalized_database_url(os.getenv("DATABASE_URL", ""))


def _clean_string(value: Any, *, field: str, maximum: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise OrderValidationError(f"{field} is required.")
    if len(text) > maximum:
        raise OrderValidationError(f"{field} is too long.")
    return text


def _reject_monetary_keys(
    value: Any,
    *,
    field: str,
    seen: set[int] | None = None,
) -> None:
    if seen is None:
        seen = set()
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in seen:
            return
        seen.add(identity)
        for key, nested_value in value.items():
            canonical_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if canonical_key in _MONETARY_KEYS:
                raise OrderValidationError(f"{field} contains unsupported monetary field: {key}")
            _reject_monetary_keys(nested_value, field=field, seen=seen)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        identity = id(value)
        if identity in seen:
            return
        seen.add(identity)
        for nested_value in value:
            _reject_monetary_keys(nested_value, field=field, seen=seen)


def _normalize_json_object(value: Mapping[str, Any] | None, *, field: str) -> dict[str, Any]:
    normalized = dict(value or {})
    try:
        encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise OrderValidationError(f"{field} must be JSON serializable.") from exc
    if len(encoded.encode("utf-8")) > 16_384:
        raise OrderValidationError(f"{field} is too large.")
    _reject_monetary_keys(normalized, field=field)
    return normalized


def _normalize_payload(
    customer: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any] | None,
) -> tuple[dict[str, str], list[dict[str, Any]], dict[str, Any]]:
    normalized_customer = {
        "name": _clean_string(customer.get("name"), field="name", maximum=200, required=True),
        "company": _clean_string(customer.get("company"), field="company", maximum=200, required=True),
        "phone": _clean_string(customer.get("phone"), field="phone", maximum=80, required=True),
        "email": _clean_string(customer.get("email"), field="email", maximum=320),
        "address_line_1": _clean_string(customer.get("address_line_1"), field="address line 1", maximum=300),
        "address_line_2": _clean_string(customer.get("address_line_2"), field="address line 2", maximum=300),
        "city": _clean_string(customer.get("city"), field="city", maximum=160, required=True),
        "state": _clean_string(customer.get("state"), field="state", maximum=160, required=True),
        "postal_code": _clean_string(customer.get("postal_code"), field="postal code", maximum=40),
        "country": _clean_string(customer.get("country"), field="country", maximum=160, required=True),
        "country_key": _clean_string(customer.get("country_key"), field="country key", maximum=8, required=True).lower(),
        "notes": _clean_string(customer.get("notes"), field="order notes", maximum=4000),
    }
    if normalized_customer["email"] and not _EMAIL_PATTERN.fullmatch(normalized_customer["email"]):
        raise OrderValidationError("email is invalid.")

    if not items:
        raise OrderValidationError("At least one order item is required.")
    normalized_items: list[dict[str, Any]] = []
    seen_skus: set[str] = set()
    for raw_item in items:
        _reject_monetary_keys(raw_item, field="order item")
        sku = _clean_string(raw_item.get("sku", raw_item.get("code")), field="SKU", maximum=120, required=True)
        if sku in seen_skus:
            raise OrderValidationError(f"Duplicate SKU in order: {sku}")
        seen_skus.add(sku)
        raw_quantity = raw_item.get("quantity", raw_item.get("qty", 0))
        try:
            numeric_quantity = Decimal(str(raw_quantity))
            if isinstance(raw_quantity, bool) or not numeric_quantity.is_finite():
                raise ValueError
            quantity = int(numeric_quantity)
            if numeric_quantity != quantity:
                raise ValueError
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise OrderValidationError(f"Invalid quantity for {sku}.") from exc
        if quantity < 1 or quantity > MAX_ORDER_ITEM_QUANTITY:
            raise OrderValidationError(f"Invalid quantity for {sku}.")
        normalized_items.append(
            {
                "sku": sku,
                "product_name": _clean_string(raw_item.get("product_name", raw_item.get("name", sku)), field=f"product name for {sku}", maximum=300, required=True),
                "description": _clean_string(raw_item.get("description"), field=f"description for {sku}", maximum=4000),
                "variant": _clean_string(raw_item.get("variant"), field=f"variant for {sku}", maximum=200),
                "collection": _clean_string(raw_item.get("collection"), field=f"collection for {sku}", maximum=200),
                "quantity": quantity,
                "notes": _clean_string(raw_item.get("notes", raw_item.get("note")), field=f"notes for {sku}", maximum=500),
                "image": _clean_string(raw_item.get("image"), field=f"image for {sku}", maximum=500),
                "metadata": _normalize_json_object(raw_item.get("metadata"), field=f"metadata for {sku}"),
            }
        )
    return normalized_customer, normalized_items, _normalize_json_object(metadata, field="order metadata")


def _payload_hash(customer: dict[str, str], items: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
    payload = json.dumps(
        {"customer": customer, "items": items, "metadata": metadata},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _saved_order(record: OrderRecord) -> SavedOrder:
    return SavedOrder(
        id=record.id,
        order_number=str(record.order_number or ""),
        access_token=record.access_token,
        status=record.status,
        created_at=_utc(record.created_at) or datetime.now(timezone.utc),
        submitted_at=_utc(record.submitted_at) or datetime.now(timezone.utc),
        customer={
            "name": record.customer_name,
            "company": record.company,
            "phone": record.phone,
            "email": record.email,
            "address_line_1": record.address_line_1,
            "address_line_2": record.address_line_2,
            "city": record.city,
            "state": record.state,
            "postal_code": record.postal_code,
            "country": record.country,
            "country_key": record.country_key,
            "notes": record.notes,
        },
        items=tuple(
            SavedOrderItem(
                sku=item.sku,
                product_name=item.product_name,
                description=item.description,
                variant=item.variant,
                collection=item.collection,
                quantity=item.quantity,
                notes=item.notes,
                image=item.image,
                metadata=dict(item.item_metadata or {}),
            )
            for item in record.items
        ),
        metadata=dict(record.order_metadata or {}),
        total_distinct_items=record.total_distinct_items,
        total_quantity=record.total_quantity,
        email_status=record.email_status,
        email_attempted_at=_utc(record.email_attempted_at),
        email_sent_at=_utc(record.email_sent_at),
        email_error=record.email_error,
        csv_text=record.csv_text,
        csv_filename=record.csv_filename,
    )


class OrderRepository:
    def __init__(
        self,
        database_url: str | None = None,
        *,
        engine: Engine | None = None,
        allow_sqlite_for_tests: bool = False,
    ) -> None:
        if engine is None:
            engine = create_database_engine(
                database_url or database_url_from_env(),
                allow_sqlite_for_tests=allow_sqlite_for_tests,
            )
        self.engine = engine

    def create_schema_for_tests(self) -> None:
        if self.engine.dialect.name != "sqlite":
            raise DatabaseConfigurationError("Test schema creation is restricted to explicit SQLite databases.")
        Base.metadata.create_all(self.engine)

    def create_order(
        self,
        *,
        idempotency_key: str,
        customer: Mapping[str, Any],
        items: Sequence[Mapping[str, Any]],
        metadata: Mapping[str, Any] | None = None,
    ) -> CreateOrderResult:
        normalized_key = _clean_string(idempotency_key, field="idempotency key", maximum=200, required=True)
        if len(normalized_key) < 8:
            raise OrderValidationError("idempotency key is too short.")
        normalized_customer, normalized_items, normalized_metadata = _normalize_payload(customer, items, metadata)
        digest = _payload_hash(normalized_customer, normalized_items, normalized_metadata)

        now = datetime.now(timezone.utc)
        record = OrderRecord(
            id=str(uuid4()),
            idempotency_key=normalized_key,
            payload_hash=digest,
            access_token=secrets.token_urlsafe(32),
            status="submitted",
            created_at=now,
            submitted_at=now,
            customer_name=normalized_customer["name"],
            company=normalized_customer["company"],
            phone=normalized_customer["phone"],
            email=normalized_customer["email"],
            address_line_1=normalized_customer["address_line_1"],
            address_line_2=normalized_customer["address_line_2"],
            city=normalized_customer["city"],
            state=normalized_customer["state"],
            postal_code=normalized_customer["postal_code"],
            country=normalized_customer["country"],
            country_key=normalized_customer["country_key"],
            notes=normalized_customer["notes"],
            order_metadata=normalized_metadata,
            total_distinct_items=len(normalized_items),
            total_quantity=sum(item["quantity"] for item in normalized_items),
            email_status="pending",
        )
        record.items = [
            OrderItemRecord(
                position=position,
                sku=item["sku"],
                product_name=item["product_name"],
                description=item["description"],
                variant=item["variant"],
                collection=item["collection"],
                quantity=item["quantity"],
                notes=item["notes"],
                image=item["image"],
                item_metadata=item["metadata"],
            )
            for position, item in enumerate(normalized_items, start=1)
        ]

        try:
            with Session(self.engine) as session, session.begin():
                existing = session.scalar(
                    select(OrderRecord).where(OrderRecord.idempotency_key == normalized_key)
                )
                if existing is not None:
                    if existing.payload_hash != digest:
                        raise IdempotencyConflictError(
                            "This submission key was already used for a different order."
                        )
                    return CreateOrderResult(_saved_order(existing), created=False)
                session.add(record)
                session.flush()
                record.order_number = f"#CE{record.internal_id:08d}"
                session.flush()
                saved = _saved_order(record)
            return CreateOrderResult(saved, created=True)
        except IdempotencyConflictError:
            raise
        except IntegrityError as exc:
            # A concurrent request may win the unique idempotency-key race.
            try:
                with Session(self.engine) as session:
                    existing = session.scalar(
                        select(OrderRecord).where(OrderRecord.idempotency_key == normalized_key)
                    )
                    if existing is not None:
                        if existing.payload_hash != digest:
                            raise IdempotencyConflictError(
                                "This submission key was already used for a different order."
                            ) from exc
                        return CreateOrderResult(_saved_order(existing), created=False)
            except IdempotencyConflictError:
                raise
            except SQLAlchemyError:
                pass
            raise OrderPersistenceError("The order could not be saved.") from exc
        except SQLAlchemyError as exc:
            raise OrderPersistenceError("The order could not be saved.") from exc

    def get_order(self, order_id: str) -> SavedOrder | None:
        try:
            with Session(self.engine) as session:
                record = session.scalar(select(OrderRecord).where(OrderRecord.id == str(order_id)))
                return _saved_order(record) if record is not None else None
        except SQLAlchemyError as exc:
            raise OrderPersistenceError("The order could not be retrieved.") from exc

    def get_order_by_access_token(self, access_token: str) -> SavedOrder | None:
        try:
            with Session(self.engine) as session:
                record = session.scalar(
                    select(OrderRecord).where(OrderRecord.access_token == str(access_token))
                )
                return _saved_order(record) if record is not None else None
        except SQLAlchemyError as exc:
            raise OrderPersistenceError("The order could not be retrieved.") from exc

    def record_email_delivery(
        self,
        order_id: str,
        status: str,
        *,
        error_message: str | None = None,
    ) -> SavedOrder:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in VALID_EMAIL_STATUSES:
            raise OrderValidationError("Invalid email delivery status.")
        now = datetime.now(timezone.utc)
        try:
            with Session(self.engine) as session, session.begin():
                record = session.scalar(select(OrderRecord).where(OrderRecord.id == str(order_id)))
                if record is None:
                    raise OrderPersistenceError("Order not found.")
                record.email_status = normalized_status
                if normalized_status in {"sent", "failed"}:
                    record.email_attempted_at = now
                record.email_sent_at = now if normalized_status == "sent" else None
                record.email_error = (
                    _clean_string(error_message, field="email error", maximum=1000)
                    if normalized_status == "failed"
                    else None
                )
                session.flush()
                saved = _saved_order(record)
            return saved
        except OrderPersistenceError:
            raise
        except SQLAlchemyError as exc:
            raise OrderPersistenceError("Email delivery status could not be saved.") from exc

    def store_order_csv(self, order_id: str, csv_text: str, csv_filename: str) -> SavedOrder:
        normalized_filename = _clean_string(csv_filename, field="CSV filename", maximum=255, required=True)
        try:
            with Session(self.engine) as session, session.begin():
                record = session.scalar(select(OrderRecord).where(OrderRecord.id == str(order_id)))
                if record is None:
                    raise OrderPersistenceError("Order not found.")
                record.csv_text = str(csv_text)
                record.csv_filename = normalized_filename
                session.flush()
                saved = _saved_order(record)
            return saved
        except OrderPersistenceError:
            raise
        except SQLAlchemyError as exc:
            raise OrderPersistenceError("The order CSV could not be saved.") from exc


def repository_from_env() -> OrderRepository:
    return OrderRepository(database_url_from_env())
