# Claude Haiku 5.5 — saved Anthropic Messages base ledger

The confirmed Anthropic Messages transport returned model `claude-haiku-5-5`. This report uses the immutable 840-instance cross-family population and the saved `Direct`/`Gen` responses; no score is imputed for the seven parse failures.

| Language | Method | n | Parse failures | C0 pass | Native pass | RTL pass | Mean input tok | Mean output tok | Mean total tok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pyrtl | Direct | 168 | 1 | 159 (94.64%) | 150 (89.29%) | 150 (89.29%) | 1840.4 | 981.3 | 2821.7 |
| pyrtl | Gen | 168 | 1 | 155 (92.26%) | 147 (87.50%) | 147 (87.50%) | 2139.4 | 979.5 | 3118.9 |
| myhdl | Direct | 168 | 0 | 166 (98.81%) | 160 (95.24%) | 128 (76.19%) | 1900.4 | 874.2 | 2774.6 |
| myhdl | Gen | 168 | 1 | 164 (97.62%) | 159 (94.64%) | 129 (76.79%) | 2174.4 | 883.2 | 3057.5 |
| amaranth | Direct | 168 | 0 | 166 (98.81%) | 162 (96.43%) | 162 (96.43%) | 2051.4 | 857.9 | 2909.2 |
| amaranth | Gen | 168 | 2 | 164 (97.62%) | 157 (93.45%) | 157 (93.45%) | 2353.4 | 821.3 | 3174.7 |
| migen | Direct | 168 | 0 | 161 (95.83%) | 157 (93.45%) | 157 (93.45%) | 1839.4 | 793.8 | 2633.2 |
| migen | Gen | 168 | 0 | 167 (99.40%) | 161 (95.83%) | 161 (95.83%) | 2144.4 | 805.1 | 2949.4 |
| pymtl3 | Direct | 168 | 1 | 156 (92.86%) | 150 (89.29%) | 120 (71.43%) | 1901.4 | 901.2 | 2802.6 |
| pymtl3 | Gen | 168 | 1 | 160 (95.24%) | 155 (92.26%) | 134 (79.76%) | 2235.4 | 971.7 | 3207.1 |
| All | Direct | 840 | 2 | 808 (96.19%) | 779 (92.74%) | 717 (85.36%) | 1906.6 | 881.7 | 2788.3 |
| All | Gen | 840 | 5 | 810 (96.43%) | 779 (92.74%) | 728 (86.67%) | 2209.4 | 892.2 | 3101.5 |

Seven outputs failed the frozen source parser; their exact error classes are retained in `claude_haiku_base_failure_counts.json` and each per-job `generation.json`. All 1,680 jobs have an official evaluation record. The routed repair arms and their contract costs require separate Claude repair responses and are not represented by this base-only table.
