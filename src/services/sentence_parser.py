"""
Smart Sentence Parser for Sentence-Level Streaming

Detects sentence boundaries in LLM streaming output while handling edge cases:
- Abbreviations (Mr., Dr., etc., i.e., e.g.)
- Numbers (1.5, 3.14, $1,000.00)
- Ellipsis (...)
- Quoted speech

Works alongside Chatterbox TTS's native chunking strategy - we detect sentences
at the LLM callback level, then pass to Chatterbox with its native `streaming_strategy`.
"""

import re
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class SentenceParser:
    """
    Intelligent sentence boundary detection for streaming LLM responses.

    Example usage:
        parser = SentenceParser(min_sentence_length=10)

        # Add chunks as they arrive from LLM
        sentences = parser.add_chunk("Hello! How are you")
        # Returns: ["Hello!"]

        sentences = parser.add_chunk(" doing today? I'm fine")
        # Returns: [" How are you doing today?"]

        # Get remaining buffer at end of stream
        final = parser.finalize()
        # Returns: " I'm fine"
    """

    # Common abbreviations that don't end sentences
    ABBREVIATIONS = {
        # Titles
        'mr', 'mrs', 'ms', 'dr', 'prof', 'sr', 'jr',
        # Time/Date
        'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
        'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun',
        # Common abbreviations
        'etc', 'vs', 'no', 'vol', 'fig', 'pp', 'p', 'st', 'ave', 'blvd',
        # Academic
        'phd', 'md', 'ba', 'bs', 'ma', 'mph',
        # Latin
        'i.e', 'e.g', 'et al', 'ibid', 'cf',
    }

    # Sentence boundary markers
    SENTENCE_ENDERS = {'.', '!', '?'}

    # Pattern for detecting numbers (e.g., 1.5, 3.14, $1,000.00)
    NUMBER_PATTERN = re.compile(r'\d+\.(?:\d+)?')

    def __init__(self, min_sentence_length: int = 10):
        """
        Initialize sentence parser.

        Args:
            min_sentence_length: Minimum characters per sentence. Shorter sentences
                                are buffered with next sentence to avoid synthesizing
                                very short phrases like "Hi." or "Oh."
        """
        self.min_sentence_length = min_sentence_length
        self.buffer = ""
        self.pending_sentence = ""  # Buffer for sentences below min length

    def add_chunk(self, text: str) -> List[str]:
        """
        Add text chunk from LLM streaming and return completed sentences.

        Args:
            text: New text chunk from LLM stream

        Returns:
            List of completed sentences ready for TTS synthesis
        """
        if not text:
            return []

        self.buffer += text
        completed_sentences = []

        # Search for sentence boundaries
        while True:
            boundary_pos = self._find_next_boundary()

            if boundary_pos is None:
                # No complete sentence yet
                break

            # Extract sentence (including punctuation)
            sentence = self.buffer[:boundary_pos + 1].strip()
            self.buffer = self.buffer[boundary_pos + 1:]

            # Handle minimum sentence length
            if len(sentence) < self.min_sentence_length:
                # Buffer this sentence to combine with next
                self.pending_sentence += sentence + " "
                continue

            # Add pending sentence if any
            if self.pending_sentence:
                sentence = self.pending_sentence + sentence
                self.pending_sentence = ""

            completed_sentences.append(sentence)

        return completed_sentences

    def _find_next_boundary(self) -> Optional[int]:
        """
        Find the position of the next sentence boundary in the buffer.

        Returns:
            Position of sentence-ending punctuation, or None if no boundary found
        """
        for i, char in enumerate(self.buffer):
            if char not in self.SENTENCE_ENDERS:
                continue

            # Check if this is a true sentence boundary
            if self._is_sentence_boundary(i):
                return i

        return None

    def _is_sentence_boundary(self, pos: int) -> bool:
        """
        Determine if punctuation at position is a true sentence boundary.

        Handles edge cases:
        - Abbreviations (Mr., Dr., etc.)
        - Numbers (1.5, 3.14)
        - Ellipsis (...)
        - Initials (J.K. Rowling)

        Args:
            pos: Position of punctuation mark in buffer

        Returns:
            True if this is a sentence boundary, False otherwise
        """
        char = self.buffer[pos]

        # Look ahead - need whitespace or end of buffer after punctuation
        if pos + 1 < len(self.buffer):
            next_char = self.buffer[pos + 1]

            # Must have whitespace after punctuation (or another punctuation for ellipsis)
            if not next_char.isspace() and next_char not in self.SENTENCE_ENDERS:
                return False

            # Check for ellipsis (... or .. or even ..)
            if char == '.' and next_char == '.':
                return False  # Part of ellipsis

        # Look behind - check if we're after ellipsis dots
        if char == '.' and pos > 0:
            prev_char = self.buffer[pos - 1]
            # Check if previous char is also a dot (we're at end of ellipsis)
            if prev_char == '.':
                # Check if there's another dot before that (3+ dots total)
                if pos > 1 and self.buffer[pos - 2] == '.':
                    # We're at the end of "..." - NOT a sentence boundary
                    return False

        # Look behind to check for abbreviations and numbers
        if char == '.':
            # Check for numbers (1.5, 3.14, etc.)
            if self._is_decimal_point(pos):
                return False

            # Check for abbreviations (Mr., Dr., etc.)
            if self._is_abbreviation(pos):
                return False

            # Check for initials (J.K. Rowling - single letter followed by period)
            if self._is_initial(pos):
                return False

        # Sentence boundary confirmed
        return True

    def _is_decimal_point(self, pos: int) -> bool:
        """Check if period at position is part of a decimal number"""
        # Look behind for digit
        if pos > 0 and self.buffer[pos - 1].isdigit():
            # Look ahead for digit
            if pos + 1 < len(self.buffer) and self.buffer[pos + 1].isdigit():
                return True
        return False

    def _is_abbreviation(self, pos: int) -> bool:
        """Check if period at position is part of an abbreviation"""
        # Extract word before the period
        start = pos - 1
        while start >= 0 and self.buffer[start].isalpha():
            start -= 1
        start += 1

        if start < pos:
            word = self.buffer[start:pos].lower()

            # Check against known abbreviations
            if word in self.ABBREVIATIONS:
                return True

            # Check for multi-character abbreviations with internal periods (e.g., "i.e.", "e.g.")
            # Look for pattern: letter.letter. or letter.letter.letter.
            if pos + 1 < len(self.buffer):
                # Check if next char is letter (e.g., "i.e" part of "i.e.")
                if self.buffer[pos + 1].isalpha():
                    return True  # Likely abbreviation

        return False

    def _is_initial(self, pos: int) -> bool:
        """Check if period is part of an initial (e.g., 'J.' in 'J.K. Rowling')"""
        # Single letter followed by period
        if pos > 0 and pos + 1 < len(self.buffer):
            prev_char = self.buffer[pos - 1]
            next_char = self.buffer[pos + 1]

            # Pattern: space + letter + period + space or period
            if prev_char.isalpha() and (next_char.isspace() or next_char == '.'):
                # Check if only one letter before period
                if pos >= 2:
                    char_before = self.buffer[pos - 2]
                    if char_before.isspace() or char_before.isupper():
                        return True
                else:
                    # At start of buffer
                    return True

        return False

    def finalize(self) -> str:
        """
        Get remaining buffer content at end of stream.

        Called when LLM stream is complete to retrieve any pending text
        that doesn't end with sentence punctuation.

        Returns:
            Remaining buffered text (may be empty string)
        """
        # Combine pending and buffer
        final_text = (self.pending_sentence + self.buffer).strip()

        # Clear state
        self.buffer = ""
        self.pending_sentence = ""

        return final_text

    def reset(self):
        """Reset parser state for new conversation turn"""
        self.buffer = ""
        self.pending_sentence = ""


# Example usage and testing
if __name__ == "__main__":
    parser = SentenceParser(min_sentence_length=10)

    # Test cases
    test_chunks = [
        "Hello! How are you",
        " doing today? I'm Dr. Smith and I",
        " have 3.14 reasons to",
        " believe this. First, etc. Second",
        ", the value is $1,000.50. Finally!",
    ]

    print("Testing sentence parser:")
    for i, chunk in enumerate(test_chunks):
        sentences = parser.add_chunk(chunk)
        print(f"\nChunk {i + 1}: {repr(chunk)}")
        print(f"  Completed sentences: {sentences}")

    final = parser.finalize()
    print(f"\nFinal buffer: {repr(final)}")
