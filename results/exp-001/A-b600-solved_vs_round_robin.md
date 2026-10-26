### A-noise0: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 39.23 | 40.14 | -0.905 | [-1.375, -0.5] | -0.02255 | 27 / 57 / 116 | 0.001404 |
| oracle_index | 200 | 0 | 40.87 | 40.14 | 0.73 | [0.59, 0.88] | 0.01819 | 92 / 0 / 108 | 4.039e-28 |
| thompson(k=0.5,hints=true) | 200 | 0 | 39.98 | 40.14 | -0.165 | [-0.27, -0.06] | -0.004111 | 17 / 47 / 136 | 0.0002269 |
| thompson(k=2,hints=false) | 200 | 0 | 40.14 | 40.14 | 0 | [-0.065, 0.065] | 0 | 17 / 16 / 167 | 1 |
| thompson(k=2,hints=true) | 200 | 0 | 39.98 | 40.14 | -0.165 | [-0.26, -0.065] | -0.004111 | 18 / 46 / 136 | 0.0006174 |
| thompson(k=8,hints=true) | 200 | 0 | 39.84 | 40.14 | -0.3 | [-0.43, -0.175] | -0.007474 | 18 / 56 / 126 | 1.109e-05 |

### A-noise1: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 39.05 | 40.14 | -1.095 | [-1.595, -0.665] | -0.02728 | 26 / 66 / 108 | 3.67e-05 |
| oracle_index | 200 | 0 | 40.87 | 40.14 | 0.73 | [0.59, 0.88] | 0.01819 | 92 / 0 / 108 | 4.039e-28 |
| thompson(k=0.5,hints=true) | 200 | 0 | 39.93 | 40.14 | -0.21 | [-0.325, -0.095] | -0.005232 | 17 / 48 / 135 | 0.0001521 |
| thompson(k=2,hints=false) | 200 | 0 | 40.14 | 40.14 | 0 | [-0.065, 0.065] | 0 | 17 / 16 / 167 | 1 |
| thompson(k=2,hints=true) | 200 | 0 | 39.88 | 40.14 | -0.26 | [-0.38, -0.14] | -0.006477 | 18 / 54 / 128 | 2.569e-05 |
| thompson(k=8,hints=true) | 200 | 0 | 39.77 | 40.14 | -0.37 | [-0.515, -0.225] | -0.009218 | 19 / 61 / 120 | 2.732e-06 |

### A-noise2: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 38.73 | 40.14 | -1.41 | [-1.92, -0.975] | -0.03513 | 19 / 84 / 97 | 6.208e-11 |
| oracle_index | 200 | 0 | 40.87 | 40.14 | 0.73 | [0.59, 0.88] | 0.01819 | 92 / 0 / 108 | 4.039e-28 |
| thompson(k=0.5,hints=true) | 200 | 0 | 39.87 | 40.14 | -0.275 | [-0.41, -0.14] | -0.006851 | 23 / 58 / 119 | 0.0001266 |
| thompson(k=2,hints=false) | 200 | 0 | 40.14 | 40.14 | 0 | [-0.065, 0.065] | 0 | 17 / 16 / 167 | 1 |
| thompson(k=2,hints=true) | 200 | 0 | 39.85 | 40.14 | -0.285 | [-0.42, -0.15] | -0.0071 | 21 / 55 / 124 | 0.0001206 |
| thompson(k=8,hints=true) | 200 | 0 | 39.66 | 40.14 | -0.475 | [-0.64, -0.315] | -0.01183 | 18 / 66 / 116 | 1.333e-07 |

Paired cluster bootstrap, 10000 replicates, seed 26102026; clusters = (regime,seed).
