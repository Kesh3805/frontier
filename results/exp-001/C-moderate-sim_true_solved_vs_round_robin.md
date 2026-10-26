### C-R2-fnr0.0-fpr0.0: sim_true_solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 39.05 | 40.14 | -1.095 | [-1.595, -0.665] | -0.02728 | 26 / 66 / 108 | 3.67e-05 |
| thompson(k=2,hints=false) | 200 | 0 | 40.14 | 40.14 | 0 | [-0.065, 0.065] | 0 | 17 / 16 / 167 | 1 |
| thompson(k=2,hints=true) | 200 | 0 | 39.88 | 40.14 | -0.26 | [-0.38, -0.14] | -0.006477 | 18 / 54 / 128 | 2.569e-05 |

### C-R2-fnr0.0-fpr0.02: sim_true_solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 39.53 | 39.68 | -0.145 | [-0.25, -0.045] | -0.003654 | 10 / 28 / 162 | 0.005098 |
| thompson(k=2,hints=false) | 200 | 0 | 39.67 | 39.68 | -0.005 | [-0.04, 0.03] | -0.000126 | 6 / 7 / 187 | 1 |
| thompson(k=2,hints=true) | 200 | 0 | 39.64 | 39.68 | -0.04 | [-0.11, 0.03] | -0.001008 | 9 / 17 / 174 | 0.1686 |

### C-R2-fnr0.2-fpr0.0: sim_true_solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 38.46 | 39.58 | -1.12 | [-1.62, -0.685] | -0.0283 | 27 / 71 / 102 | 1.011e-05 |
| thompson(k=2,hints=false) | 200 | 0 | 39.57 | 39.58 | -0.01 | [-0.09, 0.065] | -0.0002527 | 22 / 24 / 154 | 0.883 |
| thompson(k=2,hints=true) | 200 | 0 | 39.35 | 39.58 | -0.23 | [-0.36, -0.105] | -0.005811 | 26 / 50 / 124 | 0.007905 |

### C-R2-fnr0.2-fpr0.02: sim_true_solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 39.05 | 39.16 | -0.105 | [-0.215, 0] | -0.002682 | 20 / 30 / 150 | 0.2026 |
| thompson(k=2,hints=false) | 200 | 0 | 39.14 | 39.16 | -0.015 | [-0.065, 0.035] | -0.0003831 | 9 / 12 / 179 | 0.6636 |
| thompson(k=2,hints=true) | 200 | 0 | 39.1 | 39.16 | -0.05 | [-0.13, 0.025] | -0.001277 | 16 / 20 / 164 | 0.6177 |

### C-R3-fnr0.0-fpr0.0: sim_true_solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 16.3 | 17.93 | -1.63 | [-2.085, -1.175] | -0.09088 | 57 / 119 / 24 | 3.418e-06 |
| thompson(k=2,hints=false) | 200 | 0 | 18.27 | 17.93 | 0.335 | [0.155, 0.52] | 0.01868 | 86 / 54 / 60 | 0.008557 |
| thompson(k=2,hints=true) | 200 | 0 | 18.95 | 17.93 | 1.015 | [0.81, 1.22] | 0.05659 | 124 / 31 / 45 | 2.242e-14 |

### C-R3-fnr0.0-fpr0.02: sim_true_solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 18.08 | 17.63 | 0.45 | [0.135, 0.77] | 0.02552 | 102 / 60 / 38 | 0.001207 |
| thompson(k=2,hints=false) | 200 | 0 | 17.92 | 17.63 | 0.29 | [0.115, 0.47] | 0.01645 | 78 / 48 / 74 | 0.009503 |
| thompson(k=2,hints=true) | 200 | 0 | 18.7 | 17.63 | 1.075 | [0.885, 1.27] | 0.06098 | 128 / 21 / 51 | 6.459e-20 |

### C-R3-fnr0.2-fpr0.0: sim_true_solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 15.81 | 16.75 | -0.94 | [-1.38, -0.49] | -0.05612 | 66 / 109 / 25 | 0.001428 |
| thompson(k=2,hints=false) | 200 | 0 | 17.09 | 16.75 | 0.345 | [0.15, 0.545] | 0.0206 | 85 / 53 / 62 | 0.008083 |
| thompson(k=2,hints=true) | 200 | 0 | 18.2 | 16.75 | 1.445 | [1.22, 1.67] | 0.08627 | 143 / 23 / 34 | 2.295e-22 |

### C-R3-fnr0.2-fpr0.02: sim_true_solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 17.29 | 16.5 | 0.78 | [0.48, 1.085] | 0.04726 | 113 / 50 / 37 | 8.858e-07 |
| thompson(k=2,hints=false) | 200 | 0 | 16.82 | 16.5 | 0.315 | [0.145, 0.495] | 0.01909 | 85 / 50 / 65 | 0.00328 |
| thompson(k=2,hints=true) | 200 | 0 | 17.87 | 16.5 | 1.365 | [1.185, 1.55] | 0.0827 | 146 / 12 / 42 | 1.961e-30 |

### C-R5-fnr0.0-fpr0.0: sim_true_solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 32.14 | 34.23 | -2.085 | [-2.7, -1.48] | -0.06092 | 58 / 116 / 26 | 1.305e-05 |
| thompson(k=2,hints=false) | 200 | 0 | 35.77 | 34.23 | 1.545 | [1.3, 1.795] | 0.04514 | 140 / 17 / 43 | 3.046e-25 |
| thompson(k=2,hints=true) | 200 | 0 | 35.74 | 34.23 | 1.52 | [1.26, 1.79] | 0.04441 | 139 / 25 / 36 | 2.29e-20 |

### C-R5-fnr0.0-fpr0.02: sim_true_solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 34.3 | 33.81 | 0.495 | [0.15, 0.83] | 0.01464 | 107 / 55 / 38 | 5.365e-05 |
| thompson(k=2,hints=false) | 200 | 0 | 34.9 | 33.81 | 1.09 | [0.865, 1.315] | 0.03224 | 124 / 28 / 48 | 1.285e-15 |
| thompson(k=2,hints=true) | 200 | 0 | 35.31 | 33.81 | 1.505 | [1.26, 1.755] | 0.04451 | 143 / 22 / 35 | 6.309e-23 |

### C-R5-fnr0.2-fpr0.0: sim_true_solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 31.39 | 31.28 | 0.11 | [-0.47, 0.675] | 0.003517 | 100 / 74 / 26 | 0.05775 |
| thompson(k=2,hints=false) | 200 | 0 | 34.1 | 31.28 | 2.825 | [2.54, 3.125] | 0.09031 | 176 / 8 / 16 | 2.385e-42 |
| thompson(k=2,hints=true) | 200 | 0 | 34.75 | 31.28 | 3.47 | [3.165, 3.785] | 0.1109 | 187 / 4 / 9 | 3.498e-50 |

### C-R5-fnr0.2-fpr0.02: sim_true_solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 33.26 | 31.04 | 2.215 | [1.835, 2.595] | 0.07136 | 154 / 26 / 20 | 2.524e-23 |
| thompson(k=2,hints=false) | 200 | 0 | 33.47 | 31.04 | 2.43 | [2.14, 2.725] | 0.07829 | 157 / 11 / 32 | 3.098e-34 |
| thompson(k=2,hints=true) | 200 | 0 | 34.35 | 31.04 | 3.31 | [3.005, 3.625] | 0.1066 | 182 / 4 / 14 | 1.006e-48 |

Paired cluster bootstrap, 10000 replicates, seed 26102026; clusters = (regime,seed).
