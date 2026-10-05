from __future__ import annotations

import re

from .common import Environment

SHELL_ERROR = re.compile(
    r"Permission denied|No such file or directory|command not found|syntax error|Traceback \(most recent"
    r"|\b[Cc]annot\b|Operation not permitted|does not exist|[Ii]nvalid (?:option|argument|group|number|command|input)"
    r"|\bnot found\b|[Cc]ommand timed out|which: no \S+ in|Failed to|^(?:[\w./-]+: )?[Ff]ailed to\b|Not root|Try ['`]\S+ --help"
    r"|^Usage: |[Ii]llegal option|unrecognized option|No space left|Read-only file system|Not a directory|Is a directory"
    r"|missing operand|[Nn]o such (?:user|group|process)|does not have|is not (?:installed|available|allowed)"
    r"|a terminal is required|a password is required|no tty present|[Nn]eed password|[Pp]asswordless sudo|Command blocked"
    r"|\bnot (?:installed|active|present|available|running|recognized|supported)\b|No journal files|[\w./-]+: invalid user"
    r"|^(?:[\w./-]+: )?[Ee]rror: \S|errors in crontab|no matching \w+ found",
    re.M,
)
OUTPUT_HEADER = re.compile(r"^\s*The output of the OS\s*:\s*", re.I)
OUTPUT = "output"
ERROR = "error"


class OperatingSystem(Environment):
    name = "os"

    def classify(self, text: str, previous: str) -> str:
        body = OUTPUT_HEADER.sub("", text, count=1).strip()
        return ERROR if SHELL_ERROR.search(body) else OUTPUT
