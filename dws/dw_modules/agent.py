"""GitHub Copilot agent module for executing prompts programmatically.

This module mirrors the Claude Code agent.py but targets the GitHub Copilot CLI.
The Copilot CLI supports the same one-shot subprocess pattern as Claude Code:

    copilot -p "prompt" --output-format json --allow-all

Key mapping from Claude Code:
    claude -p "prompt" --output-format stream-json --dangerously-skip-permissions
    copilot -p "prompt" --output-format json --allow-all
"""

import json
import os
import re
import subprocess
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from pydantic import BaseModel


# Retry codes for Copilot execution errors
class RetryCode(str, Enum):
    """Codes indicating different types of errors that may be retryable."""

    COPILOT_ERROR = "copilot_error"
    TIMEOUT_ERROR = "timeout_error"
    EXECUTION_ERROR = "execution_error"
    ERROR_DURING_EXECUTION = "error_during_execution"
    NONE = "none"


class CopilotPromptRequest(BaseModel):
    """Copilot agent prompt configuration."""

    prompt: str
    dw_id: str
    agent_name: str = "ops"
    model: Optional[str] = None  # e.g. "gpt-4o", "claude-sonnet-4", "gemini"
    allow_all: bool = True
    output_file: str
    working_dir: Optional[str] = None


class CopilotPromptResponse(BaseModel):
    """Copilot agent response."""

    output: str
    success: bool
    session_id: Optional[str] = None
    retry_code: RetryCode = RetryCode.NONE


class CopilotResultMessage(BaseModel):
    """Copilot JSONL result message (last line)."""

    type: str
    subtype: str = ""
    is_error: bool = False
    duration_ms: int = 0
    duration_api_ms: int = 0
    num_turns: int = 0
    result: str = ""
    session_id: str = ""
    total_cost_usd: float = 0.0


def get_safe_subprocess_env() -> Dict[str, str]:
    """Get filtered environment variables safe for subprocess execution.

    Returns only the environment variables needed for Copilot CLI execution.
    """
    safe_env_vars = {
        # GitHub Configuration (required for Copilot auth)
        "GITHUB_TOKEN": os.getenv("GITHUB_TOKEN"),
        "COPILOT_GITHUB_TOKEN": os.getenv("COPILOT_GITHUB_TOKEN"),
        "GH_TOKEN": os.getenv("GH_TOKEN"),
        # BYOK keys (optional - for bring-your-own-key mode)
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "AZURE_OPENAI_API_KEY": os.getenv("AZURE_OPENAI_API_KEY"),
        # Copilot CLI Configuration
        "COPILOT_CLI_PATH": os.getenv("COPILOT_CLI_PATH", "copilot"),
        # Essential system environment variables
        "HOME": os.getenv("HOME"),
        "USER": os.getenv("USER"),
        "PATH": os.getenv("PATH"),
        "SHELL": os.getenv("SHELL"),
        "TERM": os.getenv("TERM"),
        "LANG": os.getenv("LANG"),
        "LC_ALL": os.getenv("LC_ALL"),
        # Python-specific
        "PYTHONPATH": os.getenv("PYTHONPATH"),
        "PYTHONUNBUFFERED": "1",
        # Working directory tracking
        "PWD": os.getcwd(),
    }

    return {k: v for k, v in safe_env_vars.items() if v is not None}


# Load environment variables
load_dotenv()

# Get Copilot CLI path from environment
COPILOT_PATH = os.getenv("COPILOT_CLI_PATH", "copilot")

# Output file name constants (cp_ prefix for Copilot, mirrors cc_ from Claude Code)
OUTPUT_JSONL = "cp_raw_output.jsonl"
OUTPUT_JSON = "cp_raw_output.json"
FINAL_OBJECT_JSON = "cp_final_object.json"
SUMMARY_JSON = "custom_summary_output.json"


def generate_short_id() -> str:
    """Generate a short 8-character UUID for tracking."""
    return str(uuid.uuid4())[:8]


def truncate_output(
    output: str, max_length: int = 500, suffix: str = "... (truncated)"
) -> str:
    """Truncate output to a reasonable length for display."""
    # Check if this looks like JSONL data
    if output.startswith('{"type":') and '\n{"type":' in output:
        lines = output.strip().split("\n")
        for line in reversed(lines):
            try:
                data = json.loads(line)
                if data.get("type") == "result":
                    result = data.get("result", "")
                    if result:
                        return truncate_output(result, max_length, suffix)
                elif data.get("type") == "assistant" and data.get("message"):
                    content = data["message"].get("content", [])
                    if isinstance(content, list) and content:
                        text = content[0].get("text", "")
                        if text:
                            return truncate_output(text, max_length, suffix)
            except Exception:
                pass
        return f"[JSONL output with {len(lines)} messages]{suffix}"

    if len(output) <= max_length:
        return output

    truncate_at = max_length - len(suffix)

    newline_pos = output.rfind("\n", truncate_at - 50, truncate_at)
    if newline_pos > 0:
        return output[:newline_pos] + suffix

    space_pos = output.rfind(" ", truncate_at - 20, truncate_at)
    if space_pos > 0:
        return output[:space_pos] + suffix

    return output[:truncate_at] + suffix


