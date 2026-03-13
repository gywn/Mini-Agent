"""HTML Tool - Download and extract text from web pages.

This tool helps the Agent by:
- Downloading HTML from the Internet (no images/video)
- Using curl_cffi for browser simulation (Firefox TLS fingerprint)
- Using html2text to extract textual content
- Converting HTML to Markdown format for better readability
- Being robust against malformed HTML
- Providing clean text content to avoid waste tokens
- Using Firefox cookies for authenticated requests (when profile provided)

Usage:
    The agent can use this tool to fetch the text content of any web page.
    Useful for reading articles, documentation, or any HTML content.

Configuration:
    HTML tool is controlled by the `enable_html` setting in config.yaml:

    ```yaml
    tools:
      enable_html: true  # Set to true to enable the HTML fetch tool
      html:
        max_length: 40000  # Maximum length of extracted text in characters
    ```

    Or via CLI:
        mini-agent --firefox-profile /path/to/profile

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
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import curl_cffi
import curl_cffi.requests.exceptions as curl_exceptions
import html2text

from ..utils import read_firefox_cookies
from .base import Tool, ToolResult


def is_valid_url(url: str) -> bool:
    """Validate URL format."""
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False


def clean_text(text: str) -> str:
    """Clean and normalize extracted text."""
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def truncate_text(text: str, max_length: int) -> str:
    """Truncate text to max length, respecting word boundaries."""
    if len(text) <= max_length:
        return text

    truncated = text[:max_length]
    last_space = truncated.rfind(" ")

    if last_space > max_length * 0.8:
        truncated = truncated[:last_space]

    return truncated + "... [truncated]"


def extract_title(html_content: bytes) -> str:
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
        html_str = html_content.decode("utf-8", errors="ignore")
        parser = TitleExtractor()
        parser.feed(html_str)

        if parser.title:
            return clean_text(parser.title)

        return "No title"
    except Exception:
        return "No title"


class HtmlTool(Tool):
    """Tool to download and extract text from HTML pages."""

    def __init__(
        self,
        timeout: int = 30,
        max_length: int = 40000,
        firefox_profile: Path | None = None,
    ):
        """Initialize HTML tool.

        Args:
            timeout: Request timeout in seconds
            max_length: Maximum length of extracted text in characters.
            firefox_profile: Optional path to Firefox profile directory for cookie support.
        """
        self._timeout = timeout
        self._max_length = max_length
        self._firefox_profile = firefox_profile.expanduser().absolute() if firefox_profile is not None else None
        self._session: curl_cffi.Session | None = None

        self._html2text = html2text.HTML2Text()
        self._html2text.ignore_links = False  # Include links in output
        self._html2text.inline_links = False  # Use reference-style links [text][1] instead of inline [text](url)
        self._html2text.links_each_paragraph = False  # Put all links at end of document, not after each paragraph
        self._html2text.ignore_images = True  # Skip images entirely
        self._html2text.body_width = 0  # No line wrapping

    @property
    def name(self) -> str:
        return "fetch_html"

    @property
    def description(self) -> str:
        return (
            "Fetch and extract text content from an HTML web page. "
            "Downloads the HTML from the given URL and extracts readable text, "
            "filtering out HTML tags, scripts, styles, and other non-content elements. "
            "Useful for reading articles, documentation, or any web content. "
            "Returns the page title and main text content. Use this to avoid "
            "wasting tokens on raw HTML or non-textual content."  # fmt: skip
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

    def _get_session(self) -> curl_cffi.Session:
        """Get or create a persistent curl_cffi session with cookies.

        Note: curl_cffi uses BoringSSL with embedded TLS fingerprints to impersonate
        browsers. It does NOT require libnss3 or the curl-impersonate binary.
        The impersonation works by crafting TLS Client Hello messages that exactly
        match Firefox's format (cipher suites, extensions, session IDs, etc.).
        """
        if self._session is None:
            # Create new session with Firefox impersonation
            self._session = curl_cffi.Session(impersonate="firefox")
            # Load cookies from Firefox profile if configured
            if self._firefox_profile and (self._firefox_profile / "cookies.sqlite").is_file():
                self._session.cookies = read_firefox_cookies(self._firefox_profile)

        return self._session

    def _fetch_page(self, url: str) -> tuple[str, str, str]:
        """Fetch and parse HTML page."""
        # Get persistent session with cookies
        session = self._get_session()

        try:
            # Only accept HTML content types since HtmlTool uses html2text
            # This prevents servers from returning JSON or other unexpected types
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            }
            response = session.get(url, headers=headers, timeout=self._timeout, allow_redirects=True)

            if response.status_code == 200:
                html_content = response.content
                title = extract_title(html_content)
                html_str = html_content.decode("utf-8", errors="ignore")
                text = self._html2text.handle(html_str)
                text = clean_text(text)

                return title, text, ""
            elif response.status_code == 404:
                return "", "", f"Page not found (404): {url}"
            elif response.status_code == 403:
                return "", "", f"Access forbidden (403): {url}. The site may be blocking automated access."
            elif response.status_code == 429:
                return "", "", f"Rate limited (429): Too many requests. Please try again later."
            else:
                return "", "", f"HTTP error {response.status_code}: {url}"

        except curl_exceptions.Timeout:
            return "", "", f"Request timed out after {self._timeout} seconds: {url}"
        except curl_exceptions.ConnectionError as e:
            return "", "", f"Connection error: {url}. Error: {str(e)}"
        except curl_exceptions.HTTPError as e:
            return "", "", f"HTTP error: {str(e)}"
        except curl_exceptions.RequestException as e:
            return "", "", f"Request error: {str(e)}"
        except Exception as e:
            return "", "", f"Unexpected error: {str(e)}"

    async def execute(self, url: str) -> ToolResult:
        """Fetch and extract text from an HTML page."""
        if not is_valid_url(url):
            return ToolResult(
                success=False,
                content="",
                error=f"Invalid URL: {url}. Please provide a valid HTTP/HTTPS URL.",
            )

        title, text, error = self._fetch_page(url)

        if error:
            return ToolResult(
                success=False,
                content="",
                error=error,
            )

        original_length = len(text)
        if original_length > self._max_length:
            text = text[: self._max_length]
            is_truncated = True
        else:
            is_truncated = False

        return ToolResult(
            success=True,
            content="\n".join(
                [
                    f"Title: {title}",
                    f"URL: {url}",
                    f"Truncated: {f'Yes (original length {original_length})' if is_truncated else 'No'}",
                    "",
                    "Content:",
                    text,
                ]
            ),
        )
