#!/usr/bin/env python3
"""
Module 1: Basic MCP Server - Starter Code
TODO: Implement tools for analyzing git changes and suggesting PR templates
"""

import json
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("pr-agent")

# PR template directory (shared across all modules)
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


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
    max_diff_lines: int = 500,
    cwd_from_root: bool = True,
    pathspec: str = "",
) -> str:
    """
    Возвращает изменения относительно base_branch в текущем git-репозитории.

    Args:
        base_branch: Базовая ветка для сравнения (по умолчанию "main").
        include_diff: Включать ли полный diff (по умолчанию True, но будет усечён).
        max_diff_lines: Максимум строк diff, чтобы не переполнять лимит инструмента.
        cwd_from_root: Если True — использовать корневую директорию Claude (MCP roots).
        pathspec: Необязательный путь/паттерн для ограничения области diff (например, "src/" или "*.py").
    Returns:
        JSON-строка со структурой:
        {
          "base_branch": "...",
          "changed_files": [{"path": "...", "status": "M/A/D/..."}],
          "summary": {"files": N, "insertions": I, "deletions": D},
          "diff": "...\n"
          "truncated": true|false
        }
    """
    try:
        # 1) Определим рабочую директорию
        working_dir = None
        if cwd_from_root:
            try:
                context = mcp.get_context()
                roots_result = await context.session.list_roots()
                if roots_result.roots:
                    # Берём первый root
                    working_dir = roots_result.roots[0].uri.path
            except (ValueError, AttributeError):
                # Контекст недоступен (например, в тестах) - используем текущую директорию
                working_dir = None

        def run_git(args: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git"] + args,
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=True,
            )

        # 2) Проверим доступность git и что мы в репозитории
        run_git(["--version"])
        # Это вернёт ошибку, если не в репозитории
        run_git(["rev-parse", "--is-inside-work-tree"])

        # 3) Построим базовый диапазон сравнения и опциональную область
        range_spec = f"{base_branch}...HEAD"
        extra = [pathspec] if pathspec else []

        # 4) Список изменённых файлов со статусами
        # Формат: "M\tpath", "A\tpath", "D\tpath", ...
        name_status = run_git(["diff", "--name-status", range_spec] + extra).stdout
        changed_files = []
        for line in name_status.splitlines():
            if not line.strip():
                continue
            # Может быть статус с табами (например, копирование/переименование)
            parts = line.split("\t")
            status = parts[0]
            path = parts[-1]  # последний столбец — целевой путь
            changed_files.append({"path": path, "status": status})

        # 5) Сводка по изменениям (вставки/удаления)
        # Пример строки: " 3 files changed, 20 insertions(+), 5 deletions(-)"
        numstat = run_git(["diff", "--shortstat", range_spec] + extra).stdout.strip()
        files = insertions = deletions = 0
        # Простейший парсер shortstat:
        # ищем числа в подстроках "files changed", "insertions", "deletions"
        import re
        m_files = re.search(r"(\d+)\s+files?\s+changed", numstat)
        if m_files:
            files = int(m_files.group(1))
        m_ins = re.search(r"(\d+)\s+insertions?\(\+\)", numstat)
        if m_ins:
            insertions = int(m_ins.group(1))
        m_del = re.search(r"(\d+)\s+deletions?\(-\)", numstat)
        if m_del:
            deletions = int(m_del.group(1))

        result = {
            "base_branch": base_branch,
            "changed_files": changed_files,
            "summary": {"files": files, "insertions": insertions, "deletions": deletions},
        }

        # 6) По желанию — сам diff с усечением
        if include_diff:
            full_diff = run_git(["diff", range_spec] + (["--", pathspec] if pathspec else [])).stdout
            lines = full_diff.splitlines()
            truncated = False
            if len(lines) > max_diff_lines:
                lines = lines[:max_diff_lines]
                truncated = True
                lines.append(f"\n--- Diff truncated at {max_diff_lines} lines ---")
            result["diff"] = "\n".join(lines)
            result["truncated"] = truncated

        return json.dumps(result, ensure_ascii=False)

    except subprocess.CalledProcessError as e:
        return json.dumps(
            {
                "error": "git_failed",
                "cmd": getattr(e, "cmd", None),
                "stderr": (e.stderr or "").strip(),
            },
            ensure_ascii=False,
        )
    except FileNotFoundError:
        return json.dumps(
            {"error": "git_not_found", "hint": "Git is not installed or not in PATH."},
            ensure_ascii=False,
        )


@mcp.tool()
async def get_pr_templates() -> str:
    """List available PR templates with their content."""
    # TODO: Implement this tool
    return json.dumps({"error": "Not implemented yet", "hint": "Read templates from TEMPLATES_DIR"})


@mcp.tool()
async def suggest_template(changes_summary: str, change_type: str) -> str:
    """Let Claude analyze the changes and suggest the most appropriate PR template.
    
    Args:
        changes_summary: Your analysis of what the changes do
        change_type: The type of change you've identified (bug, feature, docs, refactor, test, etc.)
    """
    # TODO: Implement this tool
    return json.dumps({"error": "Not implemented yet", "hint": "Map change_type to templates"})


if __name__ == "__main__":
    mcp.run()