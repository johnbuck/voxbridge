"""
Unit tests for SentenceParser

Tests sentence boundary detection with edge cases:
- Basic sentence endings (. ! ?)
- Abbreviations (Mr., Dr., etc.)
- Numbers (1.5, 3.14, $1,000.00)
- Ellipsis (...)
- Initials (J.K. Rowling)
- Minimum sentence length buffering
"""

import pytest
from src.services.sentence_parser import SentenceParser


class TestSentenceParserBasics:
    """Test basic sentence detection functionality"""

    def test_simple_sentence(self):
        """Test detection of simple sentence"""
        parser = SentenceParser(min_sentence_length=5)

        sentences = parser.add_chunk("Hello world!")
        assert sentences == ["Hello world!"]

    def test_multiple_sentences(self):
        """Test detection of multiple sentences in one chunk"""
        parser = SentenceParser(min_sentence_length=5)

        sentences = parser.add_chunk("Hello! How are you? I'm fine.")
        assert len(sentences) == 3
        assert sentences[0] == "Hello!"
        assert sentences[1] == "How are you?"
        assert sentences[2] == "I'm fine."

    def test_sentence_across_chunks(self):
        """Test sentence spanning multiple chunks"""
        parser = SentenceParser(min_sentence_length=5)

        # First chunk - no complete sentence
        sentences1 = parser.add_chunk("Hello ")
        assert sentences1 == []

        # Second chunk - completes sentence
        sentences2 = parser.add_chunk("world!")
        assert sentences2 == ["Hello world!"]

    def test_question_and_exclamation(self):
        """Test question marks and exclamation points"""
        parser = SentenceParser(min_sentence_length=5)

        sentences = parser.add_chunk("Really? Yes, indeed! Maybe later...")

        # "Really?" = 7 chars >= 5, emitted
        # "Yes, indeed!" = 12 chars >= 5, emitted
        # "Maybe later..." has ellipsis (not a boundary), in finalize
        assert len(sentences) >= 2
        assert "Really?" in sentences[0]
        assert "Yes, indeed!" in sentences[1]

    def test_finalize_remaining_text(self):
        """Test finalize() returns remaining buffer"""
        parser = SentenceParser(min_sentence_length=5)

        parser.add_chunk("Hello world")
        remaining = parser.finalize()

        assert remaining == "Hello world"

    def test_finalize_empty_buffer(self):
        """Test finalize() with empty buffer"""
        parser = SentenceParser(min_sentence_length=5)

        remaining = parser.finalize()
        assert remaining == ""


class TestAbbreviations:
    """Test abbreviation handling"""

    def test_title_abbreviations(self):
        """Test title abbreviations (Mr., Dr., etc.)"""
        parser = SentenceParser(min_sentence_length=10)

        # Should not split on abbreviation period
        sentences = parser.add_chunk("Hello Mr. Smith. How are you?")

        assert len(sentences) == 2
        assert "Mr. Smith" in sentences[0]
        assert "How are you?" in sentences[1]

    def test_multiple_titles(self):
        """Test multiple title abbreviations"""
        parser = SentenceParser(min_sentence_length=10)

        sentences = parser.add_chunk("Dr. Jones and Prof. Smith are here.")

        assert len(sentences) == 1
        assert "Dr. Jones and Prof. Smith are here." in sentences[0]

    def test_latin_abbreviations(self):
        """Test Latin abbreviations (i.e., e.g., etc.)"""
        parser = SentenceParser(min_sentence_length=10)

        sentences = parser.add_chunk("I like fruits, e.g., apples and oranges. They are healthy.")

        assert len(sentences) == 2
        assert "e.g." in sentences[0]
        assert "They are healthy." in sentences[1]

    def test_etc_abbreviation(self):
        """Test 'etc.' abbreviation"""
        parser = SentenceParser(min_sentence_length=10)

        sentences = parser.add_chunk("I need milk, eggs, bread, etc. from the store.")

        assert len(sentences) == 1
        assert "etc." in sentences[0]


class TestNumbers:
    """Test number handling"""

    def test_decimal_numbers(self):
        """Test decimal numbers (1.5, 3.14)"""
        parser = SentenceParser(min_sentence_length=10)

        sentences = parser.add_chunk("The price is 3.14 dollars. That's cheap.")

        assert len(sentences) == 2
        assert "3.14" in sentences[0]
        assert "That's cheap." in sentences[1]

    def test_large_decimal(self):
        """Test larger decimal numbers"""
        parser = SentenceParser(min_sentence_length=10)

        sentences = parser.add_chunk("Pi is approximately 3.14159. It's useful.")

        assert len(sentences) == 2
        assert "3.14159" in sentences[0]

    def test_multiple_decimals(self):
        """Test multiple decimal numbers"""
        parser = SentenceParser(min_sentence_length=10)

        sentences = parser.add_chunk("Values are 1.5 and 2.7. Sum is 4.2.")

        assert len(sentences) == 2
        assert "1.5 and 2.7" in sentences[0]
        assert "Sum is 4.2" in sentences[1]


class TestInitials:
    """Test initial handling (J.K. Rowling)"""

    def test_single_initial(self):
        """Test single initial (J. Smith)"""
        parser = SentenceParser(min_sentence_length=10)

        # Should not split on initial period
        sentences = parser.add_chunk("J. Smith wrote this. It's good.")

        assert len(sentences) == 2
        assert "J. Smith" in sentences[0]

    def test_double_initial(self):
        """Test double initials (J.K. Rowling)"""
        parser = SentenceParser(min_sentence_length=10)

        sentences = parser.add_chunk("J.K. Rowling wrote Harry Potter. It's famous.")

        assert len(sentences) == 2
        assert "J.K. Rowling" in sentences[0]
        assert "It's famous." in sentences[1]


