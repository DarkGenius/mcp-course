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
        # Используем git rev-parse чтобы найти корень репозитория,
        # не обращаясь к клиенту (list_roots может вызвать deadlock).
        working_dir = None
        try:
            top = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            if top:
                working_dir = top
        except subprocess.CalledProcessError:
            pass

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
    try:
        # Проверяем, существует ли директория с шаблонами
        if not TEMPLATES_DIR.exists():
            return json.dumps(
                {"error": "templates_dir_not_found", "hint": "Templates directory does not exist."},
                ensure_ascii=False,
            )

        # Получаем список всех .md файлов в директории шаблонов
        template_files = sorted(TEMPLATES_DIR.glob("*.md"))

        if not template_files:
            return json.dumps(
                {"error": "no_templates_found", "hint": "No .md template files found."},
                ensure_ascii=False,
            )

        # Читаем содержимое каждого шаблона и возвращаем как массив
        templates = []
        for template_file in template_files:
            try:
                content = template_file.read_text(encoding="utf-8")
                templates.append(
                    {
                        "filename": template_file.name,
                        "name": template_file.stem,
                        "content": content,
                    }
                )
            except OSError:
                # Пропускаем файлы, которые не удалось прочитать
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
    # Получаем список доступных шаблонов
    templates_response = await get_pr_templates()
    templates = json.loads(templates_response)

    # Проверяем, не было ли ошибки при получении шаблонов (если вернулся dict с error)
    if isinstance(templates, dict) and "error" in templates:
        return json.dumps(
            {
                "error": "templates_unavailable",
                "details": templates,
                "hint": "Could not load PR templates.",
            },
            ensure_ascii=False,
        )

    # Находим соответствующий шаблон по типу изменений
    change_type_lower = change_type.lower().strip()
    template_file = TYPE_MAPPING.get(change_type_lower, "feature.md")

    # Ищем шаблон в списке
    selected_template = next(
        (t for t in templates if t["filename"] == template_file),
        templates[0] if templates else None  # По умолчанию — первый шаблон
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


@mcp.tool()
async def add_numbers(a: int, b: int) -> str:
    """Simple test tool: returns the sum of two numbers.

    Args:
        a: First number
        b: Second number
    """
    return json.dumps({"result": a + b})


if __name__ == "__main__":
    mcp.run(transport="stdio")