def check_copilot_installed() -> Optional[str]:
    """Check if Copilot CLI is installed. Return error message if not."""
    try:
        result = subprocess.run(
            [COPILOT_PATH, "--version"], capture_output=True, text=True
        )
        if result.returncode != 0:
            return f"Error: Copilot CLI is not installed. Expected at: {COPILOT_PATH}"
    except FileNotFoundError:
        return f"Error: Copilot CLI is not installed. Expected at: {COPILOT_PATH}"
    return None


def extract_assistant_text(messages: List[Dict[str, Any]]) -> str:
    """Extract the assistant's text response from Copilot JSONL messages.

    Copilot format: assistant.message events have data.content (string).
    This is different from Claude Code where content is an array of blocks.

    Returns:
        Concatenated text from all assistant.message events
    """
    texts = []
    for msg in messages:
        if msg.get("type") == "assistant.message":
            data = msg.get("data", {})
            content = data.get("content", "")
            if content:
                texts.append(content)
    return "\n".join(texts)


def parse_copilot_output(
    output_file: str,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Parse JSONL output file and return all messages and the result message.

    Copilot JSONL format differs from Claude Code:
    - assistant.message: data.content is a string (not an array)
    - result: has sessionId (camelCase), exitCode, usage (no "result" text field)

    Returns:
        Tuple of (all_messages, result_message) where result_message is None if not found
    """
    try:
        with open(output_file, "r") as f:
            messages = [json.loads(line) for line in f if line.strip()]

            result_message = None
            for message in reversed(messages):
                if message.get("type") == "result":
                    result_message = message
                    break

            return messages, result_message
    except Exception:
        return [], None


def convert_jsonl_to_json(jsonl_file: str) -> str:
    """Convert JSONL file to JSON array file."""
    output_dir = os.path.dirname(jsonl_file)
    json_file = os.path.join(output_dir, OUTPUT_JSON)

    messages, _ = parse_copilot_output(jsonl_file)

    with open(json_file, "w") as f:
        json.dump(messages, f, indent=2)

    return json_file


def save_last_entry_as_raw_result(json_file: str) -> Optional[str]:
    """Save the last entry from a JSON array file as cp_final_object.json."""
    try:
        with open(json_file, "r") as f:
            messages = json.load(f)

        if not messages:
            return None

        last_entry = messages[-1]

        output_dir = os.path.dirname(json_file)
        final_object_file = os.path.join(output_dir, FINAL_OBJECT_JSON)

        with open(final_object_file, "w") as f:
            json.dump(last_entry, f, indent=2)

        return final_object_file
    except Exception:
        return None


def get_copilot_env() -> Dict[str, str]:
    """Get only the required environment variables for Copilot execution."""
    return get_safe_subprocess_env()


def save_prompt(prompt: str, dw_id: str, agent_name: str = "ops") -> None:
    """Save a prompt to the appropriate logging directory."""
    match = re.match(r"^(/\w+)", prompt)
    if not match:
        return

    slash_command = match.group(1)
    command_name = slash_command[1:]

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    prompt_dir = os.path.join(project_root, "agents", dw_id, agent_name, "prompts")
    os.makedirs(prompt_dir, exist_ok=True)

    prompt_file = os.path.join(prompt_dir, f"{command_name}.txt")
    with open(prompt_file, "w") as f:
        f.write(prompt)


def prompt_copilot_with_retry(
    request: CopilotPromptRequest,
    max_retries: int = 3,
    retry_delays: List[int] = None,
) -> CopilotPromptResponse:
    """Execute Copilot with retry logic for certain error types."""
    if retry_delays is None:
        retry_delays = [1, 3, 5]

    while len(retry_delays) < max_retries:
        retry_delays.append(retry_delays[-1] + 2)

    last_response = None

    for attempt in range(max_retries + 1):
        if attempt > 0:
            delay = retry_delays[attempt - 1]
            time.sleep(delay)

        response = prompt_copilot(request)
        last_response = response

        if response.success or response.retry_code == RetryCode.NONE:
            return response

        if response.retry_code in [
            RetryCode.COPILOT_ERROR,
            RetryCode.TIMEOUT_ERROR,
            RetryCode.EXECUTION_ERROR,
            RetryCode.ERROR_DURING_EXECUTION,
        ]:
            if attempt < max_retries:
                continue
            else:
                return response

    return last_response


def prompt_copilot(request: CopilotPromptRequest) -> CopilotPromptResponse:
    """Execute Copilot CLI with the given prompt configuration.

    Uses the same one-shot subprocess pattern as Claude Code:
        copilot -p "prompt" --output-format json --allow-all
    """

    # Check if Copilot CLI is installed
    error_msg = check_copilot_installed()
    if error_msg:
        return CopilotPromptResponse(
            output=error_msg,
            success=False,
            session_id=None,
            retry_code=RetryCode.NONE,
        )

    # Save prompt before execution
    save_prompt(request.prompt, request.dw_id, request.agent_name)

    # Create output directory if needed
    output_dir = os.path.dirname(request.output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Build command
    # copilot -p "prompt" --output-format json --allow-all
    cmd = [COPILOT_PATH, "-p", request.prompt]

    if request.model:
        cmd.extend(["--model", request.model])

    cmd.extend(["--output-format", "json"])

    # --allow-all is equivalent to Claude Code's --dangerously-skip-permissions
    if request.allow_all:
        cmd.append("--allow-all")

    # Set up environment with only required variables
    env = get_copilot_env()

    try:
        # Open output file for streaming
        with open(request.output_file, "w") as output_f:
            result = subprocess.run(
                cmd,
                stdout=output_f,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=request.working_dir,
            )

        if result.returncode == 0:
            # Parse the JSONL file
            messages, result_message = parse_copilot_output(request.output_file)

            # Convert JSONL to JSON array file
            json_file = convert_jsonl_to_json(request.output_file)

            # Save the last entry as final object
            save_last_entry_as_raw_result(json_file)

            # Extract the assistant's text from assistant.message events
            assistant_text = extract_assistant_text(messages)

            if result_message:
                # Copilot uses camelCase: sessionId, exitCode
                session_id = result_message.get("sessionId")
                exit_code = result_message.get("exitCode", 0)
                is_error = exit_code != 0

                return CopilotPromptResponse(
                    output=assistant_text or "(no text response)",
                    success=not is_error,
                    session_id=session_id,
                    retry_code=RetryCode.NONE,
                )
            elif assistant_text:
                # No result message but we got assistant text - still a success
                return CopilotPromptResponse(
                    output=assistant_text,
                    success=True,
                    session_id=None,
                    retry_code=RetryCode.NONE,
                )
            else:
                return CopilotPromptResponse(
                    output="No response found in Copilot output",
                    success=False,
                    session_id=None,
                    retry_code=RetryCode.NONE,
                )
        else:
            stderr_msg = result.stderr.strip() if result.stderr else ""

            stdout_msg = ""
            error_from_jsonl = None
            try:
                if os.path.exists(request.output_file):
                    messages, result_message = parse_copilot_output(request.output_file)

                    if result_message and result_message.get("is_error"):
                        error_from_jsonl = result_message.get("result", "Unknown error")
                    elif messages:
                        for msg in reversed(messages[-5:]):
                            if msg.get("type") == "assistant" and msg.get(
                                "message", {}
                            ).get("content"):
                                content = msg["message"]["content"]
                                if isinstance(content, list) and content:
                                    text = content[0].get("text", "")
                                    if text and (
                                        "error" in text.lower()
                                        or "failed" in text.lower()
                                    ):
                                        error_from_jsonl = text[:500]
                                        break

                    if not error_from_jsonl:
                        with open(request.output_file, "r") as f:
                            lines = f.readlines()
                            if lines:
                                stdout_msg = lines[-1].strip()[:200]
            except Exception:
                pass

            if error_from_jsonl:
                error_msg = f"Copilot error: {error_from_jsonl}"
            elif stdout_msg and not stderr_msg:
                error_msg = f"Copilot error: {stdout_msg}"
            elif stderr_msg and not stdout_msg:
                error_msg = f"Copilot error: {stderr_msg}"
            elif stdout_msg and stderr_msg:
                error_msg = f"Copilot error: {stderr_msg}\nStdout: {stdout_msg}"
            else:
                error_msg = (
                    f"Copilot error: Command failed with exit code {result.returncode}"
                )

            return CopilotPromptResponse(
                output=truncate_output(error_msg, max_length=800),
                success=False,
                session_id=None,
                retry_code=RetryCode.COPILOT_ERROR,
            )

    except subprocess.TimeoutExpired:
        return CopilotPromptResponse(
            output="Error: Copilot command timed out after 5 minutes",
            success=False,
            session_id=None,
            retry_code=RetryCode.TIMEOUT_ERROR,
        )
    except Exception as e:
        return CopilotPromptResponse(
            output=f"Error executing Copilot: {e}",
            success=False,
            session_id=None,
            retry_code=RetryCode.EXECUTION_ERROR,
        )


class CopilotTemplateRequest(BaseModel):
    """Copilot agent template execution request."""

    agent_name: str
    slash_command: str
    args: List[str]
    dw_id: str
    model: Optional[str] = None
    working_dir: Optional[str] = None


def execute_template(request: CopilotTemplateRequest) -> CopilotPromptResponse:
    """Execute a Copilot template with slash command and arguments."""

    prompt = f"{request.slash_command} {' '.join(request.args)}"

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    output_dir = os.path.join(
        project_root, "agents", request.dw_id, request.agent_name
    )
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, OUTPUT_JSONL)

    prompt_request = CopilotPromptRequest(
        prompt=prompt,
        dw_id=request.dw_id,
        agent_name=request.agent_name,
        model=request.model,
        allow_all=True,
        output_file=output_file,
        working_dir=request.working_dir,
    )

    return prompt_copilot_with_retry(prompt_request)
