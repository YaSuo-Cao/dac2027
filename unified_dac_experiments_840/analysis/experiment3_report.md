| method | n | native_percent | rtl_percent | mean_calls | mean_amortized_tokens | mean_lazy_tokens |
|---|---|---|---|---|---|---|
| Direct GatedBest@1 | 840 | 70.23809523809523 | 65.23809523809524 | 1.0 | 1485.982142857143 | 1485.982142857143 |
| Direct GatedBest@3 | 840 | 75.23809523809524 | 69.88095238095238 | 3.0 | 4472.7488095238095 | 4472.7488095238095 |
| Direct GatedBest@5 | 840 | 76.54761904761904 | 71.19047619047619 | 5.0 | 7439.453571428571 | 7439.453571428571 |
| Direct Pass@1 | 840 | 70.35714285714286 | 65.66666666666666 | 1.0 | 1487.890714285714 | 1487.890714285714 |
| Direct Pass@3 | 840 | 80.78571428571428 | 76.77380952380952 | 3.0 | 4463.6721428571445 | 4463.6721428571445 |
| Direct Pass@5 | 840 | 84.52380952380952 | 80.95238095238095 | 5.0 | 7439.453571428571 | 7439.453571428571 |
| Gen GatedBest@1 | 840 | 73.33333333333333 | 69.76190476190476 | 1.0 | 1690.8416666666667 | 1690.8416666666667 |
| Gen GatedBest@3 | 840 | 77.85714285714286 | 74.04761904761905 | 3.0 | 5071.872619047619 | 5071.872619047619 |
| Gen GatedBest@5 | 840 | 78.69047619047619 | 75.0 | 5.0 | 8463.035714285714 | 8463.035714285714 |
| Gen Pass@1 | 840 | 73.76190476190474 | 70.02380952380953 | 1.0 | 1692.607142857143 | 1692.607142857143 |
| Gen Pass@3 | 840 | 84.82142857142857 | 82.07142857142857 | 3.0 | 5077.8214285714275 | 5077.8214285714275 |
| Gen Pass@5 | 840 | 88.09523809523809 | 85.59523809523809 | 5.0 | 8463.035714285714 | 8463.035714285714 |
| ParaRoute-Fast | 840 | 84.28571428571429 | 79.4047619047619 | 1.236904761904762 | 2574.6607142857147 | 2626.3690476190477 |
| ParaRoute-Full | 840 | 85.95238095238096 | 80.95238095238095 | 1.3511904761904763 | 2908.254761904763 | 2966.5142857142855 |

All 840 instances have five fresh samples per arm, all at temperature 0.7 / top_p 0.95; no temperature-0.2 k1 is imported. Pass@k is the unbiased estimator 1-C(5-c,k)/C(5,k), so expected pass counts need not be integers. Its k-call cost is the expected cost of k samples estimated from all five responses; the physical sampling experiment generates all five. GatedBest uses only C0 on the first k samples and prefers the first warning-free gate-passing candidate; native/RTL outcomes never rank candidates. Fast and Full use the same model at temperature 0.2 with at most one/two code repairs. mean_calls counts code-generation/repair calls; table_vi.csv additionally includes calls for lazy and shared contracts. All contract formatting attempts are charged. Five-HCL sharing conserves each actual contract bill once across siblings; single-HCL lazy accounting pays only on the first contract-requiring branch. Specialized strata are secondary diagnostics in table_vi_specialized.csv.
