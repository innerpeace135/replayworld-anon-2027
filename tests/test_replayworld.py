from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import re
import subprocess
import sys
import types

import httpx
import numpy as np
import pytest
from openai import APIConnectionError, AsyncOpenAI

from collect import browsergym, common, mind2web, shoppingbench, split, toolbench
from replayworld.config import ROOT, ClusterConfig, ModelConfig, load_config
from replayworld.environments import ENVIRONMENTS
from replayworld.environments.webshop import WebShop
from replayworld.evaluate import CRITERIA, env_reaction, evaluate, normalize_action, parse_rating, rescale
from replayworld.evolve import evolve
from replayworld.harness.agentic_turn import agentic_turn, extract_observation
from replayworld.harness.tools import Tool, ToolExecutor, schema, shell_tool_group
from replayworld.llm import LanguageModel, Reply, ToolCall, preflight, room_in_context, with_scheme
from replayworld.lpf import cold_start_ranking, learnability, top
from replayworld.mcca import MCCA, Arbiter
from replayworld.repertoire import Edit, Repertoire, Revision, Skill
from replayworld.roles import Aggregator, Comparator, Discrepancy, DiscrepancySummary, Reviser, ask, share_of
from replayworld.sbs import Clusters, build_clusters, sbs
from replayworld.simulate import simulate
from replayworld.simulator import Prediction, Simulator
from replayworld.traces import Trace, load_traces, render_history
from replayworld.world_model import WorldModel

PREDICTION = (
    '<predicted_observation>[{"product_id": "3986206075", "title": "sample", "price": 9.5}]</predicted_observation>'
)
DISCREPANCY = {
    "content_diff": "prices differ",
    "content_accuracy": "plausible",
    "missing_in_predicted": "seller rating",
    "behavioral_issues": "none",
    "trajectory_quality": "medium",
    "improvement_rules": "list the seller rating",
}
SUMMARY = {
    "behavioral_issues": ["60% of predictions list unrelated products"],
    "attribute_issues": [],
    "behavioral_suggestions": ["match the query keywords"],
    "attribute_suggestions": [],
    "issue_frequencies": {"unrelated_products": 0.6},
}


class ScriptedModel:
    def __init__(self):
        self.revisions = 0
        self.tool_choices: list[str] = []
        self.offered: set[str] = set()
        self.summary = json.dumps(SUMMARY)

    async def reply(self, messages, tools=None, **decoding) -> Reply:
        opening = messages[0]["content"]
        self.offered.update(tool["function"]["name"] for tool in tools or [])
        if opening == "ping":
            return Reply("pong")
        if opening.startswith("You are auditing"):
            criterion = re.search(r'"(format|consistency|factuality)": <1-5>', opening).group(1)
            return Reply(json.dumps({criterion: {"format": 5, "consistency": 4, "factuality": 3}[criterion]}))
        if opening.startswith("You decide whether two agent actions"):
            return Reply(json.dumps({"equivalent": True, "reason": "same target"}))
        if opening.startswith("You are the agent operating"):
            return Reply('find_product({"q": "next"})')
        if opening.startswith("You are an environment simulator"):
            self.tool_choices.append("auto" if tools else "none")
            opened = any(message["role"] == "tool" for message in messages)
            if tools and not opened:
                name = re.search(r"^- (\S+) —", opening, re.M).group(1)
                return Reply("", [ToolCall("call-1", "load_skill", {"name": name})])
            return Reply(PREDICTION)
        if opening.startswith("You are evaluating"):
            return Reply(json.dumps(DISCREPANCY))
        if opening.startswith("You are analyzing a batch"):
            return Reply(self.summary)
        self.revisions += 1
        name = f"cnt_scripted_rule_{self.revisions}"
        body = f"---\nname: {name}\ndescription: USE WHEN: scripted case {self.revisions}.\n---\n# Rule {self.revisions}\n\nUnique body {self.revisions}."
        return Reply(
            json.dumps({"updates": [{"action": "add", "skill_name": name, "rationale": "scripted", "content": body}]})
        )

    async def complete(self, prompt, **decoding) -> str:
        return (await self.reply([{"role": "user", "content": prompt}], **decoding)).text


class HashEmbedder:
    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = []
        for text in texts:
            seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
            vector = np.random.default_rng(seed).normal(size=16)
            vectors.append(vector / np.linalg.norm(vector))
        return np.stack(vectors).astype(np.float32)


def skill(identifier: str, body: str = "body") -> Skill:
    return Skill(identifier, f"USE WHEN: {identifier}", body)


def trace(reward: float, length: int) -> Trace:
    return Trace("t", "task", ["o"] * (length + 1), ["a"] * length, reward)


def test_config_loads_plain_values_and_names_bad_keys(tmp_path):
    config = load_config("configs/sample.yaml")
    assert config.simulator.api_base == "localhost:8000/v1"
    assert with_scheme(config.simulator.api_base).split("://") == ["http", "localhost:8000/v1"]
    assert config.data.output_dir == "outputs/sample"
    assert config.harness.capabilities == ["coding"] and config.harness.replay_capabilities == []
    assert config.judge.reasoning_effort == "medium" and config.judge.api_base == ""
    stale = tmp_path / "stale.yaml"
    stale.write_text(config_text("configs/sample.yaml").replace("  reply_cap: 4", "  coding: true"))
    with pytest.raises(ValueError, match="unknown HarnessConfig keys"):
        load_config(str(stale))
    bare = tmp_path / "bare.yaml"
    bare.write_text(config_text("configs/sample.yaml").replace("  model: Qwen/Qwen3.5-397B-A17B\n", "", 1))
    with pytest.raises(ValueError, match="ModelConfig needs model"):
        load_config(str(bare))


