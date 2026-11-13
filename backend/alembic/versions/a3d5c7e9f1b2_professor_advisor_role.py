"""professor advisor role

Revision ID: a3d5c7e9f1b2
Revises: 8c4a920c9f58
Create Date: 2026-11-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3d5c7e9f1b2'
down_revision: Union[str, Sequence[str], None] = '8c4a920c9f58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('professors', sa.Column('advisor_role', sa.String(), server_default='unknown', nullable=False))
    op.add_column('professors', sa.Column('advisor_note', sa.Text(), nullable=True))
    op.add_column('professors', sa.Column('advisor_source_url', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('professors', 'advisor_source_url')
    op.drop_column('professors', 'advisor_note')
    op.drop_column('professors', 'advisor_role')
