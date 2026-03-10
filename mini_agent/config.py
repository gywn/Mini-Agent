"""Configuration management module

Provides unified configuration loading and management functionality
with support for overlaying multiple YAML config files.
"""

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


def deep_merge(base: Any, override: Any) -> Any:
    """Recursively merge two dictionaries or replace values.

    Used for overlaying multiple YAML config files, where later configs
    override earlier ones. Nested dictionaries are merged recursively.

    Args:
        base: The base dictionary to merge into
        override: The override dictionary - its values take precedence

    Returns:
        Merged dictionary with override values taking precedence
    """
    merged: dict[str, Any] = {}
    if override is None:
        return base
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    for key in set(base.keys()) | set(override.keys()):
        merged[key] = deep_merge(base.get(key), override.get(key))
    return merged


class RetryConfig(BaseModel):
    """Retry configuration"""

    enabled: bool = True
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0


class LLMConfig(BaseModel):
    """LLM configuration"""

    api_key: str
    api_base: str = "https://api.minimax.io"
    model: str = "MiniMax-M2.5"
    provider: Literal["anthropic", "openai"] = "anthropic"  # "anthropic" or "openai"
    retry: RetryConfig = Field(default_factory=RetryConfig)


class AgentConfig(BaseModel):
    """Agent configuration"""

    max_steps: int = 50
    workspace_dir: str = "./workspace"
    system_prompt_path: str = "system_prompt.md"
    editing_mode: Literal["vi", "emacs"] = "emacs"  # "vi" or "emacs" - CLI terminal editing mode


class MCPConfig(BaseModel):
    """MCP (Model Context Protocol) timeout configuration"""

    connect_timeout: float = 10.0  # Connection timeout (seconds)
    execute_timeout: float = 60.0  # Tool execution timeout (seconds)
    sse_read_timeout: float = 120.0  # SSE read timeout (seconds)


class SerperConfig(BaseModel):
    """Serper search tool configuration"""

    enabled: bool = False  # Enable Serper search tool
    api_key: str = ""  # Serper API key (or set via SERPER_API_KEY env var)
    base_url: str = "https://google.serper.dev"


class HtmlConfig(BaseModel):
    """HTML tool configuration"""

    max_length: int = 40000  # Maximum length of extracted text in characters


class ToolsConfig(BaseModel):
    """Tools configuration

    Controls which tools are available to the Agent.

    Tool Categories:
    1. Workspace-independent tools (initialized in initialize_base_tools):
       - HtmlTool (fetch_html): Web page text extraction
       - SerperTool: Web search
       - Skill tools: Claude Skills functionality
       - MCP tools: External MCP server tools

    2. Workspace-dependent tools (initialized in add_workspace_tools):
       - BashTool: Command execution
       - ReadTool/WriteTool/EditTool: File operations
       - SessionNoteTool: Persistent memory
    """

    # Basic tools (file operations, bash)
    enable_file_tools: bool = True
    enable_bash: bool = True
    enable_note: bool = True

    # Serper search tool
    enable_serper: bool = False
    serper: SerperConfig = Field(default_factory=SerperConfig)

    # HTML tool - Web page text extraction (fetch_html)
    # When enabled, the Agent can fetch any URL and extract readable text
    # Useful for reading articles, documentation, or web content
    # Note: Does not extract images/video, only text content
    enable_html: bool = False
    html: HtmlConfig = Field(default_factory=HtmlConfig)

    # Skills
    enable_skills: bool = True
    skills_dir: str = "./skills"

    # MCP tools
    enable_mcp: bool = True
    mcp_config_path: str = "mcp.json"
    mcp: MCPConfig = Field(default_factory=MCPConfig)


