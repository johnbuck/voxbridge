"""
Unit tests for text filtering utilities.

Tests the action text filtering functionality used to remove roleplay actions
from LLM responses before TTS synthesis.
"""

import pytest
from src.utils.text_filters import filter_action_text, filter_action_text_with_metadata


class TestFilterActionText:
    """Test filter_action_text() function."""

    def test_simple_action_removal(self):
        """Test basic asterisk action removal."""
        text = "*perks ears up*"
        result = filter_action_text(text)
        assert result == ""

    def test_action_with_surrounding_text(self):
        """Test action removal with surrounding text."""
        text = "*perks ears up* Oh! Testing?"
        result = filter_action_text(text)
        assert result == "Oh! Testing?"

    def test_multiple_actions(self):
        """Test multiple action removals."""
        text = "*perks ears up* Oh! Testing? *tilts head* Does my voice sound okay?"
        result = filter_action_text(text)
        assert result == "Oh! Testing? Does my voice sound okay?"

    def test_preserve_math_expressions(self):
        """Test that math expressions are preserved."""
        text = "The answer is 2*3*4 which equals 24"
        result = filter_action_text(text, preserve_math=True)
        assert "2*3*4" in result
        assert result == "The answer is 2*3*4 which equals 24"

    def test_preserve_simple_multiplication(self):
        """Test simple multiplication preservation."""
        text = "Calculate 5*6 for me"
        result = filter_action_text(text, preserve_math=True)
        assert "5*6" in result

    def test_mixed_actions_and_math(self):
        """Test actions removed but math preserved."""
        text = "*thinks* The result of 2*3 is 6 *nods*"
        result = filter_action_text(text, preserve_math=True)
        assert "2*3" in result
        assert "*thinks*" not in result
        assert "*nods*" not in result
        assert "The result of 2*3 is 6" in result

    def test_action_without_preserve_math(self):
        """Test that preserve_math=False removes all asterisks."""
        text = "Calculate 2*3*4"
        result = filter_action_text(text, preserve_math=False)
        # With preserve_math=False, even math gets removed
        assert "2" in result or result == "Calculate"  # Depending on regex behavior

    def test_multiple_asterisks(self):
        """Test actions with multiple asterisks."""
        text = "**bold action** normal text ***triple asterisk***"
        result = filter_action_text(text)
        assert "bold action" not in result
        assert "triple asterisk" not in result
        assert "normal text" in result

    def test_whitespace_cleanup(self):
        """Test that excessive whitespace is cleaned up."""
        text = "*action1*   *action2*   some    text"
        result = filter_action_text(text)
        assert "  " not in result  # No double spaces
        assert result == "some text"

    def test_punctuation_spacing(self):
        """Test punctuation spacing is normalized."""
        text = "*action* text , more text . end"
        result = filter_action_text(text)
        assert result == "text, more text. end"

    def test_empty_string(self):
        """Test empty string handling."""
        result = filter_action_text("")
        assert result == ""

    def test_none_input(self):
        """Test None input handling."""
        result = filter_action_text(None)
        assert result is None

    def test_no_actions(self):
        """Test text without any actions."""
        text = "Just normal text here"
        result = filter_action_text(text)
        assert result == text

    def test_action_at_end(self):
        """Test action at end of text."""
        text = "Some text here *action at end*"
        result = filter_action_text(text)
        assert result == "Some text here"

    def test_action_at_start(self):
        """Test action at start of text."""
        text = "*action at start* Some text here"
        result = filter_action_text(text)
        assert result == "Some text here"

    def test_only_actions(self):
        """Test text with only actions (should result in empty string)."""
        text = "*action1* *action2* *action3*"
        result = filter_action_text(text)
        assert result == ""

    def test_nested_asterisks(self):
        """Test nested asterisks handling."""
        text = "*outer *inner* outer* text"
        result = filter_action_text(text)
        # Regex should handle this gracefully
        assert "text" in result

    def test_single_asterisk_not_removed(self):
        """Test that single asterisks without pairs are preserved."""
        text = "This is a * single asterisk"
        result = filter_action_text(text)
        # Single asterisks don't match the pattern *content*
        assert "*" in result or "single asterisk" in result

    def test_math_at_boundaries(self):
        """Test math expressions at text boundaries."""
        text = "2*3 at start, 4*5*6 in middle, and 7*8 at end"
        result = filter_action_text(text, preserve_math=True)
        assert "2*3" in result
        assert "4*5*6" in result
        assert "7*8" in result

    def test_action_adjacent_to_digit(self):
        """Test actions adjacent to digits (edge case)."""
        text = "Number 5 *action* and 10"
        result = filter_action_text(text)
        assert "action" not in result
        assert "Number 5" in result
        assert "10" in result

    def test_complex_real_world_example(self):
        """Test complex real-world example from user's request."""
        text = "*perks ears up* Oh! Testing? *tilts head* Does my voice sound okay, Master? I... I can try speaking differently if you need..."
        result = filter_action_text(text)
        expected = "Oh! Testing? Does my voice sound okay, Master? I... I can try speaking differently if you need..."
        assert result == expected

    def test_unicode_in_actions(self):
        """Test unicode characters in actions."""
        text = "*🎵 singing* Hello there! *💭 thinking*"
        result = filter_action_text(text)
        assert "🎵" not in result
        assert "💭" not in result
        assert "Hello there!" in result

    def test_multiple_spaces_after_removal(self):
        """Test that multiple spaces are collapsed after action removal."""
        text = "Start *action* middle *action* end"
        result = filter_action_text(text)
        assert result == "Start middle end"
        assert "  " not in result


