"""Template loading and variable substitution for DW prompt templates.

Templates are GitHub Copilot prompt files (.prompt.md) stored in
.github/copilot/prompts/. The same files work as:
  - VS Code Copilot slash commands (native .prompt.md support)
  - Copilot CLI skills (via /skills add)
  - DW automation prompts (loaded by this module)

The YAML frontmatter (name, description, tools, model) is parsed
and stripped before sending the body as a prompt to the agent.
"""

import os
import re
from typing import Dict, Tuple


def _get_prompts_dir() -> str:
    """Get the .github/copilot/prompts/ directory path."""
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return os.path.join(project_root, ".github", "copilot", "prompts")


def parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """Parse YAML frontmatter from a prompt file.

    Returns:
        Tuple of (frontmatter_dict, body) where body is the content
        after the frontmatter block.
    """
    if not content.startswith("---"):
        return {}, content

    # Find the closing ---
    end = content.find("---", 3)
    if end == -1:
        return {}, content

    frontmatter_raw = content[3:end].strip()
    body = content[end + 3 :].strip()

    # Simple YAML-like parsing (key: value pairs)
    frontmatter = {}
    for line in frontmatter_raw.split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip("'\"")
            frontmatter[key] = value

    return frontmatter, body


def load_template(template_name: str) -> str:
    """Read a prompt file from .github/copilot/prompts/.

    Strips the YAML frontmatter and returns only the body.

    Args:
        template_name: Name without extension, e.g. "plan"

    Returns:
        Template body (frontmatter stripped)
    """
    path = os.path.join(_get_prompts_dir(), f"{template_name}.prompt.md")
    with open(path, "r") as f:
        content = f.read()
    _, body = parse_frontmatter(content)
    return body


def load_template_with_metadata(template_name: str) -> Tuple[Dict[str, str], str]:
    """Read a prompt file and return both frontmatter and body.

    Args:
        template_name: Name without extension, e.g. "plan"

    Returns:
        Tuple of (frontmatter_dict, body)
    """
    path = os.path.join(_get_prompts_dir(), f"{template_name}.prompt.md")
    with open(path, "r") as f:
        content = f.read()
    return parse_frontmatter(content)


def render_template(template: str, **variables: str) -> str:
    """Substitute $VARIABLE placeholders in a template.

    Uses $VARIABLE syntax (not {variable}) to avoid conflicts with
    markdown code blocks, JSON examples, and other brace-heavy content.
    """
    result = template
    for key, value in variables.items():
        result = result.replace(f"${key}", str(value))
    return result


def load_and_render(template_name: str, **variables: str) -> str:
    """Load a prompt file and render it with variables.

    Args:
        template_name: Name without extension, e.g. "plan"
        **variables: Key-value pairs for substitution

    Returns:
        Rendered template body (frontmatter stripped, variables substituted)
    """
    template = load_template(template_name)
    return render_template(template, **variables)


def slugify(text: str, max_length: int = 40) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    slug = slug.strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("-")
    return slug
