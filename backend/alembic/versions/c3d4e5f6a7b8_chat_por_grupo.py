"""chat por grupo (mensajes, modo IA y resumen a nivel de grupo)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('grupos', sa.Column('modo_ia', sa.String(length=20), server_default='automatico', nullable=False))
    op.add_column('grupos', sa.Column('resumen_chat', sa.Text(), nullable=True))
    op.add_column('grupos', sa.Column('resumen_hasta_id', sa.Integer(), nullable=True))
    op.add_column('mensajes_chat', sa.Column('id_grupo', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_mensajes_chat_id_grupo', 'mensajes_chat', 'grupos', ['id_grupo'], ['id'], ondelete='CASCADE')
    op.create_index('ix_mensajes_chat_id_grupo', 'mensajes_chat', ['id_grupo'])
    # Los mensajes existentes pasan al grupo del dueño de su proyecto.
    op.execute(
        "UPDATE mensajes_chat SET id_grupo = ("
        " SELECT u.id_grupo FROM proyectos p JOIN usuarios u ON u.id = p.id_administrador"
        " WHERE p.id = mensajes_chat.id_proyecto)"
    )


def downgrade() -> None:
    op.drop_index('ix_mensajes_chat_id_grupo', table_name='mensajes_chat')
    op.drop_constraint('fk_mensajes_chat_id_grupo', 'mensajes_chat', type_='foreignkey')
    op.drop_column('mensajes_chat', 'id_grupo')
    op.drop_column('grupos', 'resumen_hasta_id')
    op.drop_column('grupos', 'resumen_chat')
    op.drop_column('grupos', 'modo_ia')
