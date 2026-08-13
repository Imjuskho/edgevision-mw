"""Phase 3: health snapshot 4-dimension scores, dedup status fields, export job fields

Revision ID: 7e097577179d
Revises: 0009
Create Date: 2026-07-27 06:22:22.846704

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '7e097577179d'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- DatasetHealthSnapshot: replace 5 old columns with 4 dimension scores + action_items ---
    op.drop_column('dataset_health_snapshots', 'completeness_pct')
    op.drop_column('dataset_health_snapshots', 'consistency_pct')
    op.drop_column('dataset_health_snapshots', 'accuracy_pct')
    op.drop_column('dataset_health_snapshots', 'timeliness_pct')
    op.drop_column('dataset_health_snapshots', 'metrics')
    op.drop_column('dataset_health_snapshots', 'recommendations')
    op.alter_column('dataset_health_snapshots', 'overall_score',
                     existing_type=sa.Float(), type_=sa.Integer(),
                     existing_nullable=False)
    op.add_column('dataset_health_snapshots',
                   sa.Column('uniqueness_score', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('dataset_health_snapshots',
                   sa.Column('balance_score', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('dataset_health_snapshots',
                   sa.Column('coverage_score', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('dataset_health_snapshots',
                   sa.Column('confidence_score', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('dataset_health_snapshots',
                   sa.Column('action_items', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # --- DuplicateGroup: add detection_method + status, drop resolved ---
    op.drop_column('duplicate_groups', 'resolved')
    op.add_column('duplicate_groups',
                   sa.Column('detection_method', sa.String(50), nullable=False, server_default='unknown'))
    op.add_column('duplicate_groups',
                   sa.Column('status', sa.String(20), nullable=False, server_default='open'))

    # --- DuplicateGroupMember: add is_kept ---
    op.add_column('duplicate_group_members',
                   sa.Column('is_kept', sa.Boolean(), nullable=True))

    # --- ExportJob: add split_config, augmentation_config, image_count, output_path, checksum ---
    op.add_column('export_jobs',
                   sa.Column('split_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('export_jobs',
                   sa.Column('augmentation_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('export_jobs',
                   sa.Column('image_count', sa.Integer(), nullable=True))
    op.add_column('export_jobs',
                   sa.Column('output_path', sa.String(1000), nullable=True))
    op.add_column('export_jobs',
                   sa.Column('checksum', sa.String(128), nullable=True))


def downgrade() -> None:
    # ExportJob
    op.drop_column('export_jobs', 'checksum')
    op.drop_column('export_jobs', 'output_path')
    op.drop_column('export_jobs', 'image_count')
    op.drop_column('export_jobs', 'augmentation_config')
    op.drop_column('export_jobs', 'split_config')

    # DuplicateGroupMember
    op.drop_column('duplicate_group_members', 'is_kept')

    # DuplicateGroup
    op.drop_column('duplicate_groups', 'status')
    op.drop_column('duplicate_groups', 'detection_method')
    op.add_column('duplicate_groups',
                   sa.Column('resolved', sa.Boolean(), nullable=False, server_default='false'))

    # DatasetHealthSnapshot
    op.drop_column('dataset_health_snapshots', 'confidence_score')
    op.drop_column('dataset_health_snapshots', 'coverage_score')
    op.drop_column('dataset_health_snapshots', 'balance_score')
    op.drop_column('dataset_health_snapshots', 'uniqueness_score')
    op.drop_column('dataset_health_snapshots', 'action_items')
    op.alter_column('dataset_health_snapshots', 'overall_score',
                     existing_type=sa.Integer(), type_=sa.Float(),
                     existing_nullable=False)
    op.add_column('dataset_health_snapshots',
                   sa.Column('recommendations', postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column('dataset_health_snapshots',
                   sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False))
    op.add_column('dataset_health_snapshots',
                   sa.Column('timeliness_pct', sa.Float(), nullable=False))
    op.add_column('dataset_health_snapshots',
                   sa.Column('accuracy_pct', sa.Float(), nullable=False))
    op.add_column('dataset_health_snapshots',
                   sa.Column('consistency_pct', sa.Float(), nullable=False))
    op.add_column('dataset_health_snapshots',
                   sa.Column('completeness_pct', sa.Float(), nullable=False))