def config_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_language_model_reduces_the_budget_to_fit_the_context_window():
    overflow = (
        "'max_tokens' or 'max_completion_tokens' is too large: 4096. This model's maximum context length is "
        "131072 tokens and your request has 130072 input tokens (4096 > 131072 - 130072)."
    )
    call = {"id": "c1", "type": "function", "function": {"name": "load_skill", "arguments": '{"name": "obs-format"}'}}
    message = {"role": "assistant", "content": " a page ", "tool_calls": [call]}
    completion = {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [{"index": 0, "finish_reason": "tool_calls", "message": message}],
    }
    bodies = []

    def serve(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        if bodies[-1]["max_tokens"] > 1000:
            return httpx.Response(400, json={"error": {"message": overflow, "type": "BadRequestError", "code": 400}})
        return httpx.Response(200, json=completion)

    model = LanguageModel(ModelConfig("m", api_base="localhost:8000/v1", retries=0))
    model.client = AsyncOpenAI(
        base_url=with_scheme("localhost:8000/v1"),
        api_key="EMPTY",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(serve)),
    )
    tools = [Tool("load_skill", "open a skill", schema(["name"], name={"type": "string"}), None).definition]
    reply = asyncio.run(model.reply([{"role": "user", "content": "x"}], tools=tools))
    assert [body["max_tokens"] for body in bodies] == [4096, 1000]
    assert bodies[0]["chat_template_kwargs"] == {"enable_thinking": False} and bodies[0]["temperature"] == 0.0
    assert (reply.text, reply.tool_calls) == ("a page", [ToolCall("c1", "load_skill", {"name": "obs-format"})])
    released = "maximum context length is 8192 tokens. However, you requested 9000 tokens (5000 in the messages, 4000"
    assert (room_in_context(overflow), room_in_context(released), room_in_context("bad request")) == (1000, 3192, None)


def test_update_operator_removes_targets_and_adds_written_skills():
    repertoire = Repertoire([skill("a"), skill("b"), skill("c")])
    revision = Revision(
        [
            Edit("rewrite", "a", skill("cnt_a", "rewritten")),
            Edit("delete", "b"),
            Edit("create", "d", skill("d")),
        ]
    )
    updated = repertoire.apply(revision)
    assert [item.identifier for item in updated] == ["c", "cnt_a", "d"]
    assert updated.skills["cnt_a"].body == "rewritten"
    assert [item.identifier for item in repertoire] == ["a", "b", "c"]


def test_consolidation_merges_overlapping_skills_into_the_longer_one():
    shared = "search results list relevant products with realistic prices"
    repertoire = Repertoire(
        [
            skill("short", shared + "\nshow ratings"),
            skill("long", shared + " and pagination"),
            skill("other", "error pages state the failure"),
        ]
    )
    merged = repertoire.consolidate(0.7, 5000)
    assert [item.identifier for item in merged] == ["long", "other"]
    assert merged.skills["long"].body.splitlines() == [shared + " and pagination", shared, "show ratings"]
    assert len(repertoire.consolidate(0.7, 70).skills["long"].body) == 70


def test_repertoire_round_trip_and_name_resolution(tmp_path):
    repertoire = Repertoire([skill("obs-format"), skill("cnt_reflect_user_actions")])
    repertoire.save(tmp_path / "skills")
    loaded = Repertoire.load(tmp_path / "skills")
    assert sorted(loaded.index().splitlines()) == sorted(repertoire.index().splitlines())
    assert loaded.skills["obs-format"].document() == repertoire.skills["obs-format"].document()
    assert loaded.resolve("obs_format") == "obs-format"
    assert loaded.resolve("reflect_user_actions") is None
    assert loaded.resolve("reflect_user_actions", WebShop.skill_prefixes) == "cnt_reflect_user_actions"
    assert loaded.resolve("missing") is None
    assert Repertoire([skill("search-results-pattern")]).resolve("empty_search_results_pattern") is None


def test_sbs_draws_distinct_traces_and_reaches_small_clusters():
    clusters = Clusters([list(range(0, 90)), list(range(90, 100))], [])
    rng = random.Random(0)
    drawn = sbs(range(100), clusters, 40, rng)
    assert len(drawn) == len(set(drawn)) == 40
    assert sum(index >= 90 for index in drawn) > 4
    assert sorted(sbs(range(95, 100), clusters, 40, rng)) == [95, 96, 97, 98, 99]


def test_clusters_cover_every_replay_trace():
    traces = [Trace(f"t{index}", f"task {index % 7} about item {index}", ["o", "o"], ["a"]) for index in range(60)]
    clusters = build_clusters(traces, HashEmbedder(), ClusterConfig(first_level=4, leaves_per_node=2, min_split_size=6))
    assert clusters.trace_ids == [item.trace_id for item in traces]
    assert sorted(index for cluster in clusters.members for index in cluster) == list(range(60))


def test_learnability_prefers_rewarded_traces_wrong_at_one_step():
    rewards = np.array([1.0, 1.0, 0.0])
    max_errors = np.array([0.9, 0.1, 0.9])
    mean_errors = np.array([0.2, 0.1, 0.8])
    scores = learnability(rewards, max_errors, mean_errors)
    assert top(scores, 1, random.Random(0)) == [0]


def test_cold_start_ranking_scores_reward_band_and_typical_length():
    traces = [trace(0.5, 5), trace(1.0, 5), trace(0.5, 1), trace(1.0, 1), trace(0.0, 9)]
    assert cold_start_ranking(traces).tolist() == [2.0, 1.0, 1.0, 0.0, 0.0]


