from __future__ import annotations

import argparse
import json
import math
import random
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import ClusterConfig, load_config, resolve
from .embedding import Embedder
from .traces import Trace, load_traces


@dataclass
class Clusters:
    members: list[list[int]]
    trace_ids: list[str]

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"members": self.members, "trace_ids": self.trace_ids}), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Clusters:
        stored = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(stored["members"], stored["trace_ids"])


def kmeans(vectors: np.ndarray, k: int, seed: int) -> np.ndarray:
    from sklearn.cluster import MiniBatchKMeans

    k = min(k, len(vectors))
    if k <= 1:
        return np.zeros(len(vectors), dtype=np.int64)
    model = MiniBatchKMeans(n_clusters=k, random_state=seed, n_init=3, max_iter=100, batch_size=min(1024, len(vectors)))
    return model.fit_predict(vectors)


def build_clusters(traces: list[Trace], embedder, config: ClusterConfig) -> Clusters:
    vectors = embedder.encode([trace.task for trace in traces])
    first = kmeans(vectors, config.first_level, config.seed)
    members = []
    for node in range(int(first.max()) + 1):
        inside = np.flatnonzero(first == node)
        if len(inside) == 0:
            continue
        if len(inside) < config.min_split_size:
            members.append(inside.tolist())
            continue
        second = kmeans(vectors[inside], config.leaves_per_node, config.seed + node)
        for leaf in range(int(second.max()) + 1):
            leaf_members = inside[second == leaf]
            if len(leaf_members):
                members.append(leaf_members.tolist())
    return Clusters(members, [trace.trace_id for trace in traces])


def sbs(eligible: Iterable[int], clusters: Clusters, n: int, rng: random.Random) -> list[int]:
    allowed = set(eligible)
    remaining = {}
    for label, cluster in enumerate(clusters.members):
        inside = [index for index in cluster if index in allowed]
        if inside:
            remaining[label] = inside
    weights = {label: math.sqrt(len(inside)) for label, inside in remaining.items()}
    drawn = []
    while remaining and len(drawn) < n:
        labels = list(remaining)
        label = rng.choices(labels, weights=[weights[item] for item in labels], k=1)[0]
        inside = remaining[label]
        drawn.append(inside.pop(rng.randrange(len(inside))))
        if not inside:
            del remaining[label]
    return drawn


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster the replay traces for SBS.")
    parser.add_argument("--config", default="configs/webshop.yaml")
    arguments = parser.parse_args()
    config = load_config(arguments.config)
    traces = load_traces(resolve(config.data.replay_traces))
    clusters = build_clusters(traces, Embedder(config.embedding), config.clusters)
    clusters.save(config.output("clusters.json"))
    print(f"clusters: {len(clusters.members)} over {len(traces)} replay traces")


if __name__ == "__main__":
    main()
