import argparse
import os
import sys
from pathlib import Path

import yaml

sys.path.append(str(Path(__file__).parent.parent.absolute()))

from compiler.graph.backend.utils import execute_local, ksync
from compiler.graph.logger import EVAL_LOG, init_logging
from experiments import EXP_DIR, ROOT_DIR
from experiments.utils import (
    run_wrk2_and_get_cpu,
    run_wrk_and_get_latency,
    select_random_elements,
    set_element_pool,
)

# Some elements
envoy_element_pool = {
    "acl",
    "mutation",
    "logging",
    "metrics",
    "ratelimit",
    "admissioncontrol",
    "fault",
}

app_structure = {
    "envoy": {
        "client": "frontend",
        "server": "ping",
    },
    "mrpc": {
        "client": "rpc_echo_frontend",
        "server": "rpc_echo_server",
    },
}

yml_header = {
    "envoy": """app_name: "ping_pong_bench"
app_structure:
-   "frontend->ping"
""",
    "mrpc": """app_name: "rpc_echo_bench"
app_structure:
-   "rpc_echo_frontend->rpc_echo_server"
""",
}

gen_dir = os.path.join(EXP_DIR, "gen")
report_dir = os.path.join(EXP_DIR, "report")


def gen_user_spec(backend: str, num: int, path: str) -> str:
    EVAL_LOG.info(
        f"Randomly generate user specification, backend = {backend}, num = {num}"
    )
    assert path.endswith(".yml"), "wrong user spec format"
    spec = yml_header[backend] + select_random_elements(
        app_structure[backend]["client"], app_structure[backend]["server"], num
    )
    with open(path, "w") as f:
        f.write(spec)
    return spec


def attach_elements(backend: str):
    if backend == "mrpc":
        raise NotImplementedError
    elif backend == "envoy":
        pass
    else:
        raise NotImplementedError


def detach_elements(backend: str):
    if backend == "mrpc":
        raise NotImplementedError
    elif backend == "envoy":
        execute_local(["kubectl", "delete", "envoyfilter", "--all"])
        ksync()
    else:
        raise NotImplementedError


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", type=str, required=True, choices=["mrpc", "envoy"])
    parser.add_argument("--num", type=int, help="element chain length", default=3)
    parser.add_argument("--debug", help="Print backend debug info", action="store_true")
    parser.add_argument(
        "--latency_duration", help="wrk duration for latency test", type=int, default=60
    )
    parser.add_argument(
        "--cpu_duration", help="wrk2 duration for cpu usage test", type=int, default=60
    )
    parser.add_argument(
        "--target_rate", help="wrk2 request rate", type=int, default=2000
    )
    args = parser.parse_args()

    init_logging(args.debug)

    element_pool = globals()[f"{args.backend}_element_pool"]
    set_element_pool(element_pool)

    os.system(f"rm {gen_dir} -rf")
    os.makedirs(gen_dir)

    spec = gen_user_spec(args.backend, args.num, os.path.join(gen_dir, "test.yml"))
    ncpu = int(execute_local(["nproc"]))
    results = {"pre-optimize": {}, "post-optimize": {}}

    for mode in ["pre-optimize", "post-optimize"]:
        compile_cmd = [
            "python3",
            os.path.join(ROOT_DIR, "compiler/main.py"),
            "--spec",
            os.path.join(EXP_DIR, "gen/test.yml"),
            "--backend",
            args.backend,
            "--pseudo_impl",
        ]
        if mode == "pre-optimize":
            compile_cmd.append("--no_optimize")
        EVAL_LOG.info(f"Compiling, mode = {mode}")
        execute_local(compile_cmd)

        attach_elements(args.backend)

        EVAL_LOG.info(f"Running latency tests for {args.latency_duration}s")
        results[mode]["latency"] = run_wrk_and_get_latency(args.latency_duration)
        EVAL_LOG.info(f"Running cpu usage tests for {args.cpu_duration}s")
        results[mode]["cpu"] = run_wrk2_and_get_cpu(
            ["h2", "h3"],
            cores_per_node=ncpu,
            mpstat_duration=args.cpu_duration // 2,
            wrk2_duration=args.cpu_duration,
            target_rate=args.target_rate,
        )

        detach_elements(args.backend)

    EVAL_LOG.info("Dump report")
    os.makedirs(report_dir, exist_ok=True)
    ind = len(os.listdir(report_dir)) + 1
    with open(os.path.join(report_dir, f"report_{ind}.yml"), "w") as f:
        f.write(spec)
        f.write("---\n")
        f.write(yaml.dump(results, default_flow_style=False, indent=4))
