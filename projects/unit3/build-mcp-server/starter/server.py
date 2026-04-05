#!/usr/bin/env python3
"""
Module 1: Basic MCP Server - Starter Code
TODO: Implement tools for analyzing git changes and suggesting PR templates
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("pr-agent")

# Set PR_AGENT_DEV_TOOLS=1 to register optional dev-only tools (e.g. add_numbers).
_DEV_TOOLS = os.environ.get("PR_AGENT_DEV_TOOLS", "").strip().lower() in ("1", "true", "yes")

# PR template directory (shared across all modules)
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

# Display names for known templates (aligned with solution DEFAULT_TEMPLATES)
TEMPLATE_DISPLAY_NAMES = {
    "bug.md": "Bug Fix",
    "feature.md": "Feature",
    "docs.md": "Documentation",
    "refactor.md": "Refactor",
    "test.md": "Test",
    "performance.md": "Performance",
    "security.md": "Security",
}

# Маппинг типов изменений к файлам шаблонов
TYPE_MAPPING = {
    "bug": "bug.md",
    "fix": "bug.md",
    "feature": "feature.md",
    "enhancement": "feature.md",
    "docs": "docs.md",
    "documentation": "docs.md",
    "refactor": "refactor.md",
    "cleanup": "refactor.md",
    "test": "test.md",
    "testing": "test.md",
    "performance": "performance.md",
    "optimization": "performance.md",
    "security": "security.md",
}

_SHORTSTAT_RE = re.compile(
    r"(?:(?P<files>\d+)\s+files?\s+changed)?(?:,\s*)?"
    r"(?:(?P<ins>\d+)\s+insertions?\(\+\))?(?:,\s*)?"
    r"(?:(?P<del>\d+)\s+deletions?\(-\))?"
)


def _parse_shortstat(numstat: str) -> tuple[int, int, int]:
    m = _SHORTSTAT_RE.search(numstat)
    if not m:
        return 0, 0, 0
    g = m.groupdict()
    files = int(g["files"]) if g.get("files") is not None else 0
    insertions = int(g["ins"]) if g.get("ins") is not None else 0
    deletions = int(g["del"]) if g.get("del") is not None else 0
    return files, insertions, deletions


def _template_display_type(filename: str, stem: str) -> str:
    return TEMPLATE_DISPLAY_NAMES.get(filename, stem.replace("_", " ").title())


def _json_response(payload: Any, *, compact: bool) -> str:
    if compact:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(payload, ensure_ascii=False)


# TODO: Implement tool functions here
# Example structure for a tool:
# @mcp.tool()
# async def analyze_file_changes(base_branch: str = "main", include_diff: bool = True) -> str:
#     """Get the full diff and list of changed files in the current git repository.
#
#     Args:
#         base_branch: Base branch to compare against (default: main)
#         include_diff: Include the full diff content (default: true)
#     """
#     # Your implementation here
#     pass

# Minimal stub implementations so the server runs
# TODO: Replace these with your actual implementations

