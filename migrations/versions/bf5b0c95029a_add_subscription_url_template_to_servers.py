"""add_subscription_url_template_to_servers

Revision ID: bf5b0c95029a
Revises: 894b6a0eb210
Create Date: 2026-05-27 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf5b0c95029a'
down_revision: Union[str, Sequence[str], None] = '894b6a0eb210'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('servers', sa.Column('subscription_url_template', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('servers', 'subscription_url_template')
