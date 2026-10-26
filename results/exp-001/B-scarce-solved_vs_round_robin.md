### B-R2-rho0.0: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 31.97 | 32.16 | -0.19 | [-0.7, 0.295] | -0.005908 | 97 / 72 / 31 | 0.06455 |
| oracle_index | 200 | 0 | 35.88 | 32.16 | 3.72 | [3.45, 3.995] | 0.1157 | 192 / 0 / 8 | 3.186e-58 |
| thompson(k=2,hints=false) | 200 | 0 | 32.06 | 32.16 | -0.095 | [-0.315, 0.125] | -0.002954 | 68 / 77 / 55 | 0.5066 |
| thompson(k=2,hints=true) | 200 | 0 | 33.56 | 32.16 | 1.4 | [1.155, 1.65] | 0.04353 | 136 / 27 / 37 | 1.069e-18 |

### B-R2-rho0.5: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 30.64 | 31.1 | -0.46 | [-0.92, -0.02] | -0.01479 | 86 / 78 / 36 | 0.5848 |
| oracle_index | 200 | 0 | 34.15 | 31.1 | 3.05 | [2.83, 3.28] | 0.09807 | 189 / 0 / 11 | 2.549e-57 |
| thompson(k=2,hints=false) | 200 | 0 | 31.02 | 31.1 | -0.075 | [-0.275, 0.12] | -0.002412 | 66 / 62 / 72 | 0.791 |
| thompson(k=2,hints=true) | 200 | 0 | 32.2 | 31.1 | 1.095 | [0.88, 1.315] | 0.03521 | 134 / 32 / 34 | 4.795e-16 |

### B-R2-rho0.9: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 28.46 | 30.38 | -1.915 | [-2.315, -1.54] | -0.06303 | 25 / 137 / 38 | 6.593e-20 |
| oracle_index | 200 | 0 | 31.32 | 30.38 | 0.935 | [0.77, 1.095] | 0.03078 | 122 / 13 / 65 | 2.244e-23 |
| thompson(k=2,hints=false) | 200 | 0 | 30.12 | 30.38 | -0.26 | [-0.43, -0.1] | -0.008558 | 34 / 57 / 109 | 0.02058 |
| thompson(k=2,hints=true) | 200 | 0 | 30.6 | 30.38 | 0.22 | [0.09, 0.36] | 0.007242 | 71 / 38 / 91 | 0.002033 |

### B-R3-rho0.0: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 11.34 | 8.22 | 3.115 | [2.745, 3.48] | 0.379 | 171 / 18 / 11 | 1.824e-32 |
| oracle_index | 200 | 0 | 15.39 | 8.22 | 7.17 | [6.88, 7.46] | 0.8723 | 200 / 0 / 0 | 1.245e-60 |
| thompson(k=2,hints=false) | 200 | 0 | 7.875 | 8.22 | -0.345 | [-0.595, -0.1] | -0.04197 | 58 / 84 / 58 | 0.03554 |
| thompson(k=2,hints=true) | 200 | 0 | 11.56 | 8.22 | 3.345 | [3.085, 3.61] | 0.4069 | 191 / 3 / 6 | 9.694e-53 |

### B-R3-rho0.5: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 9.79 | 8.035 | 1.755 | [1.43, 2.075] | 0.2184 | 142 / 35 / 23 | 1.732e-16 |
| oracle_index | 200 | 0 | 13.05 | 8.035 | 5.015 | [4.755, 5.275] | 0.6241 | 199 / 1 / 0 | 2.502e-58 |
| thompson(k=2,hints=false) | 200 | 0 | 7.33 | 8.035 | -0.705 | [-0.925, -0.485] | -0.08774 | 39 / 106 / 55 | 2.403e-08 |
| thompson(k=2,hints=true) | 200 | 0 | 10.18 | 8.035 | 2.145 | [1.91, 2.38] | 0.267 | 165 / 8 / 27 | 2.963e-39 |

### B-R3-rho0.9: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 7.115 | 7.88 | -0.765 | [-1.025, -0.505] | -0.09708 | 49 / 108 / 43 | 2.844e-06 |
| oracle_index | 200 | 0 | 9.07 | 7.88 | 1.19 | [0.99, 1.385] | 0.151 | 139 / 24 / 37 | 6.922e-21 |
| thompson(k=2,hints=false) | 200 | 0 | 6.855 | 7.88 | -1.025 | [-1.22, -0.835] | -0.1301 | 14 / 118 / 68 | 1.138e-21 |
| thompson(k=2,hints=true) | 200 | 0 | 8.36 | 7.88 | 0.48 | [0.34, 0.625] | 0.06091 | 92 / 31 / 77 | 3.317e-08 |

### B-R5-rho0.0: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 22.02 | 9.675 | 12.35 | [11.84, 12.86] | 1.276 | 200 / 0 / 0 | 1.245e-60 |
| oracle_index | 200 | 0 | 27.44 | 9.675 | 17.77 | [17.4, 18.14] | 1.836 | 200 / 0 / 0 | 1.245e-60 |
| thompson(k=2,hints=false) | 200 | 0 | 20.13 | 9.675 | 10.46 | [10.02, 10.9] | 1.081 | 200 / 0 / 0 | 1.245e-60 |
| thompson(k=2,hints=true) | 200 | 0 | 22.86 | 9.675 | 13.18 | [12.75, 13.62] | 1.362 | 200 / 0 / 0 | 1.245e-60 |

### B-R5-rho0.5: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 21.19 | 9.655 | 11.54 | [11.03, 12.04] | 1.195 | 200 / 0 / 0 | 1.245e-60 |
| oracle_index | 200 | 0 | 26.16 | 9.655 | 16.5 | [16.11, 16.89] | 1.709 | 200 / 0 / 0 | 1.245e-60 |
| thompson(k=2,hints=false) | 200 | 0 | 19.12 | 9.655 | 9.465 | [9.02, 9.92] | 0.9803 | 200 / 0 / 0 | 1.245e-60 |
| thompson(k=2,hints=true) | 200 | 0 | 22 | 9.655 | 12.35 | [11.9, 12.79] | 1.279 | 200 / 0 / 0 | 1.245e-60 |

### B-R5-rho0.9: solved, policy vs round_robin

| policy | clusters | excluded | mean | baseline mean | diff | 95% CI | rel. diff | A>B / A<B / ties | sign-test p |
|---|---|---|---|---|---|---|---|---|---|
| greedy_prior | 200 | 0 | 19.66 | 9.605 | 10.05 | [9.54, 10.55] | 1.046 | 200 / 0 / 0 | 1.245e-60 |
| oracle_index | 200 | 0 | 23.82 | 9.605 | 14.21 | [13.76, 14.66] | 1.479 | 200 / 0 / 0 | 1.245e-60 |
| thompson(k=2,hints=false) | 200 | 0 | 18 | 9.605 | 8.39 | [7.94, 8.83] | 0.8735 | 200 / 0 / 0 | 1.245e-60 |
| thompson(k=2,hints=true) | 200 | 0 | 20.96 | 9.605 | 11.36 | [10.92, 11.79] | 1.182 | 200 / 0 / 0 | 1.245e-60 |

Paired cluster bootstrap, 10000 replicates, seed 26102026; clusters = (regime,seed).
