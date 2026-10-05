# Settings

## Replay loop

The defaults of `replayworld/config.py` are the settings shared across environments; for example, `configs/webshop.yaml` carries the WebShop values.

| Symbol | Setting | Config key | Default | WebShop |
|:-:|:--|:--|:-:|:-:|
| n<sub>pre</sub> | pre-sample size | `evolve.n_pre` | 2,000 | 2,000 |
| n<sub>sl</sub> | traces that LPF keeps | `evolve.n_sl` | 1,000 | 1,000 |
| B | batch size | `evolve.batch_size` | 200 | 200 |
| n<sub>step</sub> | steps that LPF scores per trace | `evolve.n_step` | 3 | 1 |
| K<sub>max</sub> | cycle cap | `evolve.cycle_cap` | 12 | 15 |
| κ | patience | `evolve.patience` | 5 | 5 |
| | arbitration sample per cycle | `evolve.arbitration_sample` | 300 | 300 |
| | frequency threshold of the Reviser | `evolve.frequency_threshold` | 0.10 | none |
| | consolidation period and overlap ratio | `evolve.consolidation_period` `evolve.consolidation_overlap` | 5 and 0.7 | 5 and 0.7 |
| | cap on a skill body | `repertoire.skill_body_cap` | 5,000 characters | 5,000 characters |
| M | reply cap of an agentic turn | `harness.reply_cap` `harness.reply_cap_with_tool_group` | 4, or 6 with `coding`; 1 in the single-reply instance | 4, or 6 with `coding`; 1 in the single-reply instance |

The values of the other environments are listed in the appendix of the paper (*Replay Loop Settings*). The remaining keys are implementation defaults; `simulator.temperature` is the decoding temperature of the replay loop, and the predictions of Steps 3 and 4 are made at temperature 0.
