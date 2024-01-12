import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.absolute()))

from compiler import element_spec_base_dir, graph_base_dir
from compiler.graph.backend.utils import *
from compiler.graph.logger import EVAL_LOG, init_logging
from experiments import EXP_DIR, ROOT_DIR
from experiments.utils import *

# Some elements
envoy_element_pool = {
    "cache",
    "fault",
    "ratelimit",
    "lbsticky",
    "logging",
    "mutation",
    "acl",
    "metrics",
    "admissioncontrol",
    # "encrypt",
    "bandwidthlimit",
    "circuitbreaker",
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
app_manifest: "ping-pong-app.yaml"
app_structure:
-   "frontend->ping"
""",
    "mrpc": """app_name: "rpc_echo_bench"
app_structure:
-   "rpc_echo_frontend->rpc_echo_server"
""",
}

gen_dir = os.path.join(EXP_DIR, "generated")
report_parent_dir = os.path.join(EXP_DIR, "report")
current_time = datetime.now().strftime("%m_%d_%H_%M_%S")
report_dir = os.path.join(report_parent_dir, "trail_" + current_time)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-b", "--backend", type=str, required=True, choices=["mrpc", "envoy"]
    )
    parser.add_argument("-n", "--num", type=int, help="element chain length", default=3)
    parser.add_argument("--debug", help="Print backend debug info", action="store_true")
    parser.add_argument(
        "--trials", help="number of trails to run", type=int, default=10
    )
    parser.add_argument(
        "--latency_duration", help="wrk duration for latency test", type=int, default=60
    )
    parser.add_argument(
        "--cpu_duration", help="wrk2 duration for cpu usage test", type=int, default=60
    )
    parser.add_argument(
        "--target_rate", help="wrk2 request rate", type=int, default=2000
    )
    return parser.parse_args()


def gen_user_spec(backend: str, num: int, path: str) -> str:
    assert path.endswith(".yml"), "wrong user spec format"
    spec = yml_header[backend] + select_random_elements(
        app_structure[backend]["client"], app_structure[backend]["server"], num
    )
    with open(path, "w") as f:
        f.write(spec)
    return spec


if __name__ == "__main__":

    # Some initializaion
    args = parse_args()
    init_logging(args.debug)

    # Some housekeeping
    element_pool = globals()[f"{args.backend}_element_pool"]
    set_element_pool(element_pool)

    os.system(f"rm {gen_dir} -rf")
    os.makedirs(gen_dir)
    os.makedirs(report_parent_dir, exist_ok=True)
    os.makedirs(report_dir)

    for i in range(args.trials):
        # Step 1: Generate a random user specification based on the backend and number of elements
        EVAL_LOG.info(
            f"Randomly generate user specification, backend = {args.backend}, number of element to generate = {args.num}, trail # {i}"
        )
        spec = gen_user_spec(
            args.backend,
            args.num,
            os.path.join(gen_dir, "randomly_generated_spec.yml"),
        )

        ncpu = int(execute_local(["nproc"]))
        results = {"pre-optimize": {}, "post-optimize": {}}

        # Step 2: Collect latency and CPU result for pre- and post- optimization
        for mode in ["pre-optimize", "post-optimize"]:

            # Step 2.1: Compile the elements
            compile_cmd = [
                "python3.10",
                os.path.join(ROOT_DIR, "compiler/main.py"),
                "--spec",
                os.path.join(EXP_DIR, "generated/randomly_generated_spec.yml"),
                "--backend",
                args.backend,
            ]

            if mode == "pre-optimize":
                compile_cmd.append("--no_optimize")

            EVAL_LOG.info(f"Compiling spec, mode = {mode} ...")
            # Step 2.2: Deploy the application and attach the elements
            execute_local(compile_cmd)

            EVAL_LOG.info(
                f"Backend code and deployment script generated. Deploying the application..."
            )
            # Clean up the k8s deployments
            kdestroy()

            # Deploy the application and elements. Wait until they are in running state...
            kapply(os.path.join(graph_base_dir, "generated"))
            EVAL_LOG.info(f"Application deployed...")

            #     break
            # break

            # Step 2.4: Run wrk to get the service time
            EVAL_LOG.info(
                f"Running latency (service time) tests for {args.latency_duration}s..."
            )
            results[mode]["service time(us)"] = run_wrk_and_get_latency(
                args.latency_duration
            )

            # Step 2.5: Run wrk2 to get the tail latency
            EVAL_LOG.info(f"Running tail latency tests for {args.latency_duration}s...")
            results[mode]["tail latency(us)"] = run_wrk2_and_get_tail_latency(
                args.latency_duration
            )

            # Step 2.6: Run wrk2 to get the CPU usage
            EVAL_LOG.info(f"Running cpu usage tests for {args.cpu_duration}s...")
            results[mode]["CPU usage(VCores)"] = run_wrk2_and_get_cpu(
                # ["h2", "h3"],
                ["h2"],
                cores_per_node=ncpu,
                mpstat_duration=args.cpu_duration // 2,
                wrk2_duration=args.cpu_duration,
                target_rate=args.target_rate,
            )

            # Clean up
            kdestroy()

        EVAL_LOG.info("Dumping report...")
        with open(os.path.join(report_dir, f"report_{i}.yml"), "w") as f:
            f.write(spec)
            f.write("---\n")
            f.write(yaml.dump(results, default_flow_style=False, indent=4))