class Config(BaseModel):
    """Main configuration class"""

    llm: LLMConfig
    agent: AgentConfig
    tools: ToolsConfig

    @classmethod
    def load(cls, workspace_dir: Path | None = None) -> "Config":
        """Load configuration with automatic overlay/merge support.

        Args:
            workspace_dir: Optional workspace directory to search for workspace-level config

        Raises:
            FileNotFoundError: If no config file is found in any location
        """
        config_paths = cls.find_config_files("config.yaml", workspace_dir)
        if not config_paths:
            raise FileNotFoundError("Configuration file not found. Run scripts/setup-config.sh or place config.yaml in mini_agent/config/.")
        return cls.from_yaml(config_paths)

    @classmethod
    def from_yaml(cls, config_paths: str | Path | list[Path]) -> "Config":
        """Load configuration from YAML file(s) with overlay/merge support.

        When multiple config paths are provided, they are merged together
        with later files taking precedence over earlier ones (deep merge).
        This allows for base configs to be overridden at user/workspace levels.

        Args:
            config_paths: Single path or list of paths to YAML config files.
                          If a list, files are merged with the first path
                          having lowest priority and last path highest priority.

        Returns:
            Config instance

        Raises:
            FileNotFoundError: Configuration file does not exist
            ValueError: Invalid configuration format or missing required fields
        """
        if not isinstance(config_paths, list):
            config_paths = [Path(config_paths)]

        data: dict[str, Any] = {}
        for config_path in reversed(config_paths):
            with open(config_path, encoding="utf-8") as f:
                data = deep_merge(data, yaml.safe_load(f))

        if not data:
            raise ValueError("Configuration file is empty")

        # Parse LLM configuration
        if "api_key" not in data:
            raise ValueError("Configuration file missing required field: api_key")

        if not data["api_key"] or data["api_key"] == "YOUR_API_KEY_HERE":
            if api_key := os.environ.get("MINIMAX_API_KEY", ""):
                data["api_key"] = api_key
            else:
                raise ValueError("Please configure a valid API Key")

        # Parse retry configuration
        retry_data = data.get("retry", {})
        retry_config = RetryConfig(
            enabled=retry_data.get("enabled", True),
            max_retries=retry_data.get("max_retries", 3),
            initial_delay=retry_data.get("initial_delay", 1.0),
            max_delay=retry_data.get("max_delay", 60.0),
            exponential_base=retry_data.get("exponential_base", 2.0),
        )

        llm_config = LLMConfig(
            api_key=data["api_key"],
            api_base=data.get("api_base", "https://api.minimax.io"),
            model=data.get("model", "MiniMax-M2.5"),
            provider=data.get("provider", "anthropic"),
            retry=retry_config,
        )

        # Parse Agent configuration
        agent_config = AgentConfig(
            max_steps=data.get("max_steps", 50),
            workspace_dir=data.get("workspace_dir", "./workspace"),
            system_prompt_path=data.get("system_prompt_path", "system_prompt.md"),
            editing_mode=data.get("editing_mode", "emacs"),
        )

        # Parse tools configuration
        tools_data = data.get("tools", {})

        # Parse MCP configuration
        mcp_data = tools_data.get("mcp", {})
        mcp_config = MCPConfig(
            connect_timeout=mcp_data.get("connect_timeout", 10.0),
            execute_timeout=mcp_data.get("execute_timeout", 60.0),
            sse_read_timeout=mcp_data.get("sse_read_timeout", 120.0),
        )

        # Parse Serper configuration
        serper_data = tools_data.get("serper", {})
        serper_config = SerperConfig(
            enabled=serper_data.get("enabled", False),
            api_key=serper_data.get("api_key", ""),
            base_url=serper_data.get("base_url", "https://google.serper.dev"),
        )

        # Parse HTML tool configuration
        html_data = tools_data.get("html", {})
        html_config = HtmlConfig(
            max_length=html_data.get("max_length", 40000),
        )

        tools_config = ToolsConfig(
            enable_file_tools=tools_data.get("enable_file_tools", True),
            enable_bash=tools_data.get("enable_bash", True),
            enable_note=tools_data.get("enable_note", True),
            enable_serper=tools_data.get("enable_serper", False),
            serper=serper_config,
            enable_html=tools_data.get("enable_html", False),
            html=html_config,
            enable_skills=tools_data.get("enable_skills", True),
            skills_dir=tools_data.get("skills_dir", "./skills"),
            enable_mcp=tools_data.get("enable_mcp", True),
            mcp_config_path=tools_data.get("mcp_config_path", "mcp.json"),
            mcp=mcp_config,
        )

        return cls(
            llm=llm_config,
            agent=agent_config,
            tools=tools_config,
        )

    @staticmethod
    def get_package_dir() -> Path:
        """Get the package installation directory

        Returns:
            Path to the mini_agent package directory
        """
        # Get the directory where this config.py file is located
        return Path(__file__).parent

    @classmethod
    def find_config_files(cls, filename: str, workspace_dir: Path | None = None) -> list[Path]:
        """Find configuration file with priority order

        Search for config file in the following order of priority:
        1) {workspace_dir}/.mini_agent/config/{filename} in the workspace directory
        2) ~/.mini-agent/config/{filename} in user home directory
        3) {package}/mini_agent/config/{filename} in package installation directory

        Args:
            filename: Configuration file name (e.g., "config.yaml", "mcp.json", "system_prompt.md")
            workspace_dir: Optional workspace directory to search for workspace-level config
                          (e.g., .mini_agent/config/config.yaml in the project)

        Returns:
            List of Paths to found config files in priority order (lowest to highest).
            Empty list if no config files found.
        """
        config_paths: list[Path] = []

        # Priority 1: Development mode - current directory's config/ subdirectory
        if workspace_dir is not None:
            workspace_config = workspace_dir / ".mini-agent" / "config" / filename
            if workspace_config.exists():
                config_paths.append(workspace_config)

        # Priority 2: User config directory
        user_config = Path.home() / ".mini-agent" / "config" / filename
        if user_config.exists():
            config_paths.append(user_config)

        # Priority 3: Package installation directory's config/ subdirectory
        package_config = cls.get_package_dir() / "config" / filename
        if package_config.exists():
            config_paths.append(package_config)

        return config_paths
