from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .llm import LanguageModel, parse_json
from .prompts import prompt
from .repertoire import UNSAFE, Edit, Repertoire, Revision, Skill
from .traces import Trace, render_history

FIELD_CHARS = 250
QUOTED_OBSERVATIONS = 8
QUOTE_CHARS = 400
MIN_EVIDENCE_CHARS = 12
COMPARATOR_TOKENS = 2048
AGGREGATOR_TOKENS = 8192
REVISER_TOKENS = 8192
COMPARATOR_KEYS = ("content_diff", "behavioral_issues", "improvement_rules", "trajectory_quality")
AGGREGATOR_KEYS = ("issue_frequencies",)
REVISER_KEYS = ("updates", "no_change_reason")
STATED_SHARE = re.compile(r"\W*(\d+(?:\.\d+)?)\s*%")
EDIT_KINDS = {"add": "create", "update": "rewrite", "retire": "delete"}


@dataclass
class Discrepancy:
    trace_id: str
    t: int
    action: str
    prediction: str
    recorded: str
    content_diff: str = ""
    content_accuracy: str = ""
    missing_in_predicted: str = ""
    behavioral_issues: str = ""
    trajectory_quality: str = ""
    improvement_rules: str = ""

    def to_dict(self) -> dict:
        row = asdict(self)
        return {"id": row.pop("trace_id"), **row}


@dataclass
class DiscrepancySummary:
    cycle: int
    n_discrepancies: int
    n_quality: int
    behavioral_issues: list[str] = field(default_factory=list)
    attribute_issues: list[str] = field(default_factory=list)
    behavioral_suggestions: list[str] = field(default_factory=list)
    attribute_suggestions: list[str] = field(default_factory=list)
    causes: dict[str, float] = field(default_factory=dict)
    parsed: bool = False

    @property
    def empty(self) -> bool:
        return not (self.behavioral_issues or self.attribute_issues or self.causes)

    def to_dict(self) -> dict:
        return asdict(self)


def text_of(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(text_of(item) for item in value)
    return value if isinstance(value, str) else str(value)


def listed(value) -> list[str]:
    return [text_of(item) for item in ([value] if isinstance(value, str) else value or [])]


def share_of(value) -> float | None:
    percent = isinstance(value, str) and value.strip().endswith("%")
    try:
        share = float(value.strip().rstrip("%")) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, share / 100.0 if percent or share > 1.0 else share))


def grounded(evidence: str, recorded: str) -> bool:
    for quote in re.split(r"[\n\"“”]+", evidence):
        quote = " ".join(quote.split())
        if len(quote.replace(" ", "")) >= MIN_EVIDENCE_CHARS and quote in recorded:
            return True
    return False


async def ask(model: LanguageModel, request: str, max_tokens: int, keys: tuple[str, ...]) -> dict | None:
    answer = parse_json(await model.complete(request, max_tokens=max_tokens))
    return answer if isinstance(answer, dict) and any(key in answer for key in keys) else None


class Comparator:
    def __init__(self, model: LanguageModel, environment: str):
        self.model = model
        self.environment = environment

    async def compare(self, trace: Trace, t: int, prediction: str) -> Discrepancy | None:
        recorded = trace.recorded(t)
        request = prompt(
            f"{self.environment}/comparator",
            t=t,
            t_plus_1=t + 1,
            query=trace.task,
            history=render_history(trace, t),
            action_at_t=trace.actions[t],
            predicted_obs=prediction,
            real_obs=recorded,
        )
        answer = await ask(self.model, request, COMPARATOR_TOKENS, COMPARATOR_KEYS)
        if not isinstance(answer, dict):
            return None
        return Discrepancy(
            trace_id=trace.trace_id,
            t=t,
            action=trace.actions[t],
            prediction=prediction,
            recorded=recorded,
            content_diff=text_of(answer.get("content_diff")),
            content_accuracy=text_of(answer.get("content_accuracy")),
            missing_in_predicted=text_of(answer.get("missing_in_predicted")),
            behavioral_issues=text_of(answer.get("behavioral_issues")),
            trajectory_quality=text_of(answer.get("trajectory_quality")).strip().lower(),
            improvement_rules=text_of(answer.get("improvement_rules")),
        )


class Aggregator:
    def __init__(self, model: LanguageModel, environment: str):
        self.model = model
        self.environment = environment

    async def aggregate(self, discrepancies: list[Discrepancy], cycle: int) -> DiscrepancySummary:
        summary = DiscrepancySummary(
            cycle=cycle,
            n_discrepancies=len(discrepancies),
            n_quality=sum(item.trajectory_quality in ("high", "medium") for item in discrepancies),
        )
        if not discrepancies:
            return summary
        request = prompt(
            f"{self.environment}/aggregator", n=len(discrepancies), discrepancies_text=self.render(discrepancies)
        )
        answer = await ask(self.model, request, AGGREGATOR_TOKENS, AGGREGATOR_KEYS)
        frequencies = answer.get("issue_frequencies") if isinstance(answer, dict) else None
        if not isinstance(frequencies, dict):
            return summary
        summary.behavioral_issues = listed(answer.get("behavioral_issues"))
        summary.attribute_issues = listed(answer.get("attribute_issues"))
        summary.behavioral_suggestions = listed(answer.get("behavioral_suggestions"))
        summary.attribute_suggestions = listed(answer.get("attribute_suggestions"))
        for cause, value in frequencies.items():
            share = share_of(value)
            if share is not None:
                summary.causes[text_of(cause)] = share
        summary.parsed = bool(summary.causes) or not frequencies
        return summary

    @staticmethod
    def render(discrepancies: list[Discrepancy]) -> str:
        blocks = []
        for number, item in enumerate(discrepancies):
            lines = [f"--- Feedback {number} (quality={item.trajectory_quality}) ---"]
            for name in (
                "content_diff",
                "content_accuracy",
                "missing_in_predicted",
                "behavioral_issues",
                "improvement_rules",
            ):
                value = getattr(item, name)
                if value:
                    lines.append(f"  {name}: {value[:FIELD_CHARS]}")
            blocks.append("\n".join(lines))
        return "\n".join(blocks)


