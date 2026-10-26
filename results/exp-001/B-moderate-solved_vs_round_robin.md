### B-R2-rho0.0: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 39.05 | 40.14 | -1.095 | [-1.595, -0.665] | -0.02728 | 26 / 66 / 108 | 3.67e-05 |
| oracle_index | 200 | 0 | 40.87 | 40.14 | 0.73 | [0.59, 0.88] | 0.01819 | 92 / 0 / 108 | 4.039e-28 |
| thompson(k=2,hints=false) | 200 | 0 | 40.14 | 40.14 | 0 | [-0.065, 0.065] | 0 | 17 / 16 / 167 | 1 |
| thompson(k=2,hints=true) | 200 | 0 | 39.88 | 40.14 | -0.26 | [-0.38, -0.14] | -0.006477 | 18 / 54 / 128 | 2.569e-05 |

### B-R2-rho0.5: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 37.66 | 38.49 | -0.835 | [-1.315, -0.415] | -0.02169 | 41 / 68 / 91 | 0.0124 |
| oracle_index | 200 | 0 | 39.62 | 38.49 | 1.12 | [0.94, 1.31] | 0.02909 | 118 / 1 / 81 | 3.611e-34 |
| thompson(k=2,hints=false) | 200 | 0 | 38.58 | 38.49 | 0.085 | [-0.01, 0.18] | 0.002208 | 36 / 29 / 135 | 0.457 |
| thompson(k=2,hints=true) | 200 | 0 | 38.55 | 38.49 | 0.05 | [-0.085, 0.185] | 0.001299 | 50 / 42 / 108 | 0.4657 |

### B-R2-rho0.9: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 33.67 | 33.78 | -0.105 | [-0.54, 0.29] | -0.003108 | 97 / 61 / 42 | 0.005197 |
| oracle_index | 200 | 0 | 35.98 | 33.78 | 2.2 | [1.985, 2.42] | 0.06513 | 169 / 0 / 31 | 2.673e-51 |
| thompson(k=2,hints=false) | 200 | 0 | 34.07 | 33.78 | 0.29 | [0.1749, 0.405] | 0.008585 | 69 / 26 / 105 | 1.183e-05 |
| thompson(k=2,hints=true) | 200 | 0 | 34.58 | 33.78 | 0.795 | [0.64, 0.955] | 0.02353 | 115 / 19 / 66 | 6.137e-18 |

### B-R3-rho0.0: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 16.3 | 17.93 | -1.63 | [-2.085, -1.175] | -0.09088 | 57 / 119 / 24 | 3.418e-06 |
| oracle_index | 200 | 0 | 22.95 | 17.93 | 5.02 | [4.745, 5.295] | 0.2799 | 198 / 0 / 2 | 4.978e-60 |
| thompson(k=2,hints=false) | 200 | 0 | 18.27 | 17.93 | 0.335 | [0.155, 0.52] | 0.01868 | 86 / 54 / 60 | 0.008557 |
| thompson(k=2,hints=true) | 200 | 0 | 18.95 | 17.93 | 1.015 | [0.81, 1.22] | 0.05659 | 124 / 31 / 45 | 2.242e-14 |

### B-R3-rho0.5: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 14.79 | 14.66 | 0.125 | [-0.295, 0.55] | 0.008524 | 95 / 86 / 19 | 0.5522 |
| oracle_index | 200 | 0 | 20.52 | 14.66 | 5.855 | [5.56, 6.15] | 0.3992 | 200 / 0 / 0 | 1.245e-60 |
| thompson(k=2,hints=false) | 200 | 0 | 15.1 | 14.66 | 0.435 | [0.22, 0.645] | 0.02966 | 87 / 48 / 65 | 0.0009995 |
| thompson(k=2,hints=true) | 200 | 0 | 16.59 | 14.66 | 1.925 | [1.68, 2.175] | 0.1313 | 160 / 12 / 28 | 3.41e-34 |

### B-R3-rho0.9: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 11.05 | 9.945 | 1.11 | [0.775, 1.445] | 0.1116 | 119 / 51 / 30 | 1.924e-07 |
| oracle_index | 200 | 0 | 14.44 | 9.945 | 4.49 | [4.21, 4.765] | 0.4515 | 196 / 1 / 3 | 1.971e-57 |
| thompson(k=2,hints=false) | 200 | 0 | 10.25 | 9.945 | 0.305 | [0.17, 0.44] | 0.03067 | 77 / 34 / 89 | 5.495e-05 |
| thompson(k=2,hints=true) | 200 | 0 | 11.7 | 9.945 | 1.755 | [1.57, 1.945] | 0.1765 | 166 / 4 / 30 | 4.598e-44 |

### B-R5-rho0.0: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 32.14 | 34.23 | -2.085 | [-2.7, -1.48] | -0.06092 | 58 / 116 / 26 | 1.305e-05 |
| oracle_index | 200 | 0 | 38.85 | 34.23 | 4.625 | [4.27, 4.985] | 0.1351 | 196 / 0 / 4 | 1.991e-59 |
| thompson(k=2,hints=false) | 200 | 0 | 35.77 | 34.23 | 1.545 | [1.3, 1.795] | 0.04514 | 140 / 17 / 43 | 3.046e-25 |
| thompson(k=2,hints=true) | 200 | 0 | 35.74 | 34.23 | 1.52 | [1.26, 1.79] | 0.04441 | 139 / 25 / 36 | 2.29e-20 |

### B-R5-rho0.5: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 30.93 | 31.5 | -0.565 | [-1.11, -0.025] | -0.01794 | 92 / 85 / 23 | 0.6521 |
| oracle_index | 200 | 0 | 37.3 | 31.5 | 5.795 | [5.455, 6.15] | 0.184 | 200 / 0 / 0 | 1.245e-60 |
| thompson(k=2,hints=false) | 200 | 0 | 33.34 | 31.5 | 1.835 | [1.56, 2.11] | 0.05825 | 149 / 17 / 34 | 1.601e-27 |
| thompson(k=2,hints=true) | 200 | 0 | 34.06 | 31.5 | 2.565 | [2.31, 2.825] | 0.08143 | 176 / 5 / 19 | 1.028e-45 |

### B-R5-rho0.9: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 27.02 | 27.45 | -0.43 | [-0.9151, 0.045] | -0.01567 | 82 / 92 / 26 | 0.4952 |
| oracle_index | 200 | 0 | 32.53 | 27.45 | 5.09 | [4.815, 5.365] | 0.1855 | 200 / 0 / 0 | 1.245e-60 |
| thompson(k=2,hints=false) | 200 | 0 | 28.32 | 27.45 | 0.88 | [0.67, 1.1] | 0.03206 | 122 / 37 / 41 | 8.435e-12 |
| thompson(k=2,hints=true) | 200 | 0 | 29.59 | 27.45 | 2.145 | [1.945, 2.355] | 0.07816 | 174 / 1 / 25 | 7.35e-51 |

Paired cluster bootstrap, 10000 replicates, seed 26102026; clusters = (regime,seed).
