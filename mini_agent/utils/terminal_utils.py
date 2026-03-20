"""Terminal display utilities for proper text alignment.

This module provides utilities for calculating visible width of text in terminals,
handling ANSI escape codes, emoji, and East Asian characters correctly.
"""

import re
import unicodedata

import tiktoken

# Compile regex once at module level for performance
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

# Unicode ranges for emoji
EMOJI_START = 0x1F300
EMOJI_END = 0x1FAFF


def calculate_display_width(text: str) -> int:
    """Calculate the visible width of text in terminal columns.

    This function correctly handles:
    - ANSI escape codes (removed from width calculation)
    - Emoji characters (counted as 2 columns)
    - East Asian Wide/Fullwidth characters (counted as 2 columns)
    - Combining characters (counted as 0 columns)
    - Regular ASCII characters (counted as 1 column)

    Args:
        text: Input text that may contain ANSI codes, emoji, or unicode characters

    Returns:
        Number of terminal columns the text will occupy when displayed

    Examples:
        >>> calculate_display_width("Hello")
        5
        >>> calculate_display_width("你好")
        4
        >>> calculate_display_width("🤖")
        2
        >>> calculate_display_width("\033[31mRed\033[0m")
        3
    """
    # Remove ANSI escape codes (they don't occupy display space)
    clean_text = ANSI_ESCAPE_RE.sub("", text)

    width = 0
    for char in clean_text:
        # Skip combining characters (zero width)
        if unicodedata.combining(char):
            continue

        code_point = ord(char)

        # Emoji range (most common emoji, counted as 2 columns)
        if EMOJI_START <= code_point <= EMOJI_END:
            width += 2
            continue

        # East Asian Width property
        # W = Wide, F = Fullwidth (both occupy 2 columns)
        eaw = unicodedata.east_asian_width(char)
        if eaw in ("W", "F"):
            width += 2
        else:
            width += 1

    return width


def truncate_text_by_tokens(
    text: str,
    max_tokens: int,
    offset: int | None = 1,
    truncation_indicator: str = "[…]",
) -> str:
    """Truncate text by token count if it exceeds the limit.

    This function implements a line-wise truncation strategy:
    - Each line is checked individually against a per-line token limit
    - Lines that exceed the limit are truncated with a truncation indicator
    - Line numbers are added to help locate content in the original file

    The algorithm uses binary search to find the optimal tokens-per-line limit
    that keeps the total output within max_tokens while preserving as much
    content as possible.

    Args:
        text: Text to be truncated (may contain multiple lines)
        max_tokens: Maximum total tokens allowed in the output (including
            line numbers and truncation indicators)
        offset: Starting line number for numbering (default: 1). Useful when
            reading a file segment, so line numbers reflect original positions.
        truncation_indicator: String appended to truncated lines to indicate
            that content was removed (default: "[…]")

    Returns:
        str: Formatted text with line numbers. Lines exceeding the computed
            limit are truncated with the truncation indicator appended.

    Example:
        >>> text = "short\n" + "word " * 100 + "\nshort"
        >>> result = truncate_text_by_tokens(text, max_tokens=50)
        >>> print(result)
             1│short
             2│word word word […]
             3│short
    """
    # Initialize tokenizer (cl100k_base is efficient and commonly used)
    encoding = tiktoken.get_encoding("cl100k_base")

    # Pre-calculate token overhead for line numbers and truncation indicator
    # This accounts for the fixed-width formatting that will be added to each line
    # When offset is None, line numbers are omitted entirely
    tokens_per_line_number = 0 if offset is None else len(encoding.encode(f"{128:6d}│"))
    tokens_per_indicator = len(encoding.encode(truncation_indicator))

    # Token cache to avoid re-encoding the same lines during binary search
    # Each entry is the tokenized form of a line from the input text
    token_cache: list[list[int]] = []

    def _format_with_limit(max_tokens_per_line: int) -> tuple[int, str]:
        """Format all lines with the given per-line token limit.

        This is an inner function used during binary search to test different
        token limits and find the optimal one.

        Args:
            max_tokens_per_line: Maximum tokens allowed for each line (including
                the line number and truncation indicator overhead)

        Returns:
            Tuple of (total_tokens, formatted_content)
        """
        content = ""
        for line_idx, line in enumerate(text.splitlines()):
            # Use cached tokenized line if available, otherwise encode and cache
            if line_idx < len(token_cache):
                line_tokens = token_cache[line_idx]
            else:
                line_tokens = encoding.encode(line)
                token_cache.append(line_tokens)

            # Add line number prefix (e.g., "     1│") when offset is provided
            # When offset is None, line numbers are omitted entirely (for bash output)
            if offset is not None:
                line_number = line_idx + offset
                content += f"{line_number:6d}│"

            # Check if line fits within the token limit
            available_tokens = max_tokens_per_line - tokens_per_line_number
            if len(line_tokens) <= available_tokens:
                # Line fits completely - add full content
                content += line
            else:
                # Line needs truncation - keep what fits and add indicator
                truncated_tokens = line_tokens[: max(0, available_tokens - tokens_per_indicator)]
                content += encoding.decode(truncated_tokens) + truncation_indicator

            content += "\n"

        # Return total token count and the formatted content
        return len(encoding.encode(content)), content

    # Binary search to find the optimal max_tokens_per_line
    #
    # We start with two bounds:
    # - lower: 0 tokens per line (everything gets truncated to just the line number and the indicator)
    # - upper: max_tokens (hopefully everything fits)
    #
    # The loop narrows these bounds until we find the upperest per-line limit
    # that keeps total output within max_tokens.

    # First, check if everything fits with the generous upper bound
    upper_tokens, upper_content = _format_with_limit(upper_n := max_tokens)
    if upper_tokens <= max_tokens:
        # Perfect! Everything fits, return as-is
        return upper_content

    # Check edge case: even with 0 tokens per line, do we exceed?
    # (This can happen if there are many lines with just line numbers)
    lower_tokens, lower_content = _format_with_limit(lower_n := 0)
    if lower_tokens > max_tokens:
        # Even minimal output exceeds limit - return the most truncated version
        return lower_content

    # Binary search: narrow the bounds until they're adjacent
    while upper_n > lower_n + 1:
        mid_n = (lower_n + upper_n) // 2
        mid_tokens, mid_content = _format_with_limit(mid_n)

        if mid_tokens > max_tokens:
            # Still too many tokens - need to reduce per-line limit
            upper_n, upper_tokens, upper_content = mid_n, mid_tokens, mid_content
        else:
            # Fits within limit - try to increase per-line limit
            lower_n, lower_tokens, lower_content = mid_n, mid_tokens, mid_content

    # Return the best result found (the upperer limit that still fit)
    return lower_content
