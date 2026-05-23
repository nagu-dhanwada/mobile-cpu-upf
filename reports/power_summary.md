# Power Exploration Summary

These numbers are architectural estimates for comparing schemes before a real
implementation power analysis flow. Treat absolute values as placeholders and
relative ordering as the useful signal.

| Scheme | Dynamic mW | Leakage mW | Total mW | Relative to baseline |
| --- | ---: | ---: | ---: | ---: |
| dvfs_retention_domains | 6.395 | 5.221 | 11.616 | 25.5% |
| core_power_gated_sleep | 6.437 | 6.049 | 12.486 | 27.4% |
| clock_gated_idle | 10.962 | 7.16 | 18.122 | 39.8% |
| baseline_always_on | 38.4 | 7.16 | 45.56 | 100.0% |
