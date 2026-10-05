from __future__ import annotations

from pathlib import Path

from .common import arguments, save, subset, trace_row

SOURCE = "mind2web"
PAGE_CHARS = 8000


def load_demonstrations(dataset: str):
    import datasets

    if Path(dataset).exists():
        loaded = datasets.load_from_disk(dataset)
        return loaded["train"] if isinstance(loaded, datasets.DatasetDict) else loaded
    return datasets.load_dataset(dataset, split="train")


def convert(demonstration: dict, index: int) -> dict | None:
    pages = [action["cleaned_html"] for action in demonstration["actions"]]
    actions = demonstration["action_reprs"]
    if len(pages) < 2:
        return None
    steps = [
        {"action": actions[position], "observation": pages[position + 1][:PAGE_CHARS]}
        for position in range(len(pages) - 1)
    ]
    clipped = len(pages[-1]) > PAGE_CHARS
    return trace_row(SOURCE, index, demonstration["confirmed_task"], pages[0][:PAGE_CHARS], steps, 1.0, clipped)


def collect(dataset: str, output: str, sample: int | None, seed: int) -> int:
    demonstrations = load_demonstrations(dataset)
    return save(output, [convert(demonstrations[index], index) for index in subset(len(demonstrations), sample, seed)])


def main() -> None:
    parser = arguments("Convert Mind2Web demonstrations into traces.", queries=False)
    parser.add_argument("--dataset", default="osunlp/Mind2Web")
    options = parser.parse_args()
    print(f"{SOURCE}: {collect(options.dataset, options.output, options.sample, options.seed)} traces")


if __name__ == "__main__":
    main()
