# Soak comparison

board 1 vs board 2

## Summary

| metric | board 1 | board 2 |
| --- | --- | --- |
| Pass rate (%) | 100.0 | 100.0 |
| Cycles | 200 | 200 |
| Infra retries | 0 | 0 |

## Durations

| transport | kind | board 1 median (s) | board 2 median (s) | ratio | flag |
| --- | --- | --- | --- | --- | --- |
| ble | failure | 281.85 | 251.85 | 0.89 |  |
| ble | fixed | 206.3 | 205.4 | 1.00 |  |
| ble | generated | 256.65 | 288.05 | 1.12 |  |
| wifi | failure | 152.7 | 152.7 | 1.00 |  |
| wifi | fixed | 31.9 | 27.85 | 0.87 |  |
| wifi | generated | 61.55 | 52.55 | 0.85 |  |

## Flags

- none