class TestEllipsis:
    """Test ellipsis handling"""

    def test_three_dot_ellipsis(self):
        """Test three-dot ellipsis (...)"""
        parser = SentenceParser(min_sentence_length=10)

        # Ellipsis should not end sentence - it continues into next part
        sentences = parser.add_chunk("I was thinking... maybe we should go. Yes.")

        # Should get 1 complete sentence (ellipsis continues), "Yes." in finalize (too short)
        assert len(sentences) == 1
        assert "thinking... maybe we should go." in sentences[0]

        final = parser.finalize()
        assert final == "Yes."

    def test_ellipsis_continuation(self):
        """Test ellipsis as continuation"""
        parser = SentenceParser(min_sentence_length=10)

        sentences = parser.add_chunk("Well... I don't know. Maybe later?")

        assert len(sentences) == 2
        assert "Well... I don't know." in sentences[0]
        assert "Maybe later?" in sentences[1]


class TestMinimumLength:
    """Test minimum sentence length buffering"""

    def test_short_sentence_buffering(self):
        """Test short sentences are buffered with next sentence"""
        parser = SentenceParser(min_sentence_length=10)

        # "Hi." is too short, should buffer
        sentences = parser.add_chunk("Hi. How are you today?")

        # Should get one combined sentence
        assert len(sentences) == 1
        assert "Hi. How are you today?" in sentences[0]

    def test_multiple_short_sentences(self):
        """Test multiple short sentences buffered together"""
        parser = SentenceParser(min_sentence_length=10)

        sentences = parser.add_chunk("Hi. Oh. Yes. How are you doing today?")

        # "Hi. Oh. Yes." = 12 chars (>= 10), gets emitted
        # "How are you doing today?" gets emitted separately
        assert len(sentences) == 2
        assert "Hi. Oh. Yes." in sentences[0]
        assert "How are you doing today?" in sentences[1]

    def test_min_length_threshold(self):
        """Test sentences exactly at min length"""
        parser = SentenceParser(min_sentence_length=10)

        # "Short one." = 10 chars, should not buffer
        sentences = parser.add_chunk("Short one. This is longer.")

        assert len(sentences) == 2

    def test_zero_min_length(self):
        """Test with min_length=0 (no buffering)"""
        parser = SentenceParser(min_sentence_length=0)

        sentences = parser.add_chunk("A. B. C.")

        # "A." and "B." are initials (not sentence boundaries)
        # Only "C." is a true sentence boundary
        assert len(sentences) == 1
        assert "A. B. C." in sentences[0]


class TestEdgeCases:
    """Test edge cases and special scenarios"""

    def test_empty_chunk(self):
        """Test adding empty chunk"""
        parser = SentenceParser(min_sentence_length=5)

        sentences = parser.add_chunk("")
        assert sentences == []

    def test_whitespace_only(self):
        """Test chunk with only whitespace"""
        parser = SentenceParser(min_sentence_length=5)

        sentences = parser.add_chunk("   \n\t  ")
        assert sentences == []

    def test_no_punctuation(self):
        """Test chunk with no sentence-ending punctuation"""
        parser = SentenceParser(min_sentence_length=5)

        sentences = parser.add_chunk("Hello world")
        assert sentences == []

        # Should return via finalize
        remaining = parser.finalize()
        assert remaining == "Hello world"

    def test_reset(self):
        """Test reset() clears state"""
        parser = SentenceParser(min_sentence_length=5)

        parser.add_chunk("Hello world")
        parser.reset()

        remaining = parser.finalize()
        assert remaining == ""

    def test_mixed_whitespace(self):
        """Test sentences with various whitespace"""
        parser = SentenceParser(min_sentence_length=5)

        sentences = parser.add_chunk("Hello!  \n  How are you?\t\tGood.")

        assert len(sentences) == 3


class TestRealWorldExamples:
    """Test real-world LLM response patterns"""

    def test_conversational_response(self):
        """Test typical conversational AI response"""
        parser = SentenceParser(min_sentence_length=10)

        text = "That's a great question! I'd be happy to help. Let me explain."
        sentences = parser.add_chunk(text)

        assert len(sentences) == 3

    def test_technical_explanation(self):
        """Test technical explanation with numbers and abbreviations"""
        parser = SentenceParser(min_sentence_length=10)

        text = "The value of π is approximately 3.14. Dr. Smith proved this, i.e., mathematically."
        sentences = parser.add_chunk(text)

        assert len(sentences) == 2
        assert "3.14" in sentences[0]
        assert "i.e." in sentences[1]

    def test_streamed_chunks(self):
        """Test incremental streaming chunks (simulating LLM)"""
        parser = SentenceParser(min_sentence_length=10)

        all_sentences = []

        # Simulate LLM streaming
        chunks = [
            "Hello! ",
            "How can I ",
            "help you today? ",
            "I'm here to ",
            "assist."
        ]

        for chunk in chunks:
            sentences = parser.add_chunk(chunk)
            all_sentences.extend(sentences)

        # Get final sentence
        final = parser.finalize()
        if final:
            all_sentences.append(final)

        # "Hello!" (6 chars) buffered with next, giving 2 sentences total
        assert len(all_sentences) == 2
        assert "Hello! How can I help you today?" in all_sentences[0]
        assert "I'm here to assist." in all_sentences[1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
