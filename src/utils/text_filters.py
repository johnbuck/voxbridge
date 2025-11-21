"""
Text filtering utilities for VoxBridge TTS preprocessing.

Removes roleplay actions and markdown formatting that would sound
unnatural when spoken by TTS synthesis.

Example:
    >>> from src.utils.text_filters import filter_action_text
    >>> text = "*perks ears up* Oh! Testing? *tilts head*"
    >>> filtered = filter_action_text(text)
    >>> print(filtered)
    "Oh! Testing?"
"""

import re
import logging
from typing import Tuple, Dict, Optional

logger = logging.getLogger(__name__)


def filter_action_text(
    text: str,
    remove_asterisks: bool = True,
    preserve_math: bool = True
) -> str:
    """
    Remove roleplay actions and markdown formatting from text.

    Designed for TTS preprocessing to remove text that sounds unnatural
    when spoken aloud (e.g., "*perks ears up*" → "perks ears up").

    Args:
        text: Raw text to filter
        remove_asterisks: Remove *action* patterns (default: True)
        preserve_math: Don't remove math expressions like 2*3*4 (default: True)

    Returns:
        Filtered text suitable for TTS synthesis

    Examples:
        >>> filter_action_text("*perks ears* Hello!")
        "Hello!"

        >>> filter_action_text("The result is 2*3*4")
        "The result is 2*3*4"  # Math preserved

        >>> filter_action_text("*smiles* Hi *waves* there!")
        "Hi there!"
    """
    if not text or not isinstance(text, str):
        return text

    original_text = text

    # Pattern 1: Remove asterisk-wrapped actions
    if remove_asterisks:
        if preserve_math:
            # Only remove if NOT surrounded by digits (preserves math)
            # Negative lookbehind (?<!\d) and negative lookahead (?!\d)
            # Matches: *text* but not 2*3*4
            text = re.sub(r'(?<!\d)\*+[^*]+\*+(?!\d)', '', text)
        else:
            # Remove all asterisk-wrapped text
            text = re.sub(r'\*+[^*]+\*+', '', text)

    # Pattern 2: Clean up whitespace artifacts
    text = re.sub(r'\s{2,}', ' ', text)  # Multiple spaces → single space
    text = re.sub(r'\s+([,.!?;:])', r'\1', text)  # Space before punctuation
    text = text.strip()

    # Log if filtering made changes
    if text != original_text and text:
        removed = len(original_text) - len(text)
        logger.debug(f"🔧 [TEXT_FILTER] Removed {removed} chars from: \"{original_text[:50]}...\"")

    return text


def filter_action_text_with_metadata(text: str) -> Tuple[str, Dict]:
    """
    Filter action text and return metadata about what was removed.

    Useful for logging, debugging, and analytics to understand
    what content is being filtered and how much.

    Args:
        text: Raw text to filter

    Returns:
        Tuple of (filtered_text, metadata) where metadata contains:
        - removed_actions: List of removed action strings
        - action_count: Number of actions filtered
        - char_diff: Character count difference
        - has_math: Boolean indicating if math expressions detected

    Examples:
        >>> text = "*perks ears* Hello *waves* world"
        >>> filtered, meta = filter_action_text_with_metadata(text)
        >>> print(filtered)
        "Hello world"
        >>> print(meta['action_count'])
        2
        >>> print(meta['removed_actions'])
        ['perks ears', 'waves']
    """
    metadata = {
        'removed_actions': [],
        'action_count': 0,
        'char_diff': 0,
        'has_math': False
    }

    if not text:
        return text, metadata

    original_length = len(text)

    # Detect math expressions
    math_pattern = r'\d+\s*[\*\/\+\-]\s*\d+'
    if re.search(math_pattern, text):
        metadata['has_math'] = True

    # Extract actions before removing (for metadata)
    # Use same pattern as filter function to avoid matching math expressions
    action_pattern = r'(?<!\d)\*+([^*]+)\*+(?!\d)'
    actions = re.findall(action_pattern, text)

    metadata['removed_actions'] = actions
    metadata['action_count'] = len(actions)

    # Filter text
    filtered_text = filter_action_text(text)
    metadata['char_diff'] = original_length - len(filtered_text)

    return filtered_text, metadata


# Example usage and validation
if __name__ == "__main__":
    # Test cases for quick validation
    test_cases = [
        ("*perks ears up* Oh! Testing?", "Oh! Testing?"),
        ("The result is 2*3*4", "The result is 2*3*4"),
        ("*smiles* Hello *waves* there!", "Hello there!"),
        ("No actions here", "No actions here"),
        ("*action*  Multiple   spaces", "Multiple spaces"),
    ]

    print("Running text filter validation tests...\n")
    all_passed = True

    for input_text, expected in test_cases:
        result = filter_action_text(input_text)
        passed = result == expected
        all_passed = all_passed and passed

        status = "✅" if passed else "❌"
        print(f"{status} Input: '{input_text}'")
        print(f"   Expected: '{expected}'")
        print(f"   Got:      '{result}'")

        if not passed:
            print(f"   MISMATCH!")
        print()

    if all_passed:
        print("✅ All validation tests passed!")
    else:
        print("❌ Some tests failed - check implementation")
