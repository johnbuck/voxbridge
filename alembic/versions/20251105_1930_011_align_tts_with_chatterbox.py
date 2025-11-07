"""align TTS config with Chatterbox API

Revision ID: 011_align_tts_with_chatterbox
Revises: 010_remove_streaming_from_agents
Create Date: 2025-11-05 19:30:00.000000

Description:
    Remove unsupported TTS fields (tts_rate, tts_pitch) that don't work with Chatterbox.
    Add Chatterbox-supported TTS fields (exaggeration, cfg_weight, temperature, language).

    Breaking change: Existing agents will lose tts_rate and tts_pitch values.

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add Chatterbox-supported TTS parameters and remove unsupported ones.

    New fields (what Chatterbox actually uses):
    - tts_exaggeration: Emotion intensity (0.25-2.0, default 1.0)
    - tts_cfg_weight: Speech pace control (0.0-1.0, default 0.7)
    - tts_temperature: Sampling randomness (0.05-5.0, default 0.3)
    - tts_language: Language code (default "en")

    Removed fields (not supported by Chatterbox):
    - tts_rate: Chatterbox ignores the 'speed' parameter
    - tts_pitch: No equivalent in Chatterbox API
    """
    # Add new Chatterbox-supported columns
    op.add_column('agents', sa.Column('tts_exaggeration', sa.Float(), nullable=False, server_default='1.0'))
    op.add_column('agents', sa.Column('tts_cfg_weight', sa.Float(), nullable=False, server_default='0.7'))
    op.add_column('agents', sa.Column('tts_temperature', sa.Float(), nullable=False, server_default='0.3'))
    op.add_column('agents', sa.Column('tts_language', sa.String(length=10), nullable=False, server_default='en'))

    # Drop unsupported columns
    op.drop_column('agents', 'tts_rate')
    op.drop_column('agents', 'tts_pitch')


def downgrade() -> None:
    """
    Restore old TTS fields and remove Chatterbox-specific ones.

    Warning: This will lose tts_exaggeration, tts_cfg_weight, tts_temperature, tts_language values.
    """
    # Restore old columns (with default values)
    op.add_column('agents', sa.Column('tts_rate', sa.Float(), nullable=False, server_default='1.0'))
    op.add_column('agents', sa.Column('tts_pitch', sa.Float(), nullable=False, server_default='1.0'))

    # Drop new columns
    op.drop_column('agents', 'tts_language')
    op.drop_column('agents', 'tts_temperature')
    op.drop_column('agents', 'tts_cfg_weight')
    op.drop_column('agents', 'tts_exaggeration')
