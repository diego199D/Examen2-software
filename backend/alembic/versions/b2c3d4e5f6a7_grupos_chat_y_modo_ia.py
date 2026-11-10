"""grupos, chat grupal persistido y modo de la IA (segundo parcial)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-09 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'grupos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('nombre_normalizado', sa.String(length=100), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_grupos_nombre_normalizado', 'grupos', ['nombre_normalizado'], unique=True)

    op.add_column('usuarios', sa.Column('id_grupo', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_usuarios_id_grupo', 'usuarios', 'grupos', ['id_grupo'], ['id'], ondelete='SET NULL')

    op.add_column('proyectos', sa.Column('modo_ia', sa.String(length=20), server_default='automatico', nullable=False))
    op.add_column('proyectos', sa.Column('resumen_chat', sa.Text(), nullable=True))
    op.add_column('proyectos', sa.Column('resumen_hasta_id', sa.Integer(), nullable=True))

    tipo_mensaje = sa.Enum('humano', 'senior_ai', 'sistema', name='tipomensaje')
    op.create_table(
        'mensajes_chat',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('id_proyecto', sa.Integer(), sa.ForeignKey('proyectos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('id_usuario', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True),
        sa.Column('autor_nombre', sa.String(length=150), nullable=False),
        sa.Column('tipo', tipo_mensaje, nullable=False),
        sa.Column('texto', sa.Text(), nullable=False),
        sa.Column('datos', sa.JSON(), nullable=True),
        sa.Column('fecha', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_mensajes_chat_id_proyecto', 'mensajes_chat', ['id_proyecto'])


def downgrade() -> None:
    op.drop_index('ix_mensajes_chat_id_proyecto', table_name='mensajes_chat')
    op.drop_table('mensajes_chat')
    sa.Enum(name='tipomensaje').drop(op.get_bind(), checkfirst=True)
    op.drop_column('proyectos', 'resumen_hasta_id')
    op.drop_column('proyectos', 'resumen_chat')
    op.drop_column('proyectos', 'modo_ia')
    op.drop_constraint('fk_usuarios_id_grupo', 'usuarios', type_='foreignkey')
    op.drop_column('usuarios', 'id_grupo')
    op.drop_index('ix_grupos_nombre_normalizado', table_name='grupos')
    op.drop_table('grupos')
