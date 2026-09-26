# Soak comparison

board 1 solo vs board 1 parallel

## Summary

| metric | board 1 solo | board 1 parallel |
| --- | --- | --- |
| Pass rate (%) | 100.0 | 100.0 |
| Cycles | 200 | 200 |
| Infra retries | 0 | 0 |

## Durations

| transport | kind | board 1 solo median (s) | board 1 parallel median (s) | ratio | flag |
| --- | --- | --- | --- | --- | --- |
| ble | failure | 182.75 | 281.85 | 1.54 | FLAG |
| ble | fixed | 108.7 | 206.3 | 1.90 | FLAG |
| ble | generated | 219.25 | 256.65 | 1.17 |  |
| wifi | failure | 152.8 | 152.7 | 1.00 |  |
| wifi | fixed | 31.9 | 31.9 | 1.00 |  |
| wifi | generated | 63.95 | 61.55 | 0.96 |  |

## Flags

- duration: ble failure is slower on board 2 by 54 %
- duration: ble fixed is slower on board 2 by 90 %