def test_mcca_keeps_the_earliest_best_cycle_and_stops_at_patience():
    mcca = MCCA(None, None, None, None, [], 300, patience=2, seed=0)
    stops = [mcca.select(cycle, score) for cycle, score in enumerate([50.0, 60.0, 60.0, -math.inf], start=1)]
    assert stops == [False, False, False, True]
    assert (mcca.winner, mcca.best) == (2, 60.0)


def test_arbitration_score_averages_rule_checks_and_discrepancy_score():
    arbiter = Arbiter(WebShop())
    summary = DiscrepancySummary(1, 4, 3, causes={"a": 0.4, "b": 0.2})
    assert arbiter.discrepancy_score(summary) == 50 * 0.7 + 25 * 0.75 + 25 * 0.8
    recorded = '[{"product_id": "100", "price": 3}]'
    traces = [Trace("t", "task", ["", recorded], ["a"])] * 2
    predictions = [Prediction(recorded, True), Prediction("", False)]
    assert arbiter.rule_check_score(predictions, traces, [0, 0]) == 50.0


def test_aggregator_reads_shares_in_any_notation():
    assert [share_of(value) for value in (0.4, "40%", 45, "0.25", "many", None)] == [0.4, 0.4, 0.45, 0.25, None, None]
    model = ScriptedModel()
    sample = load_traces(ROOT / "data/samples/replay_traces.jsonl")[0]
    discrepancy = Discrepancy(sample.trace_id, 0, sample.actions[0], "prediction", sample.recorded(0))
    model.summary = json.dumps({"behavioral_issues": "prices are too high", "issue_frequencies": {"prices": "60%"}})
    summary = asyncio.run(Aggregator(model, "webshop").aggregate([discrepancy], 1))
    assert (summary.parsed, summary.causes, summary.behavioral_issues) == (
        True,
        {"prices": 0.6},
        ["prices are too high"],
    )
    model.summary = json.dumps({"issue_frequencies": {"prices": "often"}})
    assert not asyncio.run(Aggregator(model, "webshop").aggregate([discrepancy], 1)).parsed
    assert asyncio.run(ask(ScriptedModel(), "a revision request", 16, ("issue_frequencies",))) is None
    assert "updates" in asyncio.run(ask(ScriptedModel(), "a revision request", 16, ("updates",)))


def test_comparator_reads_the_logged_history():
    class Recorder(ScriptedModel):
        async def complete(self, prompt, **decoding) -> str:
            self.request = prompt
            return json.dumps(DISCREPANCY)

    model = Recorder()
    sample = Trace("t", "task", ["start page", "first result", "second result"], ["search", "next page"])
    discrepancy = asyncio.run(Comparator(model, "webshop").compare(sample, 1, "a predicted page"))
    assert "### Step 1\nACTION: search\nOBSERVATION: first result" in model.request
    assert "Agent's action after step 1: next page" in model.request and "second result" in model.request
    assert (discrepancy.t, discrepancy.recorded, discrepancy.trajectory_quality) == (1, "second result", "medium")


def test_frequency_threshold_keeps_rare_causes_from_the_reviser():
    class Recorder(ScriptedModel):
        async def complete(self, prompt, **decoding) -> str:
            self.request = prompt
            return json.dumps({"updates": []})

    summary = DiscrepancySummary(
        1,
        10,
        8,
        behavioral_issues=["60% of predictions list unrelated products", "5% of predictions omit the price"],
        causes={"unrelated_products": 0.6, "missing_price": 0.05},
    )
    model = Recorder()
    repertoire = Repertoire([skill("obs-format")])
    asyncio.run(Reviser(model, "webshop", 0.10, 5000, 2).revise(repertoire, summary, [("search", "a real page")]))
    assert "unrelated products" in model.request and "unrelated_products: 60%" in model.request
    assert "omit the price" not in model.request and "missing_price" not in model.request
    assert "- Action: search\n  Real observation: a real page" in model.request
    asyncio.run(Reviser(model, "webshop", 0.0, 5000, 2).revise(repertoire, summary, []))
    assert "omit the price" in model.request and "missing_price: 5%" in model.request
    rare = DiscrepancySummary(1, 10, 8, causes={"missing_price": 0.05})
    revision = asyncio.run(Reviser(model, "webshop", 0.10, 5000, 2).revise(repertoire, rare, []))
    assert revision.note == "no cause passes the frequency threshold"


def test_arbitration_pass_without_a_summary_returns_no_score():
    model = ScriptedModel()
    environment = WebShop()
    simulator = Simulator(model, environment, load_config("configs/sample.yaml").harness)
    traces = load_traces(ROOT / "data/samples/arbitration_traces.jsonl")
    roles = (Comparator(model, environment.name), Aggregator(model, environment.name))
    mcca = MCCA(simulator, *roles, Arbiter(environment), traces, 4, patience=5, seed=0)
    repertoire = Repertoire([skill("obs-format")])
    scored = asyncio.run(mcca.arbitrate(repertoire, 1))
    model.summary = "no recurring cause could be extracted"
    failed = asyncio.run(mcca.arbitrate(repertoire, 2))
    assert 0.0 < scored <= 100.0 and failed == -math.inf
    assert mcca.history[0]["arbitration_score"] == scored
    assert mcca.history[1] == {"cycle": 2, "arbitration_score": None, "discrepancies": 4}


