# Mini Agent Architecture Guide

This document provides a **code-centric reference** for understanding the Mini Agent project structure. It focuses on **what each file does** and **how components relate**, complementing the README.md which covers features and usage.

> **For features, usage, and quick start → See [README.md](../README.md)**

---

## Table of Contents

1. [Project Structure Overview](#project-structure-overview)
2. [Core Python Files Reference](#core-python-files-reference)
   - [Entry Points](#entry-points)
   - [Agent Core](#agent-core)
   - [LLM Clients](#llm-clients)
   - [Tools System](#tools-system)
   - [Schema & Data Models](#schema--data-models)
   - [Utilities](#utilities)
   - [Configuration](#configuration)
3. [Component Relationships](#component-relationships)
4. [Data Flow](#data-flow)
5. [Tool System Details](#tool-system-details)
6. [LLM Provider Implementation](#llm-provider-implementation)
7. [Event-Based Architecture](#event-based-architecture)
8. [Containerization](#containerization)

---

## Project Structure Overview

```
mini_agent/                          # Main package
├── __init__.py                      # Package exports (Agent, LLMClient, schema classes)
├── agent.py                         # Core Agent class
├── cli.py                          # CLI entry point
├── config.py                       # Configuration management
├── logger.py                       # Execution logging
├── retry.py                        # Retry mechanism
├── session.py                      # Session persistence & resumption
│
├── llm/                            # LLM client implementations
│   ├── __init__.py
│   ├── base.py                     # Abstract base class for LLM clients
│   ├── anthropic_client.py         # Anthropic protocol implementation
│   ├── openai_client.py            # OpenAI protocol implementation
│   └── llm_wrapper.py              # Unified facade (supports multiple providers)
│
├── schema/                         # Data models
│   ├── __init__.py
│   └── schema.py                   # Message, LLMResponse, ToolCall, etc.
│
├── tools/                          # Tool implementations
│   ├── __init__.py
│   ├── base.py                     # Tool abstract class, ToolResult
│   ├── file_tools.py               # ReadTool, WriteTool, EditTool
│   ├── bash_tool.py                # BashTool, BashOutputTool, BashKillTool
│   ├── note_tool.py                # SessionNoteTool, RecallNoteTool
│   ├── html_tool.py                # HtmlTool (web fetch)
│   ├── serper_tool.py              # SerperTool (web search)
│   ├── mcp_loader.py               # MCP tool integration
│   ├── skill_loader.py             # Claude Skills loader
│   └── skill_tool.py               # Skill execution tool
│
└── utils/                          # Utility functions
    ├── __init__.py
    └── terminal_utils.py           # Terminal display formatting
```

---

## Core Python Files Reference

### Entry Points

| File | Description |
|------|-------------|
| **`cli.py`** | CLI interface. Contains `main()` entry point, argument parsing (`parse_args()`), interactive prompt setup using `prompt_toolkit`, command handlers (`/help`, `/clear`, `/log`, etc.), Esc key cancellation listener. Calls `run_agent()` to start execution. |
| **`__init__.py`** | Package exports. Re-exports `Agent`, `LLMClient`, and all schema classes (`Message`, `LLMResponse`, `ToolCall`, `FunctionCall`, `LLMProvider`). |

---

### Agent Core

| File | Description |
|------|-------------|
| **`agent.py`** | **Main Agent class** - Orchestrates the think→act loop. Key responsibilities: <br>• Maintains message history (`self.messages`) <br>• `run()` - **Async generator** that yields events (messages, tool calls, tool results, status) <br>• Tool execution with error handling <br>• Token management with automatic summarization (`_summarize_messages()`) <br>• Cancellation support via `asyncio.Event` <br>• Logging via `AgentLogger` <br><br>Key classes: `Agent`, `Colors` (ANSI terminal colors) |

---

### LLM Clients

| File | Description |
|------|-------------|
| **`llm/base.py`** | Abstract base class `LLMClientBase`. Defines interface: `generate()`, `_prepare_request()`, `_convert_messages()`. All LLM clients inherit from this. |
| **`llm/anthropic_client.py`** | `AnthropicClient` - Implements Anthropic API protocol. Uses official `anthropic` SDK. Supports extended thinking, tool calling. Key methods: `_make_api_request()`, `_convert_tools()`, `_convert_messages()`, `_parse_response()`. |
| **`llm/openai_client.py`** | `OpenAIClient` - Implements OpenAI API protocol. Uses official `openai` SDK with `AsyncOpenAI`. Supports reasoning content via `reasoning_split`. Key methods mirror `AnthropicClient`. |
| **`llm/llm_wrapper.py`** | `LLMClient` - **Facade pattern** that wraps provider-specific clients. Automatically selects `AnthropicClient` or `OpenAIClient` based on `LLMProvider` enum. Handles API base URL normalization for MiniMax endpoints. |

---

### Tools System

| File | Description |
|------|-------------|
| **`tools/base.py`** | Base classes: `Tool` (abstract), `ToolResult`. All tools inherit from `Tool` and implement: `name`, `description`, `parameters`, `execute()`. Also provides `to_schema()` and `to_openai_schema()` for API format conversion. |
| **`tools/file_tools.py`** | File operation tools: <br>• `ReadTool` (`read_file`) - Read files with line numbers, offset/limit support, token truncation <br>• `WriteTool` (`write_file`) - Write files, auto-create directories <br>• `EditTool` (`edit_file`) - String replacement (old_str → new_str) <br><br>Helper: `truncate_text_by_tokens()` for large file handling. |
| **`tools/bash_tool.py`** | Shell command execution: <br>• `BashTool` (`bash`) - Execute commands, supports foreground/background modes, cross-platform (bash/PowerShell) <br>• `BashOutputTool` (`bash_output`) - Monitor background process output <br>• `BashKillTool` (`bash_kill`) - Terminate background processes <br><br>Helper classes: `BackgroundShell`, `BackgroundShellManager`, `BashOutputResult` |
| **`tools/note_tool.py`** | Persistent memory tools: <br>• `SessionNoteTool` (`record_note`) - Record notes to JSON file <br>• `RecallNoteTool` (`recall_notes`) - Retrieve recorded notes <br><br>Storage: `.agent_memory.json` in workspace. |
| **`tools/html_tool.py`** | `HtmlTool` (`fetch_html`) - Fetch and extract text from web pages. |
| **`tools/serper_tool.py`** | `SerperTool` - Google search via Serper API. |
| **`tools/mcp_loader.py`** | MCP (Model Context Protocol) integration: <br>• `MCPTool` - Wrapper for MCP server tools with timeout <br>• `MCPServerConnection` - Manages connection to MCP server (supports stdio, sse, http, streamable_http) <br>• `load_mcp_tools_async()` - Load tools from MCP config file <br>• `cleanup_mcp_connections()` - Cleanup on exit |
| **`tools/skill_loader.py`** | Claude Skills loader: <br>• `Skill` - Dataclass for skill data (name, description, content) <br>• `SkillLoader` - Discovers and loads skills from SKILL.md files, processes relative paths to absolute paths |
| **`tools/skill_tool.py`** | Skill execution: <br>• `GetSkillTool` (`get_skill`) - Load full skill content on-demand <br>• `create_skill_tools()` - Factory function to create skill tools |

---

### Schema & Data Models

| File | Description |
|------|-------------|
| **`schema/schema.py`** | Pydantic data models: <br>• `LLMProvider` - Enum: ANTHROPIC, OPENAI <br>• `FunctionCall` - Function name and arguments <br>• `ToolCall` - Tool invocation (id, type, function) <br>• `Message` - Chat message (role, content, thinking, tool_calls) <br>• `TokenUsage` - API token statistics <br>• `LLMResponse` - LLM API response wrapper |

---

### Utilities

| File | Description |
|------|-------------|
| **`utils/terminal_utils.py`** | Terminal display utilities: `format_markdown_with_bat()`, `calculate_display_width()`, `pad_to_width()`, `truncate_with_ellipsis()` |
| **`logger.py`** | `AgentLogger` - Logs complete agent execution: <br>• `start_new_run()` - Create new log file <br>• `log_request()` - Log LLM request <br>• `log_response()` - Log LLM response <br>• `log_tool_result()` - Log tool execution <br><br>Log location: `~/.mini-agent/log/` |

---

### Configuration

| File | Description |
|------|-------------|
| **`config.py`** | Configuration management with Pydantic: <br>• `RetryConfig` - Retry settings (max_retries, delay, exponential backoff) <br>• `LLMConfig` - API key, base URL, model, provider <br>• `AgentConfig` - max_steps, workspace, system_prompt_path <br>• `MCPConfig` - Connection/execution timeouts <br>• `SerperConfig` - Web search settings <br>• `ToolsConfig` - Tool enable/disable flags <br>• `Config` - Main composite config <br><br>Methods: `from_yaml()`, `load()`, `find_config_file()`, `get_default_config_path()` |
| **`retry.py`** | Retry mechanism: <br>• `RetryConfig` - Configuration class <br>• `RetryExhaustedError` - Exception when retries exhausted <br>• `async_retry()` - Decorator for async functions with exponential backoff |
| **`session.py`** | Session persistence for resumption with prefix caching: <br>• `get_session_history_dir()` - Get session directory for workspace <br>• `get_new_session_history()` - Generate unique session file path <br>• `load_session_history()` - Load latest session from `.mini-agent/session/` <br>• `save_session_history()` - Save current session to YAML <br><br>Session files: `.mini-agent/session/session_YYYYMMDD_HHMMSS_ffffff_UTC.yaml` |

---

## Component Relationships

### How Files Connect

```
cli.py (entry point)
    │
    ├─► config.py: Load YAML configuration
    │
    ├─► llm/llm_wrapper.py: Create LLMClient
    │       │
    │       └─► llm/anthropic_client.py OR llm/openai_client.py
    │
    ├─► tools/*: Initialize tools
    │       │
    │       ├─► tools/base.py: Tool abstract class
    │       ├─► tools/file_tools.py: File operations
    │       ├─► tools/bash_tool.py: Shell commands
    │       ├─► tools/note_tool.py: Session memory
    │       ├─► tools/mcp_loader.py: External MCP tools
    │       ├─► tools/skill_loader.py: Claude Skills
    │       └─► tools/skill_tool.py: Skill execution
    │
    └─► agent.py: Create Agent, call run()
            │
            ├─► schema/schema.py: Message, LLMResponse, SessionHistory
            ├─► session.py: Session persistence (load/save)
            ├─► logger.py: Log execution
            ├─► retry.py: LLM call retries
            └─► tools/*: Execute tools via tool.execute()
```

### Initialization Sequence (in `cli.py::run_agent()`)

```
1. Config.from_yaml()           → Load config from YAML
2. LLMClient()                  → Create provider-specific client
3. initialize_base_tools()      → Load workspace-independent tools
   ├─► create_skill_tools()    → Load Claude Skills
   ├─► load_mcp_tools_async()   → Load MCP tools
   └─► HtmlTool, SerperTool
4. add_workspace_tools()        → Load workspace-dependent tools
   ├─► BashTool, BashOutputTool, BashKillTool
   ├─► ReadTool, WriteTool, EditTool
   └─► SessionNoteTool
5. Load system_prompt.md        → Load agent instructions
6. Agent()                      → Create agent instance
   └─► load_session_history()  → Load previous session (if interactive mode)
7. agent.run()                  → Start async generator execution loop
   └─► Consume yielded events in CLI event handler
```

---

## Data Flow

### Agent Execution Loop (in `agent.py::run()`) - Async Generator Pattern

```
1. User Input
   │
2. add_user_message() → Append to self.messages
   │
3. _summarize_messages() → If token_limit exceeded, compress history
   │
4. llm_client.generate(messages, tools) → Call LLM API
   │
5. Parse LLMResponse
   │
   ├─► yield "thinking" → Notify UI that LLM is thinking
   ├─► yield AssistantMessage → Return response to caller
   └─► No tool_calls? → Save session, DONE
   │
6. For each tool_call:
   │
   ├─► yield ToolCall → Notify UI of tool invocation
   ├─► tool = self.tools[function_name]
   ├─► result = await tool.execute(**arguments)
   ├─► yield ToolResultMessage → Return result to caller
   └─► Append to self.messages → Save session, DONE
   │
7. Repeat from step 3
```

### Tool Execution Flow

```
Agent.run()
    │
    ▼
For tool_call in response.tool_calls:
    │
    ▼
yield ToolCall(name, arguments)  → Notify caller of tool invocation
    │
    ▼
tool = self.tools[function_name]
    │
    ▼
result = await tool.execute(**arguments)
    │
    ├─► Success: result = ToolResult(success=True, content=...)
    └─► Failure: result = ToolResult(success=False, error=...)
    │
    ▼
yield ToolResultMessage(content/error)  → Return result to caller
    │
    ▼
self.messages.append(tool_msg)
    │
    ▼
save_session_history()  → Persist session state
```

---

## Tool System Details

### Tool Interface (all tools implement)

```python
class Tool:
    @property
    def name(self) -> str: pass          # Tool name (e.g., "read_file")
    
    @property
    def description(self) -> str: pass   # Tool description for LLM
    
    @property
    def parameters(self) -> dict: pass   # JSON Schema
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute tool with provided arguments"""
        ...
    
    def to_schema(self) -> dict:         # Anthropic format
        return {"name": self.name, ...}
    
    def to_openai_schema(self) -> dict:  # OpenAI format
        return {"type": "function", ...}
```

### Tool Categories

| Category | Files | Tools |
|----------|-------|-------|
| **File Operations** | `file_tools.py` | `ReadTool`, `WriteTool`, `EditTool` |
| **Shell Commands** | `bash_tool.py` | `BashTool`, `BashOutputTool`, `BashKillTool` |
| **Memory** | `note_tool.py` | `SessionNoteTool`, `RecallNoteTool` |
| **Web** | `html_tool.py`, `serper_tool.py` | `HtmlTool`, `SerperTool` |
| **External** | `mcp_loader.py` | `MCPTool` (dynamic) |
| **Skills** | `skill_loader.py`, `skill_tool.py` | `GetSkillTool` |

---

## LLM Provider Implementation

The Mini Agent supports multiple LLM providers through a unified client interface:

| Provider | Client File | Protocol |
|----------|-------------|----------|
| Anthropic | `llm/anthropic_client.py` | Anthropic API |
| OpenAI | `llm/openai_client.py` | OpenAI API |

---

## Event-Based Architecture

The Mini Agent uses an **async generator pattern** that decouples agent logic from UI rendering. This enables:
- **UI Agnosticism**: The same event stream can power terminal, web, or custom interfaces
- **Real-time Updates**: Callers receive events as they happen, not after completion
- **Session Resumption**: Events enable faithful replay of previous sessions

### Session Persistence and Replay

Sessions are automatically saved to enable resumption with prefix caching:

- **Storage Location**: `.mini-agent/session/session_YYYYMMDD_HHMMSS_ffffff_UTC.yaml`
- **Saved Data**: Tool schemas + message history
- **Load Condition**: Interactive mode only, and only if system prompt and tools match
- **Replay on Resume**: Previous messages are replayed via `print_messages()` before accepting new input

---

## Containerization

The Mini Agent includes Docker support for containerized execution, providing an isolated environment.

The `Dockerfile` is based on **Debian 13 (trixie) slim**.

The Dockerfile declares a volume at `/project`. At runtime, mount the host's current working directory (or any project directory) to this location to enable file operations and tool execution within the container.

Environment variables can be passed to the container to configure the agent:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude models |
| `OPENAI_API_KEY` | OpenAI API key for GPT models |
