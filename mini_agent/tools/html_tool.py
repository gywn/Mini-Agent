"""HTML Tool - Download and extract text from web pages.

This tool helps the Agent by:
- Downloading HTML from the Internet (no images/video)
- Using html2text to extract textual content
- Converting HTML to Markdown format for better readability
- Being robust against malformed HTML
- Replacing HTML entities with Unicode characters for proper text rendering
- Providing clean text content to avoid waste tokens

Usage:
    The agent can use this tool to fetch the text content of any web page.
    Useful for reading articles, documentation, or any HTML content.

Configuration:
    HTML tool is controlled by the `enable_html` setting in config.yaml:

    ```yaml
    tools:
      enable_html: true  # Set to true to enable the HTML fetch tool
      html:
        max_tokens: 16000  # Maximum length of extracted text in tokens
    ```

Tool Name (for LLM):
    - name: "fetch_html"
    - The agent calls this tool using fetch_html(url="...")

Example:
    Agent can use this tool to:
    - fetch("https://example.com/article")
    - fetch("https://docs.python.org/3/")
    - fetch("https://news.example.com/story")
"""

import html
import html.parser
import re
from typing import Any
from urllib.parse import urlparse

import requests
import tiktoken
from html2text import HTML2Text
from w3lib.encoding import html_to_unicode
from w3lib.html import replace_entities

from ..utils import truncate_text_by_tokens
from .base import Tool, ToolResult


def is_valid_url(url: str) -> bool:
    """Validate URL format."""
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False


def extract_title(html_str: str) -> str:
    """Extract page title from HTML content using html.parser."""

    class TitleExtractor(html.parser.HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.title: str | None = None
            self.in_title = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "title":
                self.in_title = True

        def handle_endtag(self, tag: str) -> None:
            if tag == "title":
                self.in_title = False

        def handle_data(self, data: str) -> None:
            if self.in_title and self.title is None:
                self.title = data

    try:
        parser = TitleExtractor()
        parser.feed(html_str)

        if parser.title:
            return html.unescape(parser.title).strip()

        return "No title"
    except Exception:
        return "No title"


class HtmlTool(Tool):
    """Tool to download and extract text from HTML pages."""

    def __init__(
        self,
        timeout: int = 30,
        user_agent: str = "Mini-Agent/1.0 (HTML Text Extractor)",
        max_tokens: int = 16000,
    ):
        """Initialize HTML tool.

        Args:
            timeout: Request timeout in seconds
            user_agent: User agent string for HTTP requests
            max_tokens: Maximum length of extracted text in tokens.
        """
        self._timeout = timeout
        self._user_agent = user_agent
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return "fetch_html"

    @property
    def description(self) -> str:
        return (
            "Downloads the HTML from the given URL and extracts readable text and links, "
            "filtering out HTML tags, scripts, styles, and other non-content elements. "
            "The output uses reference-style links (e.g., [text][1]) with the full URLs listed at the end of each paragraph. "
            "CRITICAL - Always consider whether visiting linked pages would provide valuable additional context."  # fmt: skip
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the web page to fetch. Must be a valid HTTP/HTTPS URL.",
                },
            },
            "required": ["url"],
        }

    def _fetch_page(self, url: str) -> tuple[str, str]:
        """Fetch and parse HTML page."""
        try:
            headers = {
                "User-Agent": self._user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }

            response = requests.get(url, headers=headers, timeout=self._timeout, allow_redirects=True)

            if response.status_code == 200:
                # Get Content-Type header for encoding detection
                content_type = response.headers.get("Content-Type")
                # Use w3lib for proper encoding detection (BOM → HTTP header → meta tags → fallback)
                _, html_str = html_to_unicode(content_type, response.content)
                html_str = replace_entities(html_str)
                return html_str, ""
            elif response.status_code == 404:
                return "", f"Page not found (404): {url}"
            elif response.status_code == 403:
                return "", f"Access forbidden (403): {url}. The site may be blocking automated access."
            elif response.status_code == 429:
                return "", f"Rate limited (429): Too many requests. Please try again later."
            else:
                return "", f"HTTP error {response.status_code}: {url}"

        except requests.exceptions.Timeout:
            return "", f"Request timed out after {self._timeout} seconds: {url}"
        except requests.exceptions.ConnectionError as e:
            return "", f"Connection error: {url}. Error: {str(e)}"
        except requests.exceptions.RequestException as e:
            return "", f"Request error: {str(e)}"
        except Exception as e:
            return "", f"Unexpected error: {str(e)}"

    def _format_page_content(self, html_str: str) -> tuple[str, bool]:
        """Convert HTML to markdown-formatted text with token-aware processing.

        Args:
            html_str: HTML content as string (already decoded)

        Returns:
            Tuple of (converted text, was_truncated flag)
        """
        html2text = HTML2Text()
        html2text.body_width = 0  # No line wrapping
        html2text.ignore_links = False  # Include links in output
        html2text.inline_links = False  # Use reference-style links [text][1] instead of inline [text](url)
        html2text.links_each_paragraph = True  # Put the links after each paragraph instead of at the end.
        html2text.ignore_images = True  # Skip images entirely
        html2text.unicode_snob = True  # Use Unicode characters instead of their ascii pseudo-replacements

        text = html2text.handle(html_str)

        # Check token count and retry without links if exceeding limit
        if len(tiktoken.get_encoding("cl100k_base").encode(text)) > self._max_tokens:
            html2text.ignore_links = True
            text = html2text.handle(html_str)

        text = re.sub(r" +$", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # The main truncation to fit the content into the context window
        truncated = truncate_text_by_tokens(text, offset=None, max_tokens=self._max_tokens)

        return truncated, truncated != text

    async def execute(self, url: str) -> ToolResult:
        """Fetch and extract text from an HTML page."""
        if not is_valid_url(url):
            return ToolResult(
                success=False,
                content="",
                error=f"Invalid URL: {url}. Please provide a valid HTTP/HTTPS URL.",
            )

        html_str, error = self._fetch_page(url)

        if error:
            return ToolResult(
                success=False,
                content="",
                error=error,
            )

        content, is_truncated = self._format_page_content(html_str)
        content = "\n".join(
            [
                f"Title: {extract_title(html_str)}",
                f"URL: {url}",
                (
                    (
                        "\nNote: The content is truncated. "
                        "Use `curl` to download the page, then install required packages with PIP (e.g., beautifulsoup4, html5lib) "
                        "and parse it locally with Python.\n"  # fmt: skip
                    )
                    if is_truncated
                    else ""
                ),
                "Content:",
                content,
            ]
        )

        return ToolResult(
            success=True,
            content=content,
        )
