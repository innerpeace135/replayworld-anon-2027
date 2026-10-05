from __future__ import annotations

import dataclasses
import typing
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ModelConfig:
    model: str
    api_base: str = ""
    api_key: str = "EMPTY"
    temperature: float = 0.0
    max_tokens: int = 4096
    concurrency: int = 32
    timeout: float = 1800.0
    retries: int = 2
    reasoning_effort: str = ""


@dataclass
class EmbeddingConfig:
    model: str = "BAAI/bge-m3"
    device: str = "cuda"
    batch_size: int = 64


@dataclass
class DataConfig:
    output_dir: str
    replay_traces: str = ""
    arbitration_traces: str = ""
    test_traces: str = ""


@dataclass
class RepertoireConfig:
    selected: str
    initial: str = ""
    skill_body_cap: int = 5000


@dataclass
class ClusterConfig:
    first_level: int = 100
    leaves_per_node: int = 10
    min_split_size: int = 20
    seed: int = 42


@dataclass
class EvolveConfig:
    n_pre: int = 2000
    n_sl: int = 1000
    batch_size: int = 200
    n_step: int = 3
    cycle_cap: int = 12
    patience: int = 5
    arbitration_sample: int = 300
    frequency_threshold: float = 0.10
    consolidation_period: int = 5
    consolidation_overlap: float = 0.7
    max_deletes_per_cycle: int = 2
    replay_thinking: bool = True
    seed: int = 42


@dataclass
class HarnessConfig:
    capabilities: list[str] = field(default_factory=list)
    replay_capabilities: list[str] = field(default_factory=list)
    reply_cap: int = 4
    reply_cap_with_tool_group: int = 6
    format_exemplar: str = ""
    shell_note: str = ""
    shell_timeout: int = 30
    simulation_max_tokens: int = 32768


@dataclass
class Config:
    environment: str
    simulator: ModelConfig
    agent: ModelConfig
    judge: ModelConfig
    action_preserve_judge: ModelConfig
    data: DataConfig
    repertoire: RepertoireConfig
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    clusters: ClusterConfig = field(default_factory=ClusterConfig)
    evolve: EvolveConfig = field(default_factory=EvolveConfig)
    harness: HarnessConfig = field(default_factory=HarnessConfig)

    def output(self, *parts: str) -> Path:
        path = resolve(self.data.output_dir).joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def folder(self, *parts: str) -> Path:
        path = resolve(self.data.output_dir).joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        return path


def build(kind, values: dict | None):
    values = values or {}
    hints = typing.get_type_hints(kind)
    unknown = set(values) - set(hints)
    if unknown:
        raise ValueError(f"unknown {kind.__name__} keys: {sorted(unknown)}")
    arguments = {}
    for spec in dataclasses.fields(kind):
        if spec.name in values:
            hint = hints[spec.name]
            value = values[spec.name]
            arguments[spec.name] = build(hint, value) if dataclasses.is_dataclass(hint) else value
    missing = [
        spec.name
        for spec in dataclasses.fields(kind)
        if spec.name not in arguments and spec.default is spec.default_factory is dataclasses.MISSING
    ]
    if missing:
        raise ValueError(f"{kind.__name__} needs {', '.join(missing)}")
    return kind(**arguments)


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def load_config(path: str) -> Config:
    with open(resolve(path), encoding="utf-8") as handle:
        return build(Config, yaml.safe_load(handle))
