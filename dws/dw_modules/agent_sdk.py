"""
GitHub Copilot SDK - The SDK Way

This module demonstrates the idiomatic way to use the GitHub Copilot Python SDK
for programmatic agent interactions. It mirrors the Claude Code agent_sdk.py
interface but targets the Copilot SDK underneath.

Key Concepts:
- CopilotClient: async - await client.start() / await client.stop()
- create_session: async - requires on_permission_request handler
- session.send_and_wait(prompt): async - blocks until turn complete
- session.get_messages(): returns all SessionEvent objects
- session.on(handler): register callback for real-time events

Example Usage:
    import asyncio
    from agent_sdk import simple_query

    response = asyncio.run(simple_query("What is 2 + 2?"))
    print(response)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# Import from the Copilot SDK
# pip install github-copilot-sdk  (package name on PyPI)
# import name is "copilot"
from copilot import CopilotClient, CopilotSession
from copilot.session import SessionEvent, SessionEventType

# Set up logging
logger = logging.getLogger(__name__)


# ============================================================================
# DATA TYPES (typed wrappers for presentation-friendly output)
# ============================================================================


@dataclass
class TextContent:
    """Text content block from a Copilot response."""

    text: str
    type: str = "text"


@dataclass
class ToolUseContent:
    """Tool use content block from a Copilot response."""

    name: str
    id: str
    input: Dict[str, Any] = field(default_factory=dict)
    type: str = "tool_use"


@dataclass
class AssistantMessage:
    """Message from the Copilot agent."""

    content: List[Any] = field(default_factory=list)
    type: str = "assistant"


@dataclass
class ResultMessage:
    """Final result message from a Copilot session turn."""

    result: str = ""
    is_error: bool = False
    session_id: str = ""
    duration_ms: int = 0
    num_turns: int = 0
    model: str = ""
    total_cost_usd: float = 0.0
    type: str = "result"


# Type alias
Message = Any  # AssistantMessage | ResultMessage


# ============================================================================
# PERMISSION HANDLERS (required by Copilot SDK for every session)
# ============================================================================


def auto_approve_handler(request) -> bool:
    """Auto-approve all tool permissions for automated workflows."""
    return True


def logging_approve_handler(request) -> bool:
    """Auto-approve but log every permission request for observability."""
    logger.info(f"Permission requested: {getattr(request, 'tool_name', 'unknown')}")
    return True


# ============================================================================
# EVENT PARSING
# ============================================================================


def parse_session_event(event: SessionEvent) -> Optional[Message]:
    """Parse a Copilot SessionEvent into a typed message."""
    event_type = event.type

    if event_type == SessionEventType.ASSISTANT_MESSAGE:
        data = event.data
        content_text = getattr(data, "content", "") if data else ""
        if content_text:
            return AssistantMessage(content=[TextContent(text=content_text)])

    elif event_type == SessionEventType.TOOL_EXECUTION_START:
        data = event.data
        tool_name = getattr(data, "tool_name", "") if data else ""
        tool_id = str(event.id) if event.id else ""
        if tool_name:
            return AssistantMessage(
                content=[ToolUseContent(name=tool_name, id=tool_id)]
            )

    elif event_type == SessionEventType.SESSION_IDLE:
        return ResultMessage(type="result")

    return None


def extract_text(message: AssistantMessage) -> str:
    """Extract all text content from an assistant message."""
    texts = []
    for block in message.content:
        if isinstance(block, TextContent):
            texts.append(block.text)
    return "\n".join(texts)


def extract_tool_uses(message: AssistantMessage) -> List[ToolUseContent]:
    """Extract all tool use blocks from an assistant message."""
    return [b for b in message.content if isinstance(b, ToolUseContent)]


def get_result_text(messages: List[Message]) -> str:
    """Extract final result text from a list of messages."""
    for msg in reversed(messages):
        if isinstance(msg, ResultMessage) and msg.result:
            return msg.result

    texts = []
    for msg in messages:
        if isinstance(msg, AssistantMessage):
            text = extract_text(msg)
            if text:
                texts.append(text)
    return "\n".join(texts)


def _events_to_messages(events: List[SessionEvent]) -> List[Message]:
    """Convert a list of SessionEvents to typed messages, filtering noise."""
    messages = []
    for event in events:
        parsed = parse_session_event(event)
        if parsed is not None:
            messages.append(parsed)
    return messages


# ============================================================================
# ONE-SHOT QUERIES
# ============================================================================


async def simple_query(prompt: str, model: Optional[str] = None) -> str:
    """Simple one-shot query with text response.

    Args:
        prompt: What to ask Copilot
        model: Which model to use (e.g., "gpt-4o", "claude-sonnet-4")

    Returns:
        Text response from Copilot
    """
    client = CopilotClient()
    await client.start()

    try:
        session = await client.create_session(
            on_permission_request=auto_approve_handler,
            model=model,
        )

        await session.send_and_wait(prompt, timeout=120.0)

        all_events = await session.get_messages()
        messages = _events_to_messages(all_events)

        return get_result_text(messages) or "No response"
    finally:
        await client.stop()


async def collect_query_response(
    prompt: str,
    model: Optional[str] = None,
    working_dir: Optional[str] = None,
) -> Tuple[List[Message], Optional[ResultMessage]]:
    """Collect all messages from a query.

    Returns:
        Tuple of (all_messages, result_message)
    """
    client = CopilotClient()
    await client.start()

    try:
        session = await client.create_session(
            on_permission_request=auto_approve_handler,
            model=model,
            working_directory=working_dir,
        )

        await session.send_and_wait(prompt, timeout=120.0)

        all_events = await session.get_messages()
        messages = _events_to_messages(all_events)

        result = None
        for msg in reversed(messages):
            if isinstance(msg, ResultMessage):
                result = msg
                break

        return messages, result
    finally:
        await client.stop()


# ============================================================================
# ERROR HANDLING
# ============================================================================


async def safe_query(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """Query with comprehensive error handling.

    Returns:
        Tuple of (response_text, error_message)
    """
    try:
        response = await simple_query(prompt)
        return response, None

    except ImportError:
        return (
            None,
            "Copilot SDK not installed. Install with: pip install github-copilot-sdk",
        )

    except FileNotFoundError:
        return None, "Copilot CLI not found. Install the GitHub Copilot CLI first."

    except TimeoutError as e:
        return None, f"Timeout error: {str(e)}"

    except Exception as e:
        return None, f"Unexpected error: {str(e)}"


# ============================================================================
# INTERACTIVE SESSIONS
# ============================================================================


class ManagedSession:
    """Async context manager wrapping CopilotClient + CopilotSession lifecycle.

    Usage:
        async with ManagedSession(model="gpt-4o") as session:
            await session.send_and_wait("Hello")
            events = session.get_messages()
    """

    def __init__(self, model: Optional[str] = None, working_dir: Optional[str] = None):
        self.model = model
        self.working_dir = working_dir
        self._client = None

    async def __aenter__(self) -> CopilotSession:
        self._client = CopilotClient()
        await self._client.start()
        session = await self._client.create_session(
            on_permission_request=auto_approve_handler,
            model=self.model,
            working_directory=self.working_dir,
        )
        return session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.stop()
        return False


async def interactive_conversation(prompts: List[str]) -> List[Message]:
    """Have a multi-turn conversation with Copilot.

    Args:
        prompts: List of prompts to send in sequence

    Returns:
        All messages from the conversation
    """
    async with ManagedSession() as session:
        for prompt in prompts:
            await session.send_and_wait(prompt, timeout=120.0)

        all_events = await session.get_messages()
        return _events_to_messages(all_events)


# ============================================================================
# ADVANCED PATTERNS
# ============================================================================


async def stream_with_progress(
    prompt: str,
    on_text: Optional[Callable[[str], None]] = None,
    on_tool: Optional[Callable[[ToolUseContent], None]] = None,
    model: Optional[str] = None,
) -> Optional[ResultMessage]:
    """Execute a query with real-time progress callbacks via session.on()."""
    client = CopilotClient()
    await client.start()
    result = None

    try:
        session = await client.create_session(
            on_permission_request=auto_approve_handler,
            model=model,
        )

        def event_handler(event: SessionEvent):
            nonlocal result
            parsed = parse_session_event(event)
            if parsed is None:
                return
            if isinstance(parsed, AssistantMessage):
                for block in parsed.content:
                    if isinstance(block, TextContent) and on_text:
                        on_text(block.text)
                    elif isinstance(block, ToolUseContent) and on_tool:
                        on_tool(block)
            elif isinstance(parsed, ResultMessage):
                result = parsed

        session.on(event_handler)
        await session.send_and_wait(prompt, timeout=120.0)

        return result
    finally:
        await client.stop()


async def query_with_timeout(prompt: str, timeout_seconds: float = 30) -> Optional[str]:
    """Query with timeout protection."""
    client = CopilotClient()
    await client.start()

    try:
        session = await client.create_session(
            on_permission_request=auto_approve_handler,
        )

        result_event = await session.send_and_wait(prompt, timeout=timeout_seconds)

        if result_event is None:
            logger.warning(f"Query timed out after {timeout_seconds} seconds")
            return None

        all_events = await session.get_messages()
        messages = _events_to_messages(all_events)
        return get_result_text(messages) or None
    except Exception as e:
        logger.warning(f"Query failed: {e}")
        return None
    finally:
        await client.stop()