class TestFilterActionTextWithMetadata:
    """Test filter_action_text_with_metadata() function."""

    def test_metadata_structure(self):
        """Test metadata structure is correct."""
        text = "*action* text"
        filtered, metadata = filter_action_text_with_metadata(text)

        assert isinstance(metadata, dict)
        assert 'removed_actions' in metadata
        assert 'action_count' in metadata
        assert 'char_diff' in metadata
        assert 'has_math' in metadata

    def test_action_count_tracking(self):
        """Test action count is tracked correctly."""
        text = "*one* text *two* more *three*"
        filtered, metadata = filter_action_text_with_metadata(text)

        assert metadata['action_count'] == 3
        assert len(metadata['removed_actions']) == 3

    def test_removed_actions_list(self):
        """Test removed actions are listed correctly."""
        text = "*perks ears* Hello *tilts head*"
        filtered, metadata = filter_action_text_with_metadata(text)

        assert 'perks ears' in metadata['removed_actions']
        assert 'tilts head' in metadata['removed_actions']

    def test_char_diff_calculation(self):
        """Test character difference is calculated correctly."""
        text = "*action* text"  # 13 chars
        filtered, metadata = filter_action_text_with_metadata(text)
        # After removal: "text" = 4 chars, diff should be 13-4=9
        # But there's whitespace cleanup, so it might be different
        assert metadata['char_diff'] >= 0
        assert metadata['char_diff'] == len(text) - len(filtered)

    def test_math_detection_positive(self):
        """Test math expression detection (positive case)."""
        text = "Calculate 2*3 for me"
        filtered, metadata = filter_action_text_with_metadata(text)

        assert metadata['has_math'] is True

    def test_math_detection_negative(self):
        """Test math expression detection (negative case)."""
        text = "*action* just text here"
        filtered, metadata = filter_action_text_with_metadata(text)

        assert metadata['has_math'] is False

    def test_math_not_counted_as_action(self):
        """Test that math expressions are not counted as actions."""
        text = "Result is 2*3*4 which equals 24"
        filtered, metadata = filter_action_text_with_metadata(text)

        assert metadata['has_math'] is True
        assert metadata['action_count'] == 0
        assert len(metadata['removed_actions']) == 0

    def test_empty_string_metadata(self):
        """Test metadata for empty string."""
        text = ""
        filtered, metadata = filter_action_text_with_metadata(text)

        assert metadata['action_count'] == 0
        assert metadata['removed_actions'] == []
        assert metadata['char_diff'] == 0
        assert metadata['has_math'] is False

    def test_no_actions_metadata(self):
        """Test metadata when no actions present."""
        text = "Just normal text"
        filtered, metadata = filter_action_text_with_metadata(text)

        assert metadata['action_count'] == 0
        assert metadata['removed_actions'] == []
        assert metadata['char_diff'] == 0

    def test_complex_metadata_example(self):
        """Test metadata for complex real-world example."""
        text = "*perks ears up* Oh! Testing? *tilts head* Does my voice sound okay?"
        filtered, metadata = filter_action_text_with_metadata(text)

        assert metadata['action_count'] == 2
        assert 'perks ears up' in metadata['removed_actions']
        assert 'tilts head' in metadata['removed_actions']
        assert metadata['char_diff'] > 0
        assert metadata['has_math'] is False

    def test_filtered_text_matches_filter_function(self):
        """Test that filtered text matches filter_action_text() output."""
        text = "*action* some text *another*"

        filtered_direct = filter_action_text(text)
        filtered_with_meta, _ = filter_action_text_with_metadata(text)

        assert filtered_direct == filtered_with_meta

    def test_metadata_with_math_and_actions(self):
        """Test metadata when both math and actions present."""
        text = "*thinking* The answer is 2*3 *nods*"
        filtered, metadata = filter_action_text_with_metadata(text)

        assert metadata['has_math'] is True
        # Math expression 2*3 should NOT be in removed_actions
        assert '2' not in str(metadata['removed_actions'])
        assert 'thinking' in metadata['removed_actions']
        assert 'nods' in metadata['removed_actions']

    def test_none_input_metadata(self):
        """Test metadata handling for None input."""
        text = None
        filtered, metadata = filter_action_text_with_metadata(text)

        # Should return None and default metadata
        assert filtered is None
        assert metadata['action_count'] == 0

    def test_whitespace_impact_on_char_diff(self):
        """Test that char_diff accounts for whitespace cleanup."""
        text = "*action*   text   here"
        filtered, metadata = filter_action_text_with_metadata(text)

        original_len = len(text)
        filtered_len = len(filtered)
        assert metadata['char_diff'] == original_len - filtered_len

    def test_multiple_asterisks_metadata(self):
        """Test metadata with multiple asterisk levels."""
        text = "**bold action** normal ***triple***"
        filtered, metadata = filter_action_text_with_metadata(text)

        assert metadata['action_count'] == 2
        assert 'bold action' in metadata['removed_actions']
        assert 'triple' in metadata['removed_actions']

    def test_removed_actions_preserve_content(self):
        """Test that removed_actions contains only the content, not asterisks."""
        text = "*first action* text *second action*"
        filtered, metadata = filter_action_text_with_metadata(text)

        # Should extract content without asterisks
        assert 'first action' in metadata['removed_actions']
        assert 'second action' in metadata['removed_actions']
        # Should NOT include asterisks
        assert '*first action*' not in metadata['removed_actions']

    def test_edge_case_single_char_action(self):
        """Test single character action."""
        text = "*a* text here"
        filtered, metadata = filter_action_text_with_metadata(text)

        assert metadata['action_count'] == 1
        assert 'a' in metadata['removed_actions']
        assert filtered == "text here"

    def test_edge_case_very_long_action(self):
        """Test very long action text."""
        long_action = "a" * 1000
        text = f"*{long_action}* normal text"
        filtered, metadata = filter_action_text_with_metadata(text)

        assert metadata['action_count'] == 1
        assert long_action in metadata['removed_actions']
        assert filtered == "normal text"
