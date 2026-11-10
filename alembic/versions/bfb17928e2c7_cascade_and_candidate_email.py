"""cascade and candidate email

Revision ID: bfb17928e2c7
Revises: 14c255d65204
Create Date: 2026-11-11 04:19:37.049855

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bfb17928e2c7'
down_revision: Union[str, None] = '14c255d65204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('applications_candidate_id_fkey', 'applications', type_='foreignkey')
    op.drop_constraint('applications_opening_id_fkey', 'applications', type_='foreignkey')
    op.create_foreign_key(
        'applications_candidate_id_fkey', 'applications', 'candidates', ['candidate_id'], ['id'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'applications_opening_id_fkey', 'applications', 'role_openings', ['opening_id'], ['id'], ondelete='RESTRICT'
    )
    op.create_unique_constraint('candidates_email_key', 'candidates', ['email'])
    op.drop_constraint('scorecard_items_scorecard_id_fkey', 'scorecard_items', type_='foreignkey')
    op.create_foreign_key(
        'scorecard_items_scorecard_id_fkey', 'scorecard_items', 'scorecards', ['scorecard_id'], ['id'], ondelete='CASCADE'
    )
    op.drop_constraint('scorecards_opening_id_fkey', 'scorecards', type_='foreignkey')
    op.create_foreign_key(
        'scorecards_opening_id_fkey', 'scorecards', 'role_openings', ['opening_id'], ['id'], ondelete='CASCADE'
    )


def downgrade() -> None:
    op.drop_constraint('scorecards_opening_id_fkey', 'scorecards', type_='foreignkey')
    op.create_foreign_key('scorecards_opening_id_fkey', 'scorecards', 'role_openings', ['opening_id'], ['id'])
    op.drop_constraint('scorecard_items_scorecard_id_fkey', 'scorecard_items', type_='foreignkey')
    op.create_foreign_key('scorecard_items_scorecard_id_fkey', 'scorecard_items', 'scorecards', ['scorecard_id'], ['id'])
    op.drop_constraint('candidates_email_key', 'candidates', type_='unique')
    op.drop_constraint('applications_opening_id_fkey', 'applications', type_='foreignkey')
    op.drop_constraint('applications_candidate_id_fkey', 'applications', type_='foreignkey')
    op.create_foreign_key('applications_opening_id_fkey', 'applications', 'role_openings', ['opening_id'], ['id'])
    op.create_foreign_key('applications_candidate_id_fkey', 'applications', 'candidates', ['candidate_id'], ['id'])
