"""add_balance_and_promocode_to_gateway_enum

Revision ID: e8d77f24b0c9
Revises: bf5b0c95029a
Create Date: 2026-05-27 16:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8d77f24b0c9'
down_revision: Union[str, Sequence[str], None] = 'bf5b0c95029a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Check and add BALANCE
        check_balance = sa.text(
            "SELECT 1 FROM pg_type t "
            "JOIN pg_enum e ON t.oid = e.enumtypid "
            "WHERE t.typname = 'paymentgateway' AND e.enumlabel = 'BALANCE'"
        )
        exists_balance = bind.execute(check_balance).scalar()
        if not exists_balance:
            with op.get_context().autocommit_block():
                op.execute("ALTER TYPE paymentgateway ADD VALUE 'BALANCE'")

        # Check and add PROMOCODE
        check_promocode = sa.text(
            "SELECT 1 FROM pg_type t "
            "JOIN pg_enum e ON t.oid = e.enumtypid "
            "WHERE t.typname = 'paymentgateway' AND e.enumlabel = 'PROMOCODE'"
        )
        exists_promocode = bind.execute(check_promocode).scalar()
        if not exists_promocode:
            with op.get_context().autocommit_block():
                op.execute("ALTER TYPE paymentgateway ADD VALUE 'PROMOCODE'")


def downgrade() -> None:
    """Downgrade schema."""
    # Enums cannot be easily modified in downgrade in PostgreSQL without recreating the type
    pass
