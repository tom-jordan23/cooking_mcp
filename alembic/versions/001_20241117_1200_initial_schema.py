"""Initial schema for cooking lab notebook

Revision ID: 001_initial_schema
Revises:
Create Date: 2024-11-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema for notebook entries, users, and feedback."""

    # Create notebook_entries table
    op.create_table(
        'notebook_entries',
        sa.Column('id', sa.String(100), primary_key=True, comment='Format: YYYY-MM-DD_slug'),
        sa.Column('version', sa.Integer(), default=1, nullable=False, comment='Schema version for migrations'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False, comment='Recipe/cooking session title'),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False, comment='Date of cooking session'),
        sa.Column('tags', sa.JSON(), default=[], comment='AI-enhanced categorization tags'),
        sa.Column('gear_ids', sa.JSON(), default=[], comment='References to normalized equipment catalog'),
        sa.Column('servings', sa.Integer(), comment='Number of servings'),
        sa.Column('dinner_time', sa.DateTime(timezone=True), comment='Planned dinner time'),
        sa.Column('cooking_method', sa.String(50), comment='Standardized cooking method vocabulary'),
        sa.Column('difficulty_level', sa.Integer(), comment='Difficulty on 1-10 scale'),
        sa.Column('prep_time_minutes', sa.Integer(), comment='Preparation time in minutes'),
        sa.Column('cook_time_minutes', sa.Integer(), comment='Cooking time in minutes'),
        sa.Column('total_time_minutes', sa.Integer(), comment='Total time (computed field)'),
        sa.Column('style_guidelines', sa.JSON(), default={}, comment='Cooking style preferences and guidelines'),
        sa.Column('ingredients_normalized', sa.JSON(), default=[], comment='Structured ingredient data with AI normalization'),
        sa.Column('protocol', sa.Text(), comment='Markdown cooking protocol with AI-generated steps'),
        sa.Column('observations', sa.JSON(), default=[], comment='Time-series observations with AI insights'),
        sa.Column('outcomes', sa.JSON(), default={}, comment='Results, ratings, and AI recommendations'),
        sa.Column('scheduling', sa.JSON(), default={}, comment='Make-ahead scheduling and AI-optimized timing'),
        sa.Column('links', sa.JSON(), default=[], comment='External recipe links and references'),
        sa.Column('ai_metadata', sa.JSON(), default={}, comment='AI embeddings, similarity scores, and generated content'),
        sa.Column('git_commit_sha', sa.String(40), comment='Git commit SHA for this version'),
        sa.Column('git_file_path', sa.String(500), comment='Relative path in Git repository'),
        sa.Column('view_count', sa.Integer(), default=0, nullable=False, comment='Number of times entry has been viewed'),
        sa.Column('success_rate', sa.Float(), comment='Historical success rate for this recipe'),

        # Constraints
        sa.CheckConstraint("id ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$'", name='valid_entry_id_format'),
        sa.CheckConstraint("difficulty_level IS NULL OR (difficulty_level >= 1 AND difficulty_level <= 10)", name='valid_difficulty_level'),
        sa.CheckConstraint("prep_time_minutes IS NULL OR prep_time_minutes >= 0", name='positive_prep_time'),
        sa.CheckConstraint("cook_time_minutes IS NULL OR cook_time_minutes >= 0", name='positive_cook_time'),
        sa.CheckConstraint("total_time_minutes IS NULL OR total_time_minutes >= 0", name='positive_total_time'),
        sa.CheckConstraint("servings IS NULL OR servings > 0", name='positive_servings'),
    )

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True, comment='Internal user ID'),
        sa.Column('slack_user_id', sa.String(50), unique=True, comment='Slack user ID'),
        sa.Column('phone_hash', sa.String(64), unique=True, comment='Hashed phone number for privacy'),
        sa.Column('email_hash', sa.String(64), unique=True, comment='Hashed email for privacy'),
        sa.Column('telegram_user_id', sa.String(50), unique=True, comment='Telegram user ID'),
        sa.Column('display_name', sa.String(100), comment="User's preferred display name"),
        sa.Column('timezone', sa.String(50), comment="User's timezone for scheduling"),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False, comment='Whether user is active for notifications'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_feedback_at', sa.DateTime(timezone=True), comment='Last time user provided feedback'),
        sa.Column('preferred_channel', sa.Enum('slack', 'sms', 'telegram', 'whatsapp', 'signal', 'email', 'web', 'api', name='feedbackchannel'), comment="User's preferred feedback channel"),
        sa.Column('notification_enabled', sa.Boolean(), default=True, nullable=False, comment='Whether to send feedback reminders'),
        sa.Column('feedback_count', sa.Integer(), default=0, nullable=False, comment='Total number of feedback entries'),
        sa.Column('avg_rating', sa.Float(), comment='Average rating given by user'),
    )

    # Create feedback table
    op.create_table(
        'feedback',
        sa.Column('id', sa.String(36), primary_key=True, comment='Unique feedback ID'),
        sa.Column('entry_id', sa.String(100), sa.ForeignKey('notebook_entries.id', ondelete='CASCADE'), nullable=False, comment='Reference to notebook entry'),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, comment='Reference to user who provided feedback'),
        sa.Column('channel', sa.Enum('slack', 'sms', 'telegram', 'whatsapp', 'signal', 'email', 'web', 'api', name='feedbackchannel'), nullable=False, comment='Channel through which feedback was collected'),
        sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'error', 'rejected', name='feedbackstatus'), default='pending', comment='Processing status of feedback'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('feedback_timestamp', sa.DateTime(timezone=True), nullable=False, comment='When the feedback was originally provided'),
        sa.Column('rating_10', sa.Float(), comment='Overall rating on 1-10 scale'),
        sa.Column('axes', sa.JSON(), default={}, comment='Multi-dimensional rating axes (doneness, salt, smoke, crust, etc.)'),
        sa.Column('metrics', sa.JSON(), default={}, comment='Quantitative cooking metrics (internal temp, rest time, etc.)'),
        sa.Column('notes', sa.Text(), comment='Free-form feedback notes'),
        sa.Column('raw_input', sa.Text(), comment='Original raw input before normalization'),
        sa.Column('normalized_data', sa.JSON(), default={}, comment='Normalized feedback data after AI processing'),
        sa.Column('ai_insights', sa.JSON(), default={}, comment='AI-generated insights and analysis'),
        sa.Column('sentiment_score', sa.Float(), comment='Sentiment analysis score (-1 to 1)'),
        sa.Column('confidence_score', sa.Float(), comment='AI confidence in feedback interpretation'),
        sa.Column('is_verified', sa.Boolean(), default=False, nullable=False, comment='Whether feedback has been verified'),
        sa.Column('verification_notes', sa.Text(), comment='Notes from verification process'),
        sa.Column('error_message', sa.Text(), comment='Error message if processing failed'),
        sa.Column('retry_count', sa.Integer(), default=0, nullable=False, comment='Number of processing retries'),

        # Constraints
        sa.CheckConstraint("rating_10 IS NULL OR (rating_10 >= 1 AND rating_10 <= 10)", name='valid_rating_range'),
        sa.CheckConstraint("sentiment_score IS NULL OR (sentiment_score >= -1 AND sentiment_score <= 1)", name='valid_sentiment_range'),
        sa.CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)", name='valid_confidence_range'),
        sa.CheckConstraint("retry_count >= 0", name='non_negative_retry_count'),
    )

    # Create indexes for notebook_entries
    op.create_index('idx_notebook_entries_date', 'notebook_entries', ['date'])
    op.create_index('idx_notebook_entries_created_at', 'notebook_entries', ['created_at'])
    op.create_index('idx_notebook_entries_updated_at', 'notebook_entries', ['updated_at'])
    op.create_index('idx_notebook_entries_cooking_method', 'notebook_entries', ['cooking_method'])
    op.create_index('idx_notebook_entries_difficulty', 'notebook_entries', ['difficulty_level'])
    op.create_index('idx_notebook_entries_git_commit', 'notebook_entries', ['git_commit_sha'])
    op.create_index('idx_notebook_entries_date_method', 'notebook_entries', ['date', 'cooking_method'])
    op.create_index('idx_notebook_entries_difficulty_servings', 'notebook_entries', ['difficulty_level', 'servings'])

    # Create indexes for users
    op.create_index('idx_users_slack_id', 'users', ['slack_user_id'])
    op.create_index('idx_users_phone_hash', 'users', ['phone_hash'])
    op.create_index('idx_users_email_hash', 'users', ['email_hash'])
    op.create_index('idx_users_telegram_id', 'users', ['telegram_user_id'])
    op.create_index('idx_users_active', 'users', ['is_active'])
    op.create_index('idx_users_last_feedback', 'users', ['last_feedback_at'])

    # Create indexes for feedback
    op.create_index('idx_feedback_entry_id', 'feedback', ['entry_id'])
    op.create_index('idx_feedback_user_id', 'feedback', ['user_id'])
    op.create_index('idx_feedback_channel', 'feedback', ['channel'])
    op.create_index('idx_feedback_status', 'feedback', ['status'])
    op.create_index('idx_feedback_created_at', 'feedback', ['created_at'])
    op.create_index('idx_feedback_timestamp', 'feedback', ['feedback_timestamp'])
    op.create_index('idx_feedback_rating', 'feedback', ['rating_10'])
    op.create_index('idx_feedback_verified', 'feedback', ['is_verified'])
    op.create_index('idx_feedback_entry_timestamp', 'feedback', ['entry_id', 'feedback_timestamp'])
    op.create_index('idx_feedback_user_created', 'feedback', ['user_id', 'created_at'])
    op.create_index('idx_feedback_status_channel', 'feedback', ['status', 'channel'])


