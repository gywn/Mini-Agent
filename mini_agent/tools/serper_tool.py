"""Serper Search Tool - Provides web search capability for the agent.

This tool integrates with Serper's Google Search API to provide web search functionality.

Usage:
    Set SERPER_API_KEY environment variable to your API key.
    The agent can then use this tool to search the web for current information.
"""

import os
from typing import Any

import requests

from .base import Tool, ToolResult


class SerperTool(Tool):
    """Web search tool using Serper API.

    This tool provides Google search results for the agent, enabling access to
    current information on the web.

    Example usage by agent:
    - search("latest AI developments 2024")
    - search("Python async tutorial", num_results=5)
    - search("news about technology", search_type="news")
    - search("tutorial", page=2)  # Get second page of results
    - search("python", num_results=10, page=3)  # Get 3rd page with 10 results
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://google.serper.dev",
    ):
        """Initialize Serper search tool.

        Args:
            api_key: Serper API key. If not provided, will read from SERPER_API_KEY env var.
            base_url: Serper API base URL.
        """
        self._api_key = api_key or os.environ.get("SERPER_API_KEY")
        if not self._api_key:
            raise ValueError("Serper API key is required. Set SERPER_API_KEY environment variable or pass api_key parameter. Get your API key at: https://serper.dev")
        self._base_url = base_url

    @property
    def name(self) -> str:
        return "google_search"

    @property
    def description(self) -> str:
        return (
            "Search the web using Google search engine. Returns title, snippet, and link for each result.\n\n"
            "CRITICAL - Pagination: The first search only returns 10 results. For detailed research, "
            "comparison tasks, or finding specific information, YOU MUST use the 'page' parameter "
            "(e.g., page=2, page=3) to retrieve additional pages. Never assume the first 10 results "
            "contain all relevant information.\n\n"
            "CRITICAL - Full content: The search snippet is often misleading for comparison tasks. "
            "After identifying relevant results, use 'fetch_html' to download the full webpage content. "
            "Never rely on snippets alone for accurate or detailed information."  # fmt: skip
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string. Be specific and use quotes for exact phrases.",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return per page (default: 10, max: 10)",
                    "default": 10,
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination. Each page returns up to num_results. Use page 1 for first results, page 2 for next set, etc. (default: 1)",
                    "default": 1,
                },
                "search_type": {
                    "type": "string",
                    "description": "Type of search: 'search' (web) or 'news'",
                    "default": "search",
                    "enum": ["search", "news"],
                },
                "language": {
                    "type": "string",
                    "description": "Language code for search results (e.g., 'en', 'zh-cn', 'ja')",
                    "default": "en",
                },
                "country": {
                    "type": "string",
                    "description": "Country code for search results (e.g., 'us', 'cn', 'jp')",
                    "default": "us",
                },
            },
            "required": ["query"],
        }

    def _build_url(self, search_type: str) -> str:
        """Build the appropriate Serper API endpoint URL."""
        endpoints = {
            "search": "/search",
            "news": "/news",
        }
        return f"{self._base_url}{endpoints.get(search_type, '/search')}"

    def _build_payload(
        self,
        query: str,
        num_results: int,
        page: int,
        language: str,
        country: str,
        search_type: str,
    ) -> dict[str, Any]:
        """Build the request payload."""
        payload = {
            "q": query,
            "num": min(num_results, 10),  # Max 10 results per page
            "page": max(1, page),  # Page number (min 1)
        }

        # Add language and country for web search
        if search_type == "search":
            payload["hl"] = language
            payload["gl"] = country

        return payload

    def _format_results(self, data: dict[str, Any], search_type: str, page: int = 1) -> str:
        """Format search results into a readable string."""
        if search_type == "search":
            return self._format_web_results(data)
        elif search_type == "news":
            return self._format_news_results(data)
        return str(data)

    def _format_web_results(self, data: dict[str, Any]) -> str:
        """Format web search results."""

        formatted = []
        # Add knowledge graph if available
        if knowledge := data.get("knowledgeGraph"):
            kg_title = knowledge.get("title", "No title")
            kg_desc = knowledge.get("description", "")
            kg_attributes = knowledge.get("attributes", {})
            if kg_title or kg_desc or kg_attributes:
                formatted.append(f"\nKnowledge Graph: {kg_title}")
                if kg_desc:
                    formatted.append(f"   {kg_desc}")
                if kg_attributes:
                    formatted.append(f"   Attributes:")
                    for key, value in kg_attributes.items():
                        formatted.append(f"     - {key}: {value}")

        for i, result in enumerate(data.get("organic", []), 1):
            title = result.get("title", "No title")
            link = result.get("link", "No link")
            snippet = result.get("snippet", "No snippet")

            formatted.append(f"\n{i}. {title}")
            formatted.append(f"   URL: {link}")
            formatted.append(f"   {snippet}")

            # Add attributes if available
            if attributes := result.get("attributes"):
                formatted.append(f"   Attributes:")
                for key, value in attributes.items():
                    formatted.append(f"     - {key}: {value}")

            # Add sitelinks if available
            if sitelinks := result.get("sitelinks"):
                formatted.append(f"   Sitelinks:")
                for sitelink in sitelinks:
                    sl_title = sitelink.get("title", "No title")
                    sl_link = sitelink.get("link", "No link")
                    sl_snippet = sitelink.get("snippet", "No snippet")
                    if sl_title and sl_link:
                        formatted.append(f"     - {sl_title}")
                        formatted.append(f"       URL: {sl_link}")
                        if sl_snippet:
                            formatted.append(f"       {sl_snippet}")

        # Add pagination info if available
        if search_info := data.get("searchInformation"):
            total_results = search_info.get("totalResults", "")
            if total_results:
                formatted.append(f"\nTotal results: {total_results}")

        return "\n".join(formatted).strip()

    def _format_news_results(self, data: dict[str, Any], page: int = 1) -> str:
        """Format news search results."""
        formatted = []
        for i, result in enumerate(data.get("news", []), 1):
            title = result.get("title", "No title")
            link = result.get("link", "No link")
            snippet = result.get("snippet", "No snippet")
            date = result.get("date", "Unknown date")
            source = result.get("source", "Unknown source")

            formatted.append(f"\n{i}. {title}")
            formatted.append(f"   Source: {source} | Date: {date}")
            formatted.append(f"   URL: {link}")
            formatted.append(f"   {snippet}")

        return "\n".join(formatted).strip()

    async def execute(
        self,
        query: str,
        num_results: int = 10,
        page: int = 1,
        search_type: str = "search",
        language: str = "en",
        country: str = "us",
    ) -> ToolResult:
        """Execute a web search using Serper API.

        Args:
            query: The search query string.
            num_results: Number of results to return per page (max 10).
            page: Page number for pagination. Use higher page numbers to get more results.
            search_type: Type of search - 'search' or 'news'.
            language: Language code for results (e.g., 'en', 'zh-cn').
            country: Country code for results (e.g., 'us', 'cn').

        Returns:
            ToolResult with search results or error message.
        """
        try:
            url = self._build_url(search_type)
            payload = self._build_payload(query, num_results, page, language, country, search_type)

            headers = {
                "X-API-KEY": self._api_key,
                "Content-Type": "application/json",
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 200:
                data = response.json()
                formatted_results = self._format_results(data, search_type, page)

                return ToolResult(
                    success=True,
                    content=formatted_results,
                )
            elif response.status_code == 401:
                return ToolResult(
                    success=False,
                    content="",
                    error="Invalid API key. Please check your Serper API key.",
                )
            elif response.status_code == 402:
                return ToolResult(
                    success=False,
                    content="",
                    error="Insufficient credits. Please check your Serper account balance.",
                )
            elif response.status_code == 429:
                return ToolResult(
                    success=False,
                    content="",
                    error="Rate limit exceeded. Please try again later.",
                )
            else:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Search failed with status {response.status_code}: {response.text}",
                )

        except requests.exceptions.Timeout:
            return ToolResult(
                success=False,
                content="",
                error="Search request timed out. Please try again.",
            )
        except requests.exceptions.RequestException as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Network error during search: {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Unexpected error during search: {str(e)}",
            )
