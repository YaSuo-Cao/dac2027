| method | group | n | native_passed | native_percent | rtl_passed | lazy_tokens |
|---|---|---|---|---|---|---|
| F | All | 840 | 690 | 82.14285714285714 | 650 | 2084653 |
| F | Stateless Comb | 49 | 9 | 18.367346938775512 | 9 | 197529 |
| F | Clocked Seq | 72 | 9 | 12.5 | 8 | 485531 |
| F | F_func | 121 | 18 | 14.87603305785124 | 17 | 683060 |
| FT | All | 840 | 700 | 83.33333333333333 | 659 | 2165412 |
| FT | Stateless Comb | 49 | 15 | 30.612244897959183 | 14 | 218646 |
| FT | Clocked Seq | 72 | 13 | 18.055555555555557 | 12 | 545173 |
| FT | F_func | 121 | 28 | 23.140495867768596 | 26 | 763819 |
| FC | All | 840 | 709 | 84.4047619047619 | 669 | 2268061 |
| FC | Stateless Comb | 49 | 12 | 24.489795918367346 | 12 | 254122 |
| FC | Clocked Seq | 72 | 25 | 34.72222222222222 | 24 | 612346 |
| FC | F_func | 121 | 37 | 30.578512396694215 | 36 | 866468 |
| FCT | All | 840 | 714 | 85.0 | 671 | 2344273 |
| FCT | Stateless Comb | 49 | 15 | 30.612244897959183 | 14 | 271118 |
| FCT | Clocked Seq | 72 | 27 | 37.5 | 24 | 671562 |
| FCT | F_func | 121 | 42 | 34.710743801652896 | 38 | 942680 |
| Inverse-Route | All | 840 | 697 | 82.97619047619048 | 657 | 2200888 |
| Inverse-Route | Stateless Comb | 49 | 12 | 24.489795918367346 | 12 | 254122 |
| Inverse-Route | Clocked Seq | 72 | 13 | 18.055555555555557 | 12 | 545173 |
| Inverse-Route | F_func | 121 | 25 | 20.66115702479339 | 24 | 799295 |
| ParaRoute | All | 840 | 712 | 84.76190476190476 | 671 | 2248233 |
| ParaRoute | Stateless Comb | 49 | 15 | 30.612244897959183 | 14 | 218646 |
| ParaRoute | Clocked Seq | 72 | 25 | 34.72222222222222 | 24 | 627994 |
| ParaRoute | F_func | 121 | 40 | 33.05785123966942 | 38 | 846640 |

All is the end-to-end /840 score. F_func, Stateless Comb and Clocked Seq are conditional repair-recovery rows from the common post-FL functional-failure pool, not alternative populations. Population flow: {"initial_native_passed": 641, "initial_c0_rejected_and_FL_attempted": 87, "after_shared_FL_native_passed": 672, "remaining_c0_rejected": 47, "functional_pool": 121}. Inverse and Equation-4 policies alias the same independently generated F/FT/FC/FCT requests. A rejected repair falls back using C0 alone. All /840 paired effects are in table_v_paired.json. table_v_actual_costs.csv reports deployment costs, actual paired-provider prompt increments for contract injection, and savings versus FCT; shared contract generation is counted once per task. The physical factorial bill is separate from per-policy deployment cost.
