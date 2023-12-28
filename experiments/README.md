# Experiments

## Random Selection

```bash
# Example
python3 evaluation.py --backend envoy
```

```bash
❯ python3 evaluation.py --help
usage: evaluation.py [-h] --backend {mrpc,envoy} [--num NUM] [--debug] [--latency_duration LATENCY_DURATION] [--cpu_duration CPU_DURATION]
                     [--target_rate TARGET_RATE]

options:
  -h, --help            show this help message and exit
  --backend {mrpc,envoy}
  --num NUM             element chain length
  --debug               Print backend debug info
  --latency_duration LATENCY_DURATION
                        wrk duration for latency test
  --cpu_duration CPU_DURATION
                        wrk2 duration for cpu usage test
  --target_rate TARGET_RATE
                        wrk2 request rate
```
