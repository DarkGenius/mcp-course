#!/usr/bin/env python3
"""Debug script to test analyze_file_changes logic outside of MCP."""

import json
import subprocess
import re
import time
import sys

def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def main():
    base_branch = "main"
    include_diff = True
    max_diff_lines = 500
    pathspec = ""

    log(f"Python: {sys.version}")
    log(f"Platform: {sys.platform}")
    log(f"CWD: {subprocess.run(['cmd', '/c', 'cd'], capture_output=True, text=True).stdout.strip()}")

    # Step 1: git rev-parse --show-toplevel
    log("Step 1: git rev-parse --show-toplevel")
    try:
        t0 = time.monotonic()
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
            timeout=10,
        )
        elapsed = time.monotonic() - t0
        working_dir = top.stdout.strip() or None
        log(f"  OK ({elapsed:.2f}s): working_dir={working_dir!r}")
    except subprocess.TimeoutExpired:
        log("  TIMEOUT!")
        return
    except subprocess.CalledProcessError as e:
        log(f"  FAILED: {e.stderr.strip()}")
        working_dir = None

    def run_git(args, label=""):
        log(f"  Running: git {' '.join(args)} {label}")
        t0 = time.monotonic()
        try:
            r = subprocess.run(
                ["git"] + args,
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            elapsed = time.monotonic() - t0
            log(f"    OK ({elapsed:.2f}s), stdout_len={len(r.stdout)}, stderr_len={len(r.stderr)}")
            return r
        except subprocess.TimeoutExpired:
            log(f"    TIMEOUT after 10s!")
            raise
        except subprocess.CalledProcessError as e:
            log(f"    FAILED: returncode={e.returncode}, stderr={e.stderr.strip()!r}")
            raise

    # Step 2: git --version
    log("Step 2: git --version")
    run_git(["--version"])

    # Step 3: rev-parse --is-inside-work-tree
    log("Step 3: git rev-parse --is-inside-work-tree")
    run_git(["rev-parse", "--is-inside-work-tree"])

    # Step 4: diff --name-status
    range_spec = f"{base_branch}...HEAD"
    extra = [pathspec] if pathspec else []
    log(f"Step 4: git diff --name-status {range_spec}")
    try:
        name_status = run_git(["diff", "--name-status", range_spec] + extra).stdout
        changed_files = []
        for line in name_status.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            status = parts[0]
            path = parts[-1]
            changed_files.append({"path": path, "status": status})
        log(f"  Changed files: {len(changed_files)}")
    except Exception:
        log("  Skipping remaining steps due to error")
        return

    # Step 5: diff --shortstat
    log(f"Step 5: git diff --shortstat {range_spec}")
    try:
        numstat = run_git(["diff", "--shortstat", range_spec] + extra).stdout.strip()
        log(f"  shortstat: {numstat!r}")
    except Exception:
        pass

    # Step 6: diff (full)
    if include_diff:
        log(f"Step 6: git diff {range_spec}")
        try:
            full_diff = run_git(["diff", range_spec] + (["--", pathspec] if pathspec else [])).stdout
            lines = full_diff.splitlines()
            log(f"  Diff lines: {len(lines)}")
        except Exception:
            pass

    log("ALL STEPS COMPLETED SUCCESSFULLY")

    # Build the same result as the tool would
    result = {
        "base_branch": base_branch,
        "changed_files": changed_files,
        "summary": {"files": len(changed_files)},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
