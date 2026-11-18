| language | arm | n | c0_passed | native_passed | rtl_passed | input_tokens_mean | cached_tokens_mean |
|---|---|---|---|---|---|---|---|
| pyrtl | Direct | 168 | 102 | 88 | 88 | 1232.8690476190477 | 489.9047619047619 |
| pyrtl | FullDocRAG | 168 | 114 | 92 | 92 | 2471.5416666666665 | 302.4761904761905 |
| pyrtl | Gen | 168 | 129 | 109 | 109 | 1419.8690476190477 | 795.4285714285714 |
| myhdl | Direct | 168 | 159 | 132 | 101 | 1286.8690476190477 | 358.0952380952381 |
| myhdl | FullDocRAG | 168 | 158 | 135 | 109 | 2531.0833333333335 | 448.0 |
| myhdl | Gen | 168 | 159 | 138 | 111 | 1453.8690476190477 | 273.5238095238095 |
| amaranth | Direct | 168 | 160 | 137 | 137 | 1374.8690476190477 | 765.7142857142857 |
| amaranth | FullDocRAG | 168 | 163 | 141 | 141 | 2620.059523809524 | 949.3333333333334 |
| amaranth | Gen | 168 | 163 | 140 | 140 | 1561.8690476190477 | 733.7142857142857 |
| migen | Direct | 168 | 139 | 108 | 108 | 1237.8690476190477 | 516.5714285714286 |
| migen | FullDocRAG | 168 | 149 | 119 | 119 | 2488.5833333333335 | 656.0 |
| migen | Gen | 168 | 149 | 123 | 123 | 1433.8690476190477 | 541.7142857142857 |
| pymtl3 | Direct | 168 | 145 | 119 | 111 | 1291.8690476190477 | 246.85714285714286 |
| pymtl3 | FullDocRAG | 168 | 141 | 123 | 119 | 2561.0476190476193 | 530.2857142857143 |
| pymtl3 | Gen | 168 | 153 | 131 | 122 | 1495.8690476190477 | 411.42857142857144 |
| All | Direct | 840 | 705 | 584 | 545 | 1284.8690476190477 | 475.42857142857144 |
| All | FullDocRAG | 840 | 725 | 610 | 580 | 2534.4630952380953 | 577.2190476190476 |
| All | Gen | 840 | 753 | 641 | 605 | 1473.0690476190475 | 551.1619047619048 |

Each arm uses all 840 instances (168 per HCL), deepseek-v4.1-flash at temperature 0.2. The acceptance pipeline is C0 -> Q_native -> C_RTL; downstream pass indicators require earlier gates. Output-format failures remain in the denominator. All-instance paired tests use 168 task clusters; per-HCL tests use exact paired binomial tests. Detailed effects and p values are in table_iv_paired.json. Cached-token fields remain unknown when the provider omits them. Full-Doc RAG uses complete passages of 1001--1492 tokens.
