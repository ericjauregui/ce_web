"""Remove monetary data while preserving orders and submission identity.

Revision ID: 20260912_0002
Revises: 20260912_0001
"""
import hashlib
import json

from alembic import op
import sqlalchemy as sa


revision = "20260912_0002"
down_revision = "20260912_0001"
branch_labels = None
depends_on = None

# Frozen migration logic: do not import evolving application models.
MONETARY_KEYS = {
    "amount", "amounts", "cost", "costs", "currencies", "currency", "discount", "discounts",
    "linetotal", "msrp", "price", "prices", "retailprice", "shippingcost", "subtotal",
    "tax", "taxes", "total", "totalamount", "unitprice", "wholesaleprice",
}


def _without_money(value):
    if isinstance(value, dict):
        return {
            key: _without_money(child)
            for key, child in value.items()
            if "".join(character for character in str(key).lower() if character.isalnum()) not in MONETARY_KEYS
        }
    if isinstance(value, list):
        return [_without_money(child) for child in value]
    return value


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("LOCK TABLE orders, order_items IN ACCESS EXCLUSIVE MODE"))
    metadata = sa.MetaData()
    orders = sa.Table("orders", metadata, autoload_with=connection)
    items = sa.Table("order_items", metadata, autoload_with=connection)
    last_id = 0
    # Small batches bound memory on the smallest database/application instances.
    while True:
        batch = connection.execute(
            sa.select(orders).where(orders.c.internal_id > last_id)
            .order_by(orders.c.internal_id).limit(100)
        ).mappings().all()
        if not batch:
            break
        for order in batch:
            customer = {
                field: order["customer_name" if field == "name" else field]
                for field in (
                    "name", "company", "phone", "email", "address_line_1", "address_line_2",
                    "city", "state", "postal_code", "country", "country_key", "notes",
                )
            }
            item_payloads = []
            for item in connection.execute(
                sa.select(items).where(items.c.order_id == order["internal_id"])
                .order_by(items.c.position)
            ).mappings().all():
                item_metadata = _without_money(item["item_metadata"] or {})
                item_payloads.append({
                    **{field: item[field] for field in (
                        "sku", "product_name", "description", "variant", "collection",
                        "quantity", "notes", "image",
                    )},
                    "metadata": item_metadata,
                })
                if item_metadata != item["item_metadata"]:
                    connection.execute(items.update().where(items.c.id == item["id"])
                                       .values(item_metadata=item_metadata))
            order_metadata = _without_money(order["order_metadata"] or {})
            payload = json.dumps(
                {"customer": customer, "items": item_payloads, "metadata": order_metadata},
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            )
            # Existing retries must still match the same order after removing
            # the formerly hashed monetary fields.
            connection.execute(orders.update().where(orders.c.internal_id == order["internal_id"])
                               .values(order_metadata=order_metadata,
                                       payload_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest()))
        last_id = batch[-1]["internal_id"]

    op.drop_column("order_items", "unit_price")
    op.drop_column("order_items", "line_total")
    op.drop_column("orders", "total_amount")
    op.drop_column("orders", "currency")


def downgrade() -> None:
    raise RuntimeError("Monetary data removal is irreversible; restore a backup only if explicitly required.")
