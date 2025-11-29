"""
Simple background bot that pings the Claude CLI every 15 minutes.

Behavior:
- Launches the Claude CLI with a non-interactive prompt using -p flag
- Sends a random prompt plus an instruction to reply with exactly one word
- Logs question and reply with timestamp to claude-answers.txt
- Sleeps 15 minutes and repeats

Run in background:
  pythonw claude_ping_bot.py

Or with visible output:
  python claude_ping_bot.py --stdout
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path
from shutil import which

# Base Claude command
CLAUDE_EXE: str = "claude"

# How long to wait between runs (in seconds)
INTERVAL_SECONDS = 15 * 60  # 15 minutes

# Maximum time to wait for a single Claude reply before giving up
REPLY_TIMEOUT_SECONDS = 120

# Prompts to rotate through; a random one is selected each cycle.
PROMPTS = [
    "Name any color",
    "Pick a planet",
    "Choose a season",
    "Say an animal",
    "Pick a programming language",
    "Name a fruit",
    "Name a country",
    "Pick a number between 1 and 100",
    "Name a musical instrument",
    "Pick a day of the week",
    "Name a vegetable",
    "Choose a month",
    "Name a sport",
    "Pick an ocean",
    "Name a bird",
]


def log_answer(answers_path: Path, question: str, answer: str) -> None:
    """Log question and answer to claude-answers.txt"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    with answers_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] Q: {question} | A: {answer}\n")


def log_debug(log_path: Path, message: str, mirror_stdout: bool = False) -> None:
    """Log debug/error info to separate debug log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] {message}\n")
    if mirror_stdout:
        print(f"[{timestamp}] {message}")


def run_single_ping(answers_path: Path, debug_log_path: Path, mirror_stdout: bool = False) -> None:
    prompt = random.choice(PROMPTS)
    full_prompt = f"{prompt} Respond with exactly one word."

    log_debug(debug_log_path, f"Asking: '{prompt}'", mirror_stdout)

    # Build command with -p flag for non-interactive mode (print and exit)
    # Using shell=True on Windows to handle .cmd wrapper scripts
    is_windows = os.name == "nt"

    if is_windows:
        # On Windows, use shell command string for .cmd files
        cmd_str = f'claude -p "{full_prompt}"'

        try:
            result = subprocess.run(
                cmd_str,
                shell=True,
                capture_output=True,
                text=True,
                timeout=REPLY_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            log_debug(debug_log_path, "ERROR: Timed out waiting for reply.", mirror_stdout)
            log_answer(answers_path, prompt, "TIMEOUT")
            return
        except Exception as exc:
            log_debug(debug_log_path, f"ERROR: Failed to run command: {exc}", mirror_stdout)
            log_answer(answers_path, prompt, f"ERROR: {exc}")
            return
    else:
        # On Unix, use list form
        resolved_exe = CLAUDE_EXE
        resolved = which(CLAUDE_EXE)
        if resolved:
            resolved_exe = resolved
        cmd_list = [resolved_exe, "-p", full_prompt]

        try:
            result = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=REPLY_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            log_debug(debug_log_path, "ERROR: Timed out waiting for reply.", mirror_stdout)
            log_answer(answers_path, prompt, "TIMEOUT")
            return
        except FileNotFoundError:
            log_debug(debug_log_path, f"ERROR: Command not found: {resolved_exe}", mirror_stdout)
            log_answer(answers_path, prompt, "ERROR: claude not found")
            return
        except Exception as exc:
            log_debug(debug_log_path, f"ERROR: Failed to run command: {exc}", mirror_stdout)
            log_answer(answers_path, prompt, f"ERROR: {exc}")
            return

    exit_code = result.returncode
    stdout_clean = (result.stdout or "").strip()
    stderr_clean = (result.stderr or "").strip()

    if exit_code == 0:
        # Extract just the reply (may contain ANSI codes or extra output)
        reply_lines = stdout_clean.split("\n")
        reply = reply_lines[-1] if reply_lines else stdout_clean
        log_answer(answers_path, prompt, reply)
        log_debug(debug_log_path, f"SUCCESS: '{prompt}' -> '{reply}'", mirror_stdout)
    else:
        error_msg = stderr_clean or stdout_clean or f"exit code {exit_code}"
        log_answer(answers_path, prompt, f"FAIL: {error_msg}")
        log_debug(debug_log_path, f"FAIL: exit_code={exit_code} stderr='{stderr_clean}'", mirror_stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ping Claude CLI every 15 minutes.")
    parser.add_argument("--stdout", action="store_true", help="Print activity to STDOUT (foreground mode).")
    parser.add_argument("--once", action="store_true", help="Run once and exit (for testing).")
    args = parser.parse_args()

    mirror_stdout = bool(args.stdout)
    script_dir = Path(__file__).resolve().parent
    answers_path = script_dir / "claude-answers.txt"
    debug_log_path = script_dir / "claude-ping-debug.log"

    log_debug(debug_log_path, "Claude ping bot started.", mirror_stdout)

    if args.once:
        run_single_ping(answers_path, debug_log_path, mirror_stdout)
        return

    try:
        while True:
            run_single_ping(answers_path, debug_log_path, mirror_stdout)
            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        log_debug(debug_log_path, "Claude ping bot stopped via KeyboardInterrupt.", mirror_stdout)
        sys.exit(0)


if __name__ == "__main__":
    main()
