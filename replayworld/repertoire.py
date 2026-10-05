from __future__ import annotations

import re
import shutil
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)
FIELD = re.compile(r"^\s*([A-Za-z_][\w-]*)\s*:\s*(.*)$")
WORD = re.compile(r"[a-z0-9]+")
UNSAFE = re.compile(r"[^\w-]+")
SUMMARY_CHARS = 220


@dataclass
class Skill:
    identifier: str
    condition: str
    body: str

    @classmethod
    def parse(cls, document: str, identifier: str = "") -> Skill:
        match = FRONTMATTER.match(document.strip())
        if not match:
            return cls(identifier=identifier, condition="", body=document.strip())
        header = {}
        for line in match.group(1).splitlines():
            entry = FIELD.match(line)
            if entry:
                header[entry.group(1)] = entry.group(2).strip().strip("\"'")
        return cls(
            identifier=UNSAFE.sub("_", header.get("name", identifier) or identifier),
            condition=header.get("description", ""),
            body=match.group(2).strip(),
        )

    def document(self) -> str:
        return f"---\nname: {self.identifier}\ndescription: {self.condition}\n---\n{self.body}\n"

    def summary(self) -> str:
        opening = next((line.strip("# ").strip() for line in self.body.splitlines() if line.strip("# ").strip()), "")
        return (self.condition or opening)[:SUMMARY_CHARS]

    def words(self) -> set[str]:
        return set(WORD.findall(f"{self.identifier} {self.condition} {self.body}".lower()))

    def merge(self, other: Skill, body_cap: int) -> Skill:
        present = {line.strip() for line in self.body.splitlines()}
        added = [line for line in other.body.splitlines() if line.strip() and line.strip() not in present]
        return Skill(self.identifier, self.condition, "\n".join([self.body, *added])[:body_cap])


@dataclass
class Edit:
    kind: str
    target: str
    skill: Skill | None = None
    rationale: str = ""
    evidence: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "target": self.target, "rationale": self.rationale, "evidence": self.evidence}


@dataclass
class Revision:
    edits: list[Edit] = field(default_factory=list)
    note: str = ""


def normalize(name: str) -> str:
    return name.strip().lower().replace("-", "_")


def stem(name: str, prefixes: tuple[str, ...]) -> str:
    name = normalize(name)
    for prefix in prefixes:
        name = name.removeprefix(prefix)
    return name


class Repertoire:
    def __init__(self, skills: Iterable[Skill] = ()):
        self.skills: dict[str, Skill] = {skill.identifier: skill for skill in skills}

    def __iter__(self) -> Iterator[Skill]:
        return iter(self.skills.values())

    def __len__(self) -> int:
        return len(self.skills)

    @classmethod
    def load(cls, directory: str | Path) -> Repertoire:
        if not Path(directory).is_dir():
            raise FileNotFoundError(f"no repertoire at {directory}")
        skills = []
        for document in sorted(Path(directory).glob("*/SKILL.md")):
            skills.append(Skill.parse(document.read_text(encoding="utf-8"), identifier=document.parent.name))
        if not skills:
            raise FileNotFoundError(f"no skills in {directory}")
        return cls(skills)

    def save(self, directory: str | Path) -> None:
        directory = Path(directory)
        if directory.exists():
            shutil.rmtree(directory)
        for skill in self:
            folder = directory / skill.identifier
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "SKILL.md").write_text(skill.document(), encoding="utf-8")

    def index(self) -> str:
        return "\n".join(f"- {skill.identifier} — {skill.summary()}" for skill in self)

    def bodies(self) -> str:
        return "\n\n".join(f"## Skill: {skill.identifier}\n{skill.body}" for skill in self)

    def resolve(self, name: str, prefixes: tuple[str, ...] = ()) -> str | None:
        if name in self.skills:
            return name
        for matches in (normalize, lambda identifier: stem(identifier, prefixes)):
            for identifier in self.skills:
                if matches(identifier) == matches(name):
                    return identifier
        return None

    def apply(self, revision: Revision) -> Repertoire:
        targets = {edit.target for edit in revision.edits}
        kept = [skill for skill in self if skill.identifier not in targets]
        written = [edit.skill for edit in revision.edits if edit.kind in ("create", "rewrite") and edit.skill]
        return Repertoire(kept + written)

    def consolidate(self, overlap: float, body_cap: int) -> Repertoire:
        merged = dict(self.skills)
        identifiers = list(merged)
        for position, first in enumerate(identifiers):
            for second in identifiers[position + 1 :]:
                if first not in merged or second not in merged:
                    continue
                shared = merged[first].words() & merged[second].words()
                smaller = min(len(merged[first].words()), len(merged[second].words()))
                if smaller and len(shared) / smaller > overlap:
                    kept, absorbed = sorted((first, second), key=lambda name: -len(merged[name].body))
                    merged[kept] = merged[kept].merge(merged.pop(absorbed), body_cap)
        return Repertoire(merged.values())