def test_role_calls_raise_on_api_errors():
    class Unreachable(ScriptedModel):
        async def complete(self, prompt, **decoding) -> str:
            raise APIConnectionError(request=httpx.Request("POST", "/v1/chat/completions"))

    model = Unreachable()
    sample = load_traces(ROOT / "data/samples/replay_traces.jsonl")[0]
    with pytest.raises(APIConnectionError):
        asyncio.run(Comparator(model, "webshop").compare(sample, 0, "a predicted observation"))


def test_agentic_turn_disables_tools_in_the_last_reply():
    choices = []

    class Caller:
        async def reply(self, messages, tools=None, **decoding):
            choices.append("tools" if tools else messages[-1]["content"])
            if tools:
                return Reply("", [ToolCall("id", "echo", {})])
            return Reply("<predicted_observation>final page</predicted_observation>")

    async def echo(arguments):
        return "ok"

    executor = ToolExecutor([Tool("echo", "echo", schema([]), echo)])
    turn = asyncio.run(agentic_turn(Caller(), [{"role": "user", "content": "x"}], executor, 4))
    assert choices == ["tools", "tools", "tools", "Tools are disabled for this reply. Output the next observation now."]
    assert (turn.prediction, turn.replies, turn.tool_calls) == ("final page", 4, ["echo"] * 3)
    assert extract_observation("no block") == "no block"


def test_single_reply_instance_uses_no_tools():
    model = ScriptedModel()
    simulator = Simulator(model, WebShop(), load_config("configs/sample.yaml").harness)
    repertoire = Repertoire([skill("obs-format")])
    sample = load_traces(ROOT / "data/samples/replay_traces.jsonl")[0]
    prediction = asyncio.run(simulator.predict(sample, 0, repertoire, single_reply=True))
    assert (prediction.replies, prediction.tool_calls, model.tool_choices) == (1, [], ["none"])
    turn = asyncio.run(simulator.predict(sample, 1, repertoire))
    assert (turn.replies, turn.tool_calls, turn.parsed) == (2, ["load_skill"], True)


def test_file_tools_stay_inside_the_sandbox(tmp_path):
    executor = ToolExecutor(shell_tool_group(tmp_path / "sandbox", "shell note", timeout=10))

    def run(name: str, **arguments) -> str:
        return asyncio.run(executor.execute(name, arguments))

    assert run("read_file", path="env/notes.md") == "shell note"
    assert run("write_file", path="state/total.txt", content="3 items") == "wrote 7 chars to state/total.txt"
    assert run("edit_file", path="state/total.txt", old_text="3", new_text="4") == "edited state/total.txt"
    assert run("bash", command="cat state/total.txt") == "[exit 0]\n4 items"
    assert run("write_file", path="../outside.txt", content="x").startswith("ERROR")
    assert run("read_file", path="/etc/hostname").startswith("ERROR")
    assert not (tmp_path / "outside.txt").exists()
    assert [tool["function"]["name"] for tool in executor.definitions] == [
        "bash",
        "read_file",
        "write_file",
        "edit_file",
    ]


def test_shell_tool_group_shares_one_budget_and_stops_runaway_commands(tmp_path):
    executor = ToolExecutor(shell_tool_group(tmp_path / "sandbox", "", timeout=1))

    def run(name: str, **arguments) -> str:
        return asyncio.run(executor.execute(name, arguments))

    assert run("bash", command="sleep 30 & sleep 30") == "ERROR: command timed out (1 s)."
    assert [run("read_file", path="state/none.txt") for _ in range(7)] == [
        "ERROR: no such file inside the scratch directory."
    ] * 7
    assert run("bash", command="echo late") == "[tool budget exhausted. Output the observation now.]"
    (tmp_path / "sandbox" / "state" / "kept.txt").write_text("from an earlier step of a free run")
    shell_tool_group(tmp_path / "sandbox", "", timeout=1, fresh=False)
    assert (tmp_path / "sandbox" / "state" / "kept.txt").exists()
    shell_tool_group(tmp_path / "sandbox", "", timeout=1)
    assert not (tmp_path / "sandbox" / "state" / "kept.txt").exists()


def test_bash_tool_bounds_its_output_and_blocks_crontab(tmp_path):
    executor = ToolExecutor(shell_tool_group(tmp_path / "sandbox", "", timeout=20))
    flood = asyncio.run(executor.execute("bash", {"command": "head -c 3000000 /dev/zero | tr '\\0' a"}))
    assert flood.startswith("[exit 0]\naaaa") and len(flood) < 4100
    assert asyncio.run(executor.execute("bash", {"command": "crontab -l"})) == "ERROR: command not allowed."
    asyncio.run(executor.execute("bash", {"command": "sleep 30 > /dev/null 2>&1 & echo started"}))
    assert "sleep 30" not in subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
    assert with_scheme("api.example.net/v1").split("://") == ["https", "api.example.net/v1"]


def test_simulation_with_the_coding_capability(tmp_path):
    config = load_config("configs/sample.yaml")
    config.data.output_dir = str(tmp_path)
    model = ScriptedModel()
    rows = asyncio.run(
        simulate(config, "data/samples/arbitration_traces.jsonl", config.repertoire.selected, 4, False, 0, model=model)
    )
    assert len(rows) == 4 and all(row["parsed"] for row in rows)
    assert all(row["tool_calls"] == ["load_skill"] and row["replies"] == 2 for row in rows)
    assert {"load_skill", "bash", "read_file", "write_file", "edit_file"} == model.offered
    traces = load_traces(ROOT / "data/samples/arbitration_traces.jsonl")
    assert [row["id"] for row in rows] == [traces[index].trace_id for index in (0, 5, 10, 15)]
    assert len(read_rows(tmp_path / "simulate" / "predictions.jsonl")) == 4
    simulator = Simulator(model, WebShop(), config.harness)
    sample = load_traces(ROOT / "data/samples/arbitration_traces.jsonl")[0]
    simulator.tool_executor(sample, Repertoire(), ("coding",), True)
    folder = simulator.sandbox(sample)
    assert (folder / "env" / "notes.md").is_file()
    assert sample.trace_id not in str(folder) and ROOT not in folder.parents


