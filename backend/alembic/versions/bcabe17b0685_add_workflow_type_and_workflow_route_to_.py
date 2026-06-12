"""add workflow_type and workflow_route to workflow_def

Revision ID: bcabe17b0685
Revises: 9ccdc473c342
Create Date: 2026-06-12 02:23:28.092448

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcabe17b0685'
down_revision: Union[str, None] = '9ccdc473c342'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 先添加 workflow_type 为 nullable
    op.add_column(
        'ai_workflow_def',
        sa.Column('workflow_type', sa.String(length=20), nullable=True,
                  comment='类型: ai_workflow / app_workflow'),
    )
    # 为现有行填充默认值
    op.execute("UPDATE ai_workflow_def SET workflow_type = 'ai_workflow' WHERE workflow_type IS NULL")
    # 改为 NOT NULL
    op.alter_column('ai_workflow_def', 'workflow_type', nullable=False)
    # 创建索引
    op.create_index(op.f('ix_ai_workflow_def_workflow_type'), 'ai_workflow_def', ['workflow_type'], unique=False)

    # 添加 workflow_route（可为空）
    op.add_column(
        'ai_workflow_def',
        sa.Column('workflow_route', sa.String(length=100), nullable=True,
                  comment='路由标识符（发布后通过此路径访问，唯一）'),
    )
    op.create_unique_constraint(None, 'ai_workflow_def', ['workflow_route'])


def downgrade() -> None:
    op.drop_constraint(None, 'ai_workflow_def', type_='unique')
    op.drop_index(op.f('ix_ai_workflow_def_workflow_type'), table_name='ai_workflow_def')
    op.drop_column('ai_workflow_def', 'workflow_route')
    op.drop_column('ai_workflow_def', 'workflow_type')