@mcp.tool()
async def analyze_file_changes(
    base_branch: str = "main",
    include_diff: bool = True,
    include_commits: bool = True,
    max_diff_lines: int = 500,
    working_directory: Optional[str] = None,
    use_repo_root: bool = True,
    pathspec: str = "",
    compact: bool = False,
) -> str:
    """
    Возвращает изменения относительно base_branch в текущем git-репозитории.

    Args:
        base_branch: Базовая ветка для сравнения (по умолчанию "main").
        include_diff: Включать ли полный diff (по умолчанию True, усечён до max_diff_lines).
        include_commits: Включать ли git log --oneline для диапазона base_branch..HEAD.
        max_diff_lines: Максимум строк diff, чтобы не переполнять лимит инструмента.
        working_directory: Явный каталог для запуска git (по умолчанию текущий каталог процесса).
        use_repo_root: Если True — подняться в корень репозитория (git rev-parse --show-toplevel)
            относительно working_directory; если False — команды git выполняются в этом каталоге.
        pathspec: Необязательный путь для ограничения области (например, "src/"); передаётся после "--".
        compact: Если True — компактный JSON без пробелов (экономия токенов).

    Returns:
        JSON-строка. Всегда: base_branch, changed_files, summary.
        Опционально: commits (если include_commits), diff и truncated (если include_diff).
    """
    try:
        start = Path(working_directory).resolve() if working_directory else Path.cwd()

        working_dir: Optional[str] = None
        if use_repo_root:
            try:
                top = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=str(start),
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
                working_dir = top or str(start)
            except subprocess.CalledProcessError as e:
                return _json_response(
                    {
                        "error": "git_failed",
                        "hint": "Could not resolve repository root (git rev-parse --show-toplevel).",
                        "stderr": (e.stderr or "").strip(),
                    },
                    compact=compact,
                )
        else:
            working_dir = str(start)

        def run_git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git"] + args,
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=check,
            )

        path_tail = ["--", pathspec] if pathspec else []

        run_git(["rev-parse", "--is-inside-work-tree"])

        range_spec = f"{base_branch}...HEAD"
        commit_range = f"{base_branch}..HEAD"

        name_status = run_git(["diff", "--name-status", range_spec] + path_tail).stdout
        changed_files = []
        for line in name_status.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            status = parts[0]
            path = parts[-1]
            changed_files.append({"path": path, "status": status})

        numstat = run_git(["diff", "--shortstat", range_spec] + path_tail).stdout.strip()
        files, insertions, deletions = _parse_shortstat(numstat)

        result: dict[str, Any] = {
            "base_branch": base_branch,
            "changed_files": changed_files,
            "summary": {"files": files, "insertions": insertions, "deletions": deletions},
        }

        if include_commits:
            log_cp = run_git(["log", "--oneline", commit_range] + path_tail, check=False)
            result["commits"] = log_cp.stdout.strip() if log_cp.returncode == 0 else ""

        if include_diff:
            full_diff = run_git(["diff", range_spec] + path_tail).stdout
            lines = full_diff.splitlines()
            truncated = False
            if len(lines) > max_diff_lines:
                lines = lines[:max_diff_lines]
                truncated = True
                lines.append(f"\n--- Diff truncated at {max_diff_lines} lines ---")
            result["diff"] = "\n".join(lines)
            result["truncated"] = truncated

        return _json_response(result, compact=compact)

    except subprocess.CalledProcessError as e:
        return _json_response(
            {
                "error": "git_failed",
                "cmd": getattr(e, "cmd", None),
                "stderr": (e.stderr or "").strip(),
            },
            compact=compact,
        )
    except FileNotFoundError:
        return _json_response(
            {"error": "git_not_found", "hint": "Git is not installed or not in PATH."},
            compact=compact,
        )


@mcp.tool()
async def get_pr_templates() -> str:
    """List available PR templates with their content."""
    try:
        if not TEMPLATES_DIR.exists():
            return json.dumps(
                {"error": "templates_dir_not_found", "hint": "Templates directory does not exist."},
                ensure_ascii=False,
            )

        template_files = sorted(TEMPLATES_DIR.glob("*.md"))

        if not template_files:
            return json.dumps(
                {"error": "no_templates_found", "hint": "No .md template files found."},
                ensure_ascii=False,
            )

        templates = []
        for template_file in template_files:
            try:
                content = template_file.read_text(encoding="utf-8")
                templates.append(
                    {
                        "filename": template_file.name,
                        "name": template_file.stem,
                        "type": _template_display_type(template_file.name, template_file.stem),
                        "content": content,
                    }
                )
            except OSError:
                pass

        return json.dumps(templates, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps(
            {"error": "unexpected_error", "message": str(e)},
            ensure_ascii=False,
        )


@mcp.tool()
async def suggest_template(changes_summary: str, change_type: str) -> str:
    """Let Claude analyze the changes and suggest the most appropriate PR template.

    Args:
        changes_summary: Your analysis of what the changes do
        change_type: The type of change you've identified (bug, feature, docs, refactor, test, etc.)
    """
    templates_response = await get_pr_templates()
    templates = json.loads(templates_response)

    if isinstance(templates, dict) and "error" in templates:
        return json.dumps(
            {
                "error": "templates_unavailable",
                "details": templates,
                "hint": "Could not load PR templates.",
            },
            ensure_ascii=False,
        )

    change_type_lower = change_type.lower().strip()
    template_file = TYPE_MAPPING.get(change_type_lower, "feature.md")

    selected_template = next(
        (t for t in templates if t["filename"] == template_file),
        templates[0] if templates else None,
    )

    if selected_template is None:
        return json.dumps(
            {
                "error": "no_templates_available",
                "hint": "No templates found to suggest.",
            },
            ensure_ascii=False,
        )

    suggestion = {
        "recommended_template": selected_template,
        "reasoning": f"Based on your analysis: '{changes_summary}', this appears to be a {change_type} change.",
        "template_content": selected_template.get("content", ""),
        "usage_hint": "Claude can help you fill out this template based on the specific changes in your PR.",
    }

    return json.dumps(suggestion, ensure_ascii=False, indent=2)


async def add_numbers(a: int, b: int) -> str:
    """Simple test tool: returns the sum of two numbers.

    Args:
        a: First number
        b: Second number
    """
    return json.dumps({"result": a + b})


if _DEV_TOOLS:
    add_numbers = mcp.tool()(add_numbers)


if __name__ == "__main__":
    mcp.run(transport="stdio")