def downgrade() -> None:
    """Drop all tables and indexes."""

    # Drop indexes for feedback
    op.drop_index('idx_feedback_status_channel', 'feedback')
    op.drop_index('idx_feedback_user_created', 'feedback')
    op.drop_index('idx_feedback_entry_timestamp', 'feedback')
    op.drop_index('idx_feedback_verified', 'feedback')
    op.drop_index('idx_feedback_rating', 'feedback')
    op.drop_index('idx_feedback_timestamp', 'feedback')
    op.drop_index('idx_feedback_created_at', 'feedback')
    op.drop_index('idx_feedback_status', 'feedback')
    op.drop_index('idx_feedback_channel', 'feedback')
    op.drop_index('idx_feedback_user_id', 'feedback')
    op.drop_index('idx_feedback_entry_id', 'feedback')

    # Drop indexes for users
    op.drop_index('idx_users_last_feedback', 'users')
    op.drop_index('idx_users_active', 'users')
    op.drop_index('idx_users_telegram_id', 'users')
    op.drop_index('idx_users_email_hash', 'users')
    op.drop_index('idx_users_phone_hash', 'users')
    op.drop_index('idx_users_slack_id', 'users')

    # Drop indexes for notebook_entries
    op.drop_index('idx_notebook_entries_difficulty_servings', 'notebook_entries')
    op.drop_index('idx_notebook_entries_date_method', 'notebook_entries')
    op.drop_index('idx_notebook_entries_git_commit', 'notebook_entries')
    op.drop_index('idx_notebook_entries_difficulty', 'notebook_entries')
    op.drop_index('idx_notebook_entries_cooking_method', 'notebook_entries')
    op.drop_index('idx_notebook_entries_updated_at', 'notebook_entries')
    op.drop_index('idx_notebook_entries_created_at', 'notebook_entries')
    op.drop_index('idx_notebook_entries_date', 'notebook_entries')

    # Drop tables
    op.drop_table('feedback')
    op.drop_table('users')
    op.drop_table('notebook_entries')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS feedbackstatus')
    op.execute('DROP TYPE IF EXISTS feedbackchannel')