def read_rows(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_judge_helpers_follow_the_printed_definitions():
    assert [rescale(r) for r in (None, 1, 2, 3, 4, 5)] == [None, 0.0, 25.0, 50.0, 75.0, 100.0]
    assert parse_rating('{"format": 4, "issues": [], "note": ""}', "format") == 4
    assert parse_rating('{"format": 0}', "format") is None and parse_rating('{"format": true}', "format") is None
    assert (
        parse_rating('text before {"consistency": 2, "violations": [{"item": 1, "evidence": "x"}', "consistency") == 2
    )
    assert parse_rating("no rating here", "factuality") is None
    assert normalize_action(" Click[B0X]  ") == "click[b0x]"
    assert normalize_action("Thought: go\nAction: search\nAction Input: {}\nextra") == "action:search action input: {}"
    pairs = [("results_page", "results_page")] * 4 + [("product_page", "product_page"), ("product_page", "receipt")]
    assert env_reaction(pairs) == 100.0 * (0.75 - 0.5) / 0.5
    assert env_reaction([("results_page", "results_page"), ("empty", "empty")]) is None
    assert env_reaction([("results_page", "product_page"), ("product_page", "results_page")]) == 0.0
    sample = Trace("t", "task", ["o0", "o1", "o2"], ["a0", "a1"])
    assert render_history(sample, 1).splitlines() == [
        "### Step 0 (initial observation, before the first action)",
        "OBSERVATION: o0",
        "### Step 1",
        "ACTION: a0",
        "OBSERVATION: o1",
    ]


def test_evaluation_scores_the_six_criteria(tmp_path):
    config = load_config("configs/sample.yaml")
    config.data.output_dir = str(tmp_path)
    rows = [json.loads(line) for line in (ROOT / "data/samples/arbitration_traces.jsonl").read_text().splitlines()[:6]]
    rows[0]["final"] = rows[1]["final"] = True
    rows[2]["free_running"] = rows[3]["free_running"] = True
    rows[4]["steps"][-1]["observation"] = "[]"
    test_file = tmp_path / "test.jsonl"
    test_file.write_text("".join(json.dumps(row) + "\n" for row in rows))
    model = ScriptedModel()
    report = asyncio.run(evaluate(config, str(test_file), config.repertoire.selected, model, model, model, model))
    scores = report["scores"]
    assert tuple(scores) == CRITERIA and report["traces"] == 6
    assert scores["Format"] == 100.0 and scores["Consistency"] == 75.0 and scores["Factuality"] == 50.0
    assert scores["ActionPreserve"] == 100.0 and report["action_preserve_ceiling"] == 100.0
    assert scores["LongHorizon"] == 62.5 and scores["EnvReaction"] == 0.0
    assert report["coverage"] == {
        "Format": 6,
        "EnvReaction": 6,
        "Consistency": 6,
        "Factuality": 6,
        "LongHorizon": 2,
        "ActionPreserve": 4,
    }
    records = read_rows(tmp_path / "evaluate" / "predictions.jsonl")
    assert len(records) == 6 and sum(record["preserved"] is None for record in records) == 2
    assert [record["LongHorizon"] for record in records] == [None, None, 62.5, 62.5, None, None]
    assert [record["recorded_type"] for record in records] == ["result"] * 4 + ["empty_result_or_error", "result"]
    assert json.loads((tmp_path / "evaluate" / "scores.json").read_text())["traces"] == 6
    rows[4]["steps"][-1]["observation"] = rows[5]["steps"][-1]["observation"]
    test_file.write_text("".join(json.dumps(row) + "\n" for row in rows[4:]))
    partial = asyncio.run(evaluate(config, str(test_file), config.repertoire.selected, model, model, model, model))
    assert partial["scores"]["EnvReaction"] is None and partial["coverage"]["EnvReaction"] == 2


def test_a_failed_request_stops_the_run(tmp_path):
    config = load_config("configs/sample.yaml")
    config.data.output_dir = str(tmp_path)
    rows = [json.loads(line) for line in (ROOT / "data/samples/arbitration_traces.jsonl").read_text().splitlines()[:2]]
    test_file = tmp_path / "test.jsonl"
    test_file.write_text("".join(json.dumps(row) + "\n" for row in rows))

    class Down(ScriptedModel):
        async def reply(self, messages, tools=None, **decoding) -> Reply:
            if messages[0]["content"].startswith("You are an environment simulator"):
                raise APIConnectionError(request=httpx.Request("POST", "/v1/chat/completions"))
            return await super().reply(messages, tools=tools, **decoding)

    model = Down()
    with pytest.raises(APIConnectionError):
        asyncio.run(evaluate(config, str(test_file), config.repertoire.selected, model, model, model, model))
    with pytest.raises(APIConnectionError):
        WorldModel(model=model).step("a task", [""], ["search"])


def test_webshop_response_types_and_rule_checks():
    environment = WebShop()
    results = "Instruction: [SEP] x [SEP] Back to Search [SEP] Page 1 (Total results: 50) [SEP] Next > [SEP] B09PKV4GR5 [SEP] Kit [SEP] $9.29"
    item = "Instruction: [SEP] x [SEP] Back to Search [SEP] < Prev [SEP] Kit [SEP] Price: $9.29 [SEP] Buy Now"
    assert environment.response_type(results) == "results_page"
    assert environment.response_type(item) == "product_page"
    assert environment.response_type("Thank you for shopping with us! [SEP] Your code:") == "receipt"
    assert environment.response_type("[]") == "empty_result_or_error"
    assert environment.response_type('{"error": "not found"}') == "empty_result_or_error"
    assert environment.response_type('[{"product_id": "1"}]') == "result"
    assert environment.response_type("  ") == "empty"
    assert environment.response_type("<observation></observation>") == "other"
    assert environment.rule_checks(item, results) == [
        0.0,
        len(environment.fields(results) & environment.fields(item)) / len(environment.fields(results)),
        0.0,
    ]
    assert not environment.parses("") and environment.parses(results) and environment.parses("[]")
    assert not environment.parses('<tool_call>{"name": "load_skill"}</tool_call>')
    assert environment.rule_checks('{{"product_id": "1"}}', '[{"product_id": "1"}]')[-1] == 1.0
    assert environment.rule_checks("[" * 5000, results)[-1] == 0.0


def test_reviser_keeps_distinct_edits_and_grounded_deletes_only():
    repertoire = Repertoire([skill("obs-format"), skill("cnt_prices"), skill("cnt_stock")])
    reviser = Reviser(None, "webshop", 0.0, 20, 2, WebShop.skill_prefixes)
    batch = [("a", "Error 404: product 123 is not in the catalog")]
    answer = {
        "updates": [
            {
                "action": "update",
                "skill_name": "prices",
                "content": "---\nname: cnt_prices\ndescription: d\n---\n" + "x" * 50,
            },
            {
                "action": "add",
                "skill_name": "cnt_prices",
                "content": "---\nname: cnt_prices\ndescription: d\n---\nsecond",
            },
            {"action": "retire", "skill_name": "cnt_stock", "content": "product 123 is not in the catalog"},
            {"action": "retire", "skill_name": "obs-format", "content": "never observed"},
            {"action": "add", "skill_name": "cnt_new", "content": "---\nname: cnt_new\ndescription: d\n---\nnew rule"},
        ]
    }
    revision = reviser.revision(repertoire, answer, batch)
    assert [(edit.kind, edit.target) for edit in revision.edits] == [
        ("rewrite", "cnt_prices"),
        ("delete", "cnt_stock"),
        ("create", "cnt_new"),
    ]
    assert len(revision.edits[0].skill.body) == 20
    assert [item.identifier for item in repertoire.apply(revision)] == ["obs-format", "cnt_prices", "cnt_new"]
    renamed = {
        "updates": [{"action": "update", "skill_name": "cnt_prices", "content": "---\nname: obs-format\n---\nbody"}]
    }
    collision = reviser.revision(repertoire, renamed, [])
    assert [(edit.target, edit.skill.identifier) for edit in collision.edits] == [("cnt_prices", "cnt_prices")]


def test_public_corpus_converters_and_split():
    answer = {
        "win": True,
        "answer_generation": {
            "valid_data": True,
            "query": "find flights",
            "train_messages": [
                [
                    {"role": "system", "content": "s"},
                    {"role": "user", "content": "find flights"},
                    {"role": "assistant", "content": "look up", "function_call": {"name": "search", "arguments": "{}"}},
                    {"role": "function", "name": "search", "content": '{"error": "", "response": "[]"}'},
                    {"role": "assistant", "function_call": {"name": "Finish", "arguments": "{}"}},
                ]
            ],
        },
    }
    converted = toolbench.convert(answer, 0)
    assert converted["steps"] == [
        {
            "action": "Thought: look up\nAction: search\nAction Input: {}",
            "observation": '{"error": "", "response": "[]"}',
        }
    ]
    demonstration = {
        "confirmed_task": "book a table",
        "action_reprs": ["[button] Search -> CLICK", "[link] Next -> CLICK"],
        "actions": [{"cleaned_html": "<html>first</html>"}, {"cleaned_html": "<html>second</html>"}],
    }
    page_trace = mind2web.convert(demonstration, 3)
    assert (page_trace["id"], page_trace["initial_observation"]) == ("mind2web-00003", "<html>first</html>")
    assert page_trace["steps"] == [{"action": "[button] Search -> CLICK", "observation": "<html>second</html>"}]
    assert "clipped" not in page_trace
    demonstration["actions"][1]["cleaned_html"] = "x" * (mind2web.PAGE_CHARS + 1)
    long_trace = mind2web.convert(demonstration, 3)
    assert long_trace["clipped"] and len(long_trace["steps"][0]["observation"]) == mind2web.PAGE_CHARS
    assert Trace.from_row(long_trace).clipped
    drawn = common.subset(1009, 169, 42)
    assert len(drawn) == 169 and drawn == sorted(set(drawn)) == common.subset(1009, 169, 42)
    assert common.subset(3, 169, 42) == [0, 1, 2] == common.subset(3, None, 42)
    rows = [
        {"source": source, "task": "t", "steps": [{}, {}], "initial_observation": "page"}
        for source in ["a"] * 9 + ["b"] * 9
    ]
    replay_rows, arbitration_rows = split.split(rows, 1 / 3, 0)
    assert (len(replay_rows), len(arbitration_rows)) == (12, 6)
    assert sorted(row["source"] for row in arbitration_rows) == ["a"] * 3 + ["b"] * 3
    assert not split.is_valid({"task": "t", "steps": [{"observation": "x"}]})
    failed = [{"observation": "[]"}, {"observation": '{"error": "Read timed out. (read timeout=30)"}'}]
    assert not split.is_valid({"task": "t", "steps": failed})


def test_shoppingbench_traces_hold_only_what_the_environment_returned():
    class Shopper:
        def __init__(self):
            self.calls = [
                [ToolCall("1", "find_product", {"q": "mouse", "page": 1})],
                [ToolCall("2", "view_product_information", {"product_ids": "7"}), ToolCall("3", "search_web", {})],
                [ToolCall("4", "recommend_product", {"product_ids": "7"})],
            ]

        async def reply(self, messages, tools=None, **decoding) -> Reply:
            return Reply("", self.calls.pop(0))

    class Api:
        def __init__(self, failing: bool):
            self.failing = failing

        async def get(self, url, params):
            if self.failing and url.endswith("view_product_information"):
                raise httpx.ReadTimeout("timed out")
            return httpx.Response(200, text=f"result of {url.rsplit('/', 1)[-1]}")

    row = asyncio.run(shoppingbench.collect_trace(0, "a gaming mouse", Shopper(), Api(False), "localhost:8080"))
    assert [step["observation"] for step in row["steps"]] == [
        "result of find_product",
        "result of view_product_information",
    ]
    assert row["reward"] == 1.0 and row["steps"][0]["action"] == 'find_product({"q": "mouse", "page": 1})'

    class Recorder:
        async def get(self, url, params):
            self.params = params
            return httpx.Response(200, text="[]")

    api = Recorder()
    asyncio.run(shoppingbench.request(api, "localhost:8080", "find_product", {"q": "mouse", "page": None}))
    assert api.params == {"q": "mouse", "page": 1}
    assert asyncio.run(shoppingbench.collect_trace(0, "a gaming mouse", Shopper(), Api(True), "localhost:8080")) is None


def test_browsergym_episodes_run_outside_the_event_loop(tmp_path, monkeypatch):
    class Environment:
        def __init__(self):
            self.pages = 0

        def observe(self):
            with pytest.raises(RuntimeError):
                asyncio.get_running_loop()
            self.pages += 1
            return {"axtree_object": f"page {self.pages}"}

        def reset(self):
            return self.observe(), {}

        def step(self, action):
            return self.observe(), 0.0, self.pages >= 4, False, {}

        def close(self):
            pass

    class Model:
        def __init__(self, config):
            pass

        async def reply(self, messages, **decoding) -> Reply:
            return Reply('Thought: open the first result.\nAction: click("12")')

    monkeypatch.setitem(sys.modules, "gymnasium", types.SimpleNamespace(make=lambda name, task_kwargs: Environment()))
    monkeypatch.setitem(sys.modules, "browsergym", types.ModuleType("browsergym"))
    monkeypatch.setitem(sys.modules, "browsergym.core", types.ModuleType("browsergym.core"))
    monkeypatch.setitem(sys.modules, "browsergym.utils", types.ModuleType("browsergym.utils"))
    monkeypatch.setitem(sys.modules, "browsergym.utils.obs", types.SimpleNamespace(flatten_axtree_to_str=str))
    monkeypatch.setattr(browsergym, "LanguageModel", Model)
    output = tmp_path / "browsergym.jsonl"
    kept = browsergym.collect("configs/sample.yaml", "data/samples/queries.jsonl", str(output), 2, "localhost")
    rows = read_rows(output)
    assert kept == 2 and rows[0]["initial_observation"] == "page 2"
    assert rows[0]["steps"] == [
        {"action": 'click("12")', "observation": "page 3"},
        {"action": 'click("12")', "observation": "page 4"},
    ]


def test_replay_cycles_evolve_the_repertoire(tmp_path):
    config = load_config("configs/sample.yaml")
    config.data.output_dir = str(tmp_path)
    embedder = HashEmbedder()
    replay_traces = load_traces(ROOT / "data/samples/replay_traces.jsonl")
    build_clusters(replay_traces, embedder, config.clusters).save(config.output("clusters.json"))
    (tmp_path / "evolve" / "cycle_09").mkdir(parents=True)
    selected = asyncio.run(evolve(config, model=ScriptedModel(), embedder=embedder))
    assert sorted(folder.name for folder in (tmp_path / "evolve").glob("cycle_*")) == ["cycle_01", "cycle_02"]
    outcome = json.loads((tmp_path / "evolve" / "arbitration.json").read_text())
    first = json.loads((tmp_path / "evolve" / "cycle_01" / "cycle.json").read_text())
    second = json.loads((tmp_path / "evolve" / "cycle_02" / "cycle.json").read_text())
    assert len(first["batch"]) == len(second["batch"]) == config.evolve.batch_size
    assert first["parsed"] == config.evolve.batch_size
    assert not set(first["batch"]) & set(second["batch"])
    assert first["revision"] == [
        {"kind": "create", "target": "cnt_scripted_rule_1", "rationale": "scripted", "evidence": ""}
    ]
    assert len(first["skills"]) == 7 and len(second["skills"]) == 8
    assert [entry["cycle"] for entry in outcome["history"]] == [1, 2]
    best = max(entry["arbitration_score"] for entry in outcome["history"])
    winner = next(entry["cycle"] for entry in outcome["history"] if entry["arbitration_score"] == best)
    assert outcome["winner"] == winner
    assert len(selected) == 6 + winner
    assert len(Repertoire.load(tmp_path / "evolve" / "selected")) == len(selected)


def test_simulator_without_a_repertoire_offers_no_skill_tool(tmp_path):
    model = ScriptedModel()
    simulator = Simulator(model, WebShop(), load_config("configs/sample.yaml").harness)
    sample = load_traces(ROOT / "data/samples/replay_traces.jsonl")[0]
    prediction = asyncio.run(simulator.predict(sample, 0, Repertoire()))
    assert (prediction.replies, prediction.tool_calls, model.tool_choices) == (1, [], ["none"])
    assert "Skill Repertoire" not in simulator.system(sample, Repertoire(), (), False, False)
    (tmp_path / "plain").mkdir()
    (tmp_path / "plain" / "rule").mkdir()
    (tmp_path / "plain" / "rule" / "SKILL.md").write_text("# Plain rule\n\nNo front matter here.")
    assert Repertoire.load(tmp_path / "plain").index() == "- rule — Plain rule"
    with pytest.raises(FileNotFoundError, match="no repertoire at"):
        Repertoire.load(tmp_path / "missing")
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError, match="no skills in"):
        Repertoire.load(tmp_path / "empty")


def test_world_model_predicts_the_next_observation():
    sample = load_traces(ROOT / "data/samples/replay_traces.jsonl")[0]
    world_model = WorldModel(model=ScriptedModel())
    assert world_model.config.environment == "webshop"
    observation = world_model.step(sample.task, sample.observations[:2], sample.actions[:2])
    assert observation == '[{"product_id": "3986206075", "title": "sample", "price": 9.5}]'


def test_response_types_of_the_other_environments():
    def label(name: str, observation: str, previous: str = "") -> str:
        return ENVIRONMENTS[name]().response_type(observation, previous)

    page = "RootWebArea 'Shop', url='shop.test/men/'\n\t[W-1] link 'MEN'\n\t[W-2] link 'WOMEN'"
    assert label("mind2web", page, page) == "no_change"
    assert label("mind2web", page.replace("/men/", "/women/"), page) == "changed"
    assert label("mind2web", page + "\n\t[W-9] dialog 'Sign in'", page) == "changed"
    assert label("mind2web", "The page shows a list of products.", page) == "other"
    report = "status=ok | output_exists=True\n[stdout] \n[stderr] \n[workbook]\nsheet 'Sheet1' dims=3x2 cells: A1=Week"
    assert label("sheetcopilot", report) == "ok_output"
    assert label("sheetcopilot", report.replace("True", "False")) == "ok_no_output"
    assert label("sheetcopilot", report.replace("status=ok", "status=error")) == "error"
    assert label("os", "The output of the OS:\n\n200") == "output"
    assert label("os", "The output of the OS is empty.") == "output"
    assert label("os", "The output of the OS:\n\nls: cannot access '/x': No such file or directory") == "error"
    assert label("tau2bench", "[user] My phone number is 555-123-2002.") == "user_turn"
    assert label("tau2bench", '[tool] {"reservation_id": "DF89BM", "status": "confirmed"}') == "tool_result"
    assert label("tau2bench", "Hello, I would like to change my flight.") == "user_turn"
    assert label("tau2bench", '<tool_call>[{"name": "get_user_details"}]</tool_call>') == "other"
    assert label("acebench", '{"status": true, "message": "User Jack has successfully logged in!"}') == "success"
    assert label("acebench", '{"status": false, "message": "Wi-Fi is not enabled, unable to login"}') == "failure"
    assert label("acebench", "\"[{'product': 'Soup', 'price': 12.0}]\"") == "success"
    assert label("bfcl", "[[19, 22], [43, 50]]") == "value"
    assert label("bfcl", '["{\\"history\\": [1]}", "{\\"error\\": \\"Order with ID 1 not found.\\"}"]') == "error"
    assert label("officebench", "Successfully sent email to Alice.") == "confirm"
    assert label("officebench", "The file notes.docx does not exist. Failed to read the file.") == "error"
    assert label("officebench", "No events found for Bob.") == "nothing"
    assert label("officebench", "/code/OfficeBench") == "content"
    assert all(label(name, "   ") == "empty" for name in ENVIRONMENTS)


