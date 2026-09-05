"""Small schema upgrade helper for this create_all-based prototype.

Production should replace this with versioned Alembic migrations.  Unlike
``create_all``, this helper safely adds the two new invoice/promise columns to
an already-created demo database.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def upgrade_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    additions = {
        "invoices": {
            "last_contact_at": "TIMESTAMP NULL",
            "contact_tier": "VARCHAR(20) NULL",
        },
        "promises_to_pay": {
            "razorpay_order_id": "VARCHAR(100) NULL",
            "razorpay_payment_id": "VARCHAR(100) NULL",
        },
    }
    with engine.begin() as connection:
        for table, columns in additions.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
