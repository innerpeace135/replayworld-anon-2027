# ReplayBench

2,080 test traces, 260 per environment, one file per environment: `<environment>/test.jsonl`, one JSON object per line.
Environments: `webshop`, `mind2web`, `sheetcopilot`, `os`, `officebench`, `acebench`, `bfcl`, `tau2bench`.

Each trace isolates one step of a logged trajectory: `task` is the task query, `initial_observation` the first observation, and `steps` the recorded `action` / `observation` pairs. The step under test is the last one; its `observation` is the ground truth, and a simulator is scored on predicting it from the history and the action. `final` marks traces whose action ended the episode (ActionPreserve is scored on the others), and `free_running` marks the LongHorizon subsample.

License: CC BY-NC-SA 4.0, except `sheetcopilot/` (GPL-3.0); upstream notices in `LICENSE`.