def test_reviser_create_does_not_replace_a_skill_with_another_prefix():
    repertoire = Repertoire([skill("navigation-elements"), skill("obs-format")])
    reviser = Reviser(None, "webshop", 0.0, 5000, 2, WebShop.skill_prefixes)
    body = "---\nname: cnt_navigation_elements\ndescription: d\n---\nnew rule"
    created = {"updates": [{"action": "add", "skill_name": "cnt_navigation_elements", "content": body}]}
    revision = reviser.revision(repertoire, created, [])
    assert [(edit.kind, edit.target) for edit in revision.edits] == [("create", "cnt_navigation_elements")]
    assert len(repertoire.apply(revision)) == 3
    rewritten = {"updates": [{"action": "update", "skill_name": "cnt_navigation_elements", "content": body}]}
    revision = reviser.revision(repertoire, rewritten, [])
    assert [(edit.kind, edit.target) for edit in revision.edits] == [("rewrite", "navigation-elements")]
    assert len(repertoire.apply(revision)) == 2


def test_preflight_names_the_endpoint_that_does_not_answer():
    class Unreachable:
        config = ModelConfig("judge-model", api_base="localhost:9/v1")

        async def reply(self, messages, **decoding):
            raise APIConnectionError(request=httpx.Request("POST", "/v1/chat/completions"))

    with pytest.raises(SystemExit, match="the judge endpoint localhost:9/v1 .model judge-model. failed a test request"):
        asyncio.run(preflight(Unreachable(), "judge"))
    asyncio.run(preflight(ScriptedModel(), "judge"))
