from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from ..prompts import fill
from ..repertoire import Repertoire

CODING = "coding"
SHELL_TOOL_CALLS = 8
SHELL_OUTPUT_CHARS = 4000
SHELL_OUTPUT_BYTES = 4 * SHELL_OUTPUT_CHARS
REAP_SECONDS = 2
FILE_CHARS = 8000
BLOCKED_COMMANDS = ("rm -rf /", "sudo ", "shutdown", "reboot", "mkfs", ":(){", "kill -9 -1", "> /dev/sd", "crontab")
BUDGET_EXHAUSTED = "[tool budget exhausted. Output the observation now.]"


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[[dict], Awaitable[str]]

    @property
    def definition(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


def schema(required: list[str], **properties) -> dict:
    return {"type": "object", "properties": properties, "required": required}


class ToolExecutor:
    def __init__(self, tools: list[Tool]):
        self.tools = {tool.name: tool for tool in tools}

    @property
    def definitions(self) -> list[dict]:
        return [tool.definition for tool in self.tools.values()]

    async def execute(self, name: str, arguments: dict) -> str:
        tool = self.tools.get(name)
        if tool is None:
            return f"[unknown tool {name}]"
        try:
            return await tool.run(arguments)
        except Exception as error:
            return f"ERROR: tool failed ({type(error).__name__}). Continue without it."


class Budget:
    def __init__(self, calls: int):
        self.remaining = calls

    def spend(self) -> bool:
        self.remaining -= 1
        return self.remaining >= 0


def skill_tools(repertoire: Repertoire) -> list[Tool]:
    async def load_skill(arguments: dict) -> str:
        name = str(arguments.get("name", "")).strip()
        identifier = repertoire.resolve(name)
        if identifier is None:
            return f"[no skill named '{name}'. Available: {', '.join(skill.identifier for skill in repertoire)}]"
        return repertoire.skills[identifier].body

    return [
        Tool(
            "load_skill",
            "Read the full text of one skill from the skill repertoire by its exact name.",
            schema(["name"], name={"type": "string", "description": "exact skill name from the skill index"}),
            load_skill,
        )
    ]


def shell_tool_group(sandbox: Path, note: str, timeout: int, fresh: bool = True) -> list[Tool]:
    budget = Budget(SHELL_TOOL_CALLS)
    root = sandbox.resolve()
    if fresh:
        shutil.rmtree(root, ignore_errors=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "env").mkdir(exist_ok=True)
    if note:
        text = fill(note, timeout=timeout, output_chars=f"{SHELL_OUTPUT_CHARS:,}")
        (root / "env" / "notes.md").write_text(text, encoding="utf-8")

    def inside(path: str) -> Path | None:
        target = (root / path).resolve()
        return target if target.is_relative_to(root) else None

    def budgeted(run: Callable[[dict], Awaitable[str]]) -> Callable[[dict], Awaitable[str]]:
        async def call(arguments: dict) -> str:
            return await run(arguments) if budget.spend() else BUDGET_EXHAUSTED

        return call

    async def bash(arguments: dict) -> str:
        command = str(arguments.get("command", "")).strip()
        if not command:
            return "ERROR: empty command."
        if any(blocked in command for blocked in BLOCKED_COMMANDS):
            return "ERROR: command not allowed."
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(root), "LANG": "C.UTF-8"},
            start_new_session=True,
        )

        async def finish() -> bytes:
            kept = bytearray()
            while chunk := await process.stdout.read(65536):
                if len(kept) < SHELL_OUTPUT_BYTES:
                    kept += chunk
            await process.wait()
            return bytes(kept)

        try:
            output = await asyncio.wait_for(finish(), timeout=timeout)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), REAP_SECONDS)
            return f"ERROR: command timed out ({timeout} s)."
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        text = output.decode("utf-8", "replace")[:SHELL_OUTPUT_CHARS]
        return f"[exit {process.returncode}]\n{text}" if text.strip() else f"[exit {process.returncode}] (no output)"

    async def read_file(arguments: dict) -> str:
        target = inside(str(arguments.get("path", "")))
        if target is None or not target.is_file():
            return "ERROR: no such file inside the scratch directory."
        return target.read_text(encoding="utf-8", errors="replace")[:FILE_CHARS]

    async def write_file(arguments: dict) -> str:
        target = inside(str(arguments.get("path", "")))
        if target is None:
            return "ERROR: path must be inside the scratch directory."
        content = str(arguments.get("content", ""))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} chars to {arguments.get('path')}"

    async def edit_file(arguments: dict) -> str:
        target = inside(str(arguments.get("path", "")))
        if target is None or not target.is_file():
            return "ERROR: no such file inside the scratch directory."
        old, new = str(arguments.get("old_text", "")), str(arguments.get("new_text", ""))
        text = target.read_text(encoding="utf-8", errors="replace")
        if not old or old not in text:
            return "ERROR: old_text not found in the file."
        target.write_text(text.replace(old, new, 1), encoding="utf-8")
        return f"edited {arguments.get('path')}"

    text = {"type": "string"}
    return [
        Tool(
            "bash",
            "Run a shell command in your scratch working directory (python3, grep, ls, cat, awk, jq available). "
            f"Use it to compute numbers, inspect env/ notes and maintain state/ files. {timeout} s timeout, output "
            f"truncated to {SHELL_OUTPUT_CHARS} chars.",
            schema(["command"], command=text),
            budgeted(bash),
        ),
        Tool(
            "read_file",
            "Read a file inside the scratch directory (e.g. env/notes.md).",
            schema(["path"], path=text),
            budgeted(read_file),
        ),
        Tool(
            "write_file",
            "Create or overwrite a file inside the scratch directory with the given content (keep state under state/).",
            schema(["path", "content"], path=text, content=text),
            budgeted(write_file),
        ),
        Tool(
            "edit_file",
            "Replace the first exact occurrence of old_text with new_text in a scratch file.",
            schema(["path", "old_text", "new_text"], path=text, old_text=text, new_text=text),
            budgeted(edit_file),
        ),
    ]