class Reviser:
    def __init__(
        self,
        model: LanguageModel,
        environment: str,
        frequency_threshold: float,
        skill_body_cap: int,
        max_deletes: int,
        skill_prefixes: tuple[str, ...] = (),
    ):
        self.model = model
        self.environment = environment
        self.frequency_threshold = frequency_threshold
        self.skill_body_cap = skill_body_cap
        self.max_deletes = max_deletes
        self.skill_prefixes = skill_prefixes

    async def revise(
        self, repertoire: Repertoire, summary: DiscrepancySummary, batch: list[tuple[str, str]]
    ) -> Revision:
        if summary.empty:
            return Revision(note="empty discrepancy summary")
        causes = {cause: share for cause, share in summary.causes.items() if share >= self.frequency_threshold}
        if summary.causes and not causes:
            return Revision(note="no cause passes the frequency threshold")
        issues = [f"[BEHAVIORAL] {item}" for item in self.frequent(summary.behavioral_issues)]
        issues += [f"[ATTRIBUTE] {item}" for item in self.frequent(summary.attribute_issues)]
        suggestions = [f"[BEHAVIORAL] {item}" for item in summary.behavioral_suggestions]
        suggestions += [f"[ATTRIBUTE] {item}" for item in summary.attribute_suggestions]
        request = prompt(
            f"{self.environment}/reviser",
            skills_content=self.render(repertoire),
            cycle=summary.cycle,
            batch_size=summary.n_discrepancies,
            n_valid=summary.n_quality,
            common_issues_text="\n".join(f"- {item}" for item in issues) or "- No common issues identified",
            suggestions_text="\n".join(f"- {item}" for item in suggestions) or "- No specific suggestions",
            frequencies_text="\n".join(f"- {cause}: {share:.0%}" for cause, share in causes.items())
            or "- No frequency data",
            recorded_text=self.quote(batch),
            max_deletes=self.max_deletes,
        )
        answer = await ask(self.model, request, REVISER_TOKENS, REVISER_KEYS)
        if not isinstance(answer, dict):
            return Revision(note="unparsable revision")
        return self.revision(repertoire, answer, batch)

    def frequent(self, issues: list[str]) -> list[str]:
        kept = []
        for issue in issues:
            stated = STATED_SHARE.match(issue)
            if stated is None or float(stated.group(1)) / 100.0 >= self.frequency_threshold:
                kept.append(issue)
        return kept

    @staticmethod
    def render(repertoire: Repertoire) -> str:
        return (
            "\n---\n\n".join(
                f"### Skill folder: {skill.identifier}/\nName: {skill.identifier}\n"
                f"Description: {skill.condition}\nContent:\n{skill.body}\n"
                for skill in repertoire
            )
            or "(No skills yet)"
        )

    @staticmethod
    def quote(batch: list[tuple[str, str]]) -> str:
        lines = [
            f"- Action: {action}\n  Real observation: {recorded[:QUOTE_CHARS]}"
            for action, recorded in batch[:QUOTED_OBSERVATIONS]
        ]
        return "\n".join(lines) or "- (none)"

    def revision(self, repertoire: Repertoire, answer: dict, batch: list[tuple[str, str]]) -> Revision:
        edits: list[Edit] = []
        targets: set[str] = set()
        written: set[str] = set()
        deletes = 0
        recorded = " ".join(" ".join(observation.split()) for _, observation in batch)
        for update in answer.get("updates") or []:
            if not isinstance(update, dict):
                continue
            kind = EDIT_KINDS.get(text_of(update.get("action")).strip().lower())
            name = UNSAFE.sub("_", text_of(update.get("skill_name")).strip())
            content = text_of(update.get("content"))
            if kind is None or not name:
                continue
            existing = repertoire.resolve(name, () if kind == "create" else self.skill_prefixes)
            target = existing or name
            if target in targets:
                continue
            rationale = text_of(update.get("rationale"))
            if kind == "delete":
                last = len(repertoire) - deletes <= 1
                if existing is None or last or deletes >= self.max_deletes or not grounded(content, recorded):
                    continue
                edits.append(Edit("delete", existing, rationale=rationale, evidence=content))
                deletes += 1
            else:
                skill = Skill.parse(content, identifier=name)
                skill.body = skill.body[: self.skill_body_cap]
                if not skill.body:
                    continue
                if skill.identifier in (set(repertoire.skills) | written) - {target}:
                    skill.identifier = target
                if skill.identifier in written:
                    continue
                edits.append(Edit("rewrite" if existing else "create", target, skill=skill, rationale=rationale))
                written.add(skill.identifier)
            targets.add(target)
        return Revision(edits=edits, note=text_of(answer.get("no_change_reason")))
