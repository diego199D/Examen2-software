"""clase de asociacion y tabla intermedia (N:M, segundo parcial)

Revision ID: a1b2c3d4e5f6
Revises: 3c32cd2a8dc4
Create Date: 2026-11-09 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '3c32cd2a8dc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('relaciones', sa.Column('id_clase_asociacion', sa.String(length=36), nullable=True))
    op.add_column('relaciones', sa.Column('tabla_intermedia', sa.String(length=63), nullable=True))
    op.create_foreign_key(
        'fk_relaciones_id_clase_asociacion',
        'relaciones',
        'clases_uml',
        ['id_clase_asociacion'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_relaciones_id_clase_asociacion', 'relaciones', type_='foreignkey')
    op.drop_column('relaciones', 'tabla_intermedia')
    op.drop_column('relaciones', 'id_clase_asociacion')
