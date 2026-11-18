# ParaRoute: Anonymous DAC Artifact

ParaRoute is a reproducible artifact for studying LLM generation and repair of
Python hardware-construction-language (HCL) programs. The release covers five
HCLs, 168 benchmark tasks, and 840 frozen task-language instances. It includes
the public-interface router, repair and contract flow, frozen model requests and
responses, native and exported-Verilog evaluation evidence, statistical ledgers,
and the RTL-aware closed-loop extension.

This repository is the expanded project tree. It intentionally does not contain
the submission PDF, Git history from the private development checkout, API
credentials, personal paths, private host settings, or provider account IDs.

## Quick verification (no model calls)

The following checks use only the files in this repository and Python's standard
library:

```sh
python verify_artifact.py
```

The verifier checks the public manifest, the 840-instance population, all frozen
experiment ledgers, the seven runtime scripts, and the anonymized evidence
shards. It reports `network_calls: 0` and `simulations: 0`.

Saved evidence is kept in compressed JSONL shards to avoid hundreds of thousands
of tiny files. To materialize the saved records in a disposable checkout:

```sh
python hydrate_artifacts.py
```

Hydration is idempotent and does not contact a model, a simulator, or a remote
service.

## Project layout

- `unified_dac_experiments_840/` — generation, repair, routing, contracts,
  evaluation adapters, configurations, frozen ledgers, and analysis scripts.
- `unified_dac_experiments_840/runtime/` — the seven frozen native/RTL runtime
  scripts used for the reported scores.
- `unified_dac_experiments_840/configs/` — population, request, evaluation,
  model, and runtime-fingerprint metadata.
- `unified_dac_experiments_840/analysis/` — Tables IV--VIII, cost ledgers,
  residual-failure analysis, and RTL-aware closed-loop budget curves.
- `frozen_data/` — anonymized saved run/evaluation evidence in gzip JSONL form.
- `third_party/pyhdl-eval/` — public benchmark sources needed to inspect the
  frozen benchmark identity.
- `RESULTS_GUIDE_ZH.md` — Chinese guide to the locked experimental results.
- `ANONYMIZATION.md` and `THIRD_PARTY_NOTICES.md` — release scope and notices.

The central result files are `analysis/table_iv.csv`, `analysis/table_v.csv`,
`analysis/table_v_actual_costs.csv`, `analysis/table_vi.csv`,
`analysis/table_vi_specialized.csv`, `analysis/table_vii_viii.csv`, and
`analysis/rtl_closed_loop_b5/` under `unified_dac_experiments_840/`.

## Recomputing frozen analyses

Optional analysis dependencies are listed in `requirements-analysis.txt`:

```sh
python -m pip install -r requirements-analysis.txt
python unified_dac_experiments_840/analyze.py 1
python unified_dac_experiments_840/analyze.py 2
python unified_dac_experiments_840/analyze.py 3
python unified_dac_experiments_840/analyze.py 4 \
  --models deepseek-v4.1-flash qwen3.8-flash glm-5.3-flash claude-haiku-5-5
```

These scripts recompute tables from saved records. They do not reproduce the
private provider calls. The frozen CSV files are the authoritative submission
copy; analysis commands may overwrite their output in a working checkout.

## Running new generations or evaluations

No credential is distributed. A new model run requires credentials supplied by
the user process, for example `OPENCODE_API_KEY`, and an explicitly configured
API endpoint. Claude requests use the Anthropic Messages protocol; other listed
models use the compatible chat-completions path. The original private evaluator
image is not distributed, so a replacement image is a new evaluation
environment and must not be described as bit-identical to the frozen scores.

`generate.py`, `repair.py`, `router.py`, `contract_flow.py`, and `rtl_closed_loop.py`
are the main implementation entry points. `remote.py` is a portable local-Docker
adapter; it contains no private SSH destination. Candidates are intended to run
with network access disabled during evaluation.

## Evaluation terminology

`C_0` is construction/probe gating, `Q_native` is the native simulation suite,
and `C_RTL` means Verilog export followed by RTL simulation. `C_RTL` does not
claim synthesis, timing closure, or physical implementation. Pass@5 is an
oracle any-pass estimator, while blind Best@5 uses only the reference-blind
construction probe. The main unified denominator is 840; historical
52/96/117/336-instance cohorts remain explicitly conditional and are not pooled
into the unified tables.

## Privacy and licensing

The public benchmark and upstream HCL notices remain in `third_party/`.
Submission-authored code is provided for anonymous review without implying a
new open-source license. `ANONYMITY_AUDIT.json` records the local privacy scan;
`MANIFEST.json` authenticates the public bytes. No upload script or credential
is stored in this repository.
