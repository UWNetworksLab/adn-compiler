import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.absolute()))

from compiler import element_spec_base_dir, graph_base_dir
from compiler.graph.backend.utils import *
from compiler.graph.logger import EVAL_LOG, init_logging
from experiments import EXP_DIR, ROOT_DIR
from experiments.utils import *

# Some elements
envoy_element_pool = [
    # "cache",
    # "fault",
    # "ratelimit",
    # "lbsticky",
    "logging",
    # "mutation",
    # "acl",
    # "metrics",
    # "admissioncontrol",
    # "encryptping-decryptping",
    # "bandwidthlimit",
    # "circuitbreaker",
]

envoy_pair_pool = [
    "encryptping-decryptping",
]

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
        "-t", "--trials", help="number of trails to run", type=int, default=10
    )
    parser.add_argument(
        "--latency_duration", help="wrk duration for latency test", type=int, default=60
    )
    parser.add_argument(
        "--cpu_duration", help="wrk2 duration for cpu usage test", type=int, default=60
    )
    parser.add_argument(
        "--target_rate", help="wrk2 request rate", type=int, default=10000
    )
    return parser.parse_args()


def generate_user_spec(backend: str, num: int, path: str) -> str:
    assert path.endswith(".yml"), "wrong user spec format"
    selected_elements, selected_yml_str = select_random_elements(
        app_structure[backend]["client"], app_structure[backend]["server"], num
    )
    spec = yml_header[backend] + selected_yml_str
    with open(path, "w") as f:
        f.write(spec)
    return selected_elements, spec


def run_trial(curr_trial_num) -> List[Element]:
    # Step 1: Generate a random user specification based on the backend and number of elements
    EVAL_LOG.info(
        f"Randomly generate user specification, backend = {args.backend}, number of element to generate = {args.num}..."
    )
    selected_elements, spec = generate_user_spec(
        args.backend,
        args.num,
        os.path.join(gen_dir, "randomly_generated_spec.yml"),
    )
    EVAL_LOG.info(f"Selected Elements and their config: {selected_elements}")

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
            "--replica",
            "10",
        ]

        if mode == "pre-optimize":
            compile_cmd.append("--no_optimize")

        EVAL_LOG.info(f"[{mode}] Compiling spec...")
        execute_local(compile_cmd)

        EVAL_LOG.info(
            f"[{mode}] Backend code and deployment script generated. Deploying the application..."
        )
        # Clean up the k8s deployments
        kdestroy()

        # Deploy the application and elements. Wait until they are in running state...
        kapply(os.path.join(graph_base_dir, "generated"))
        ksync()
        EVAL_LOG.info(f"[{mode}] Application deployed...")
        time.sleep(10)

        # Perform some basic testing to see if the application is healthy
        if test_application():
            EVAL_LOG.info(f"[{mode}] Application is healthy...")
        else:
            EVAL_LOG.info(f"[{mode}] Application is unhealthy. Restarting the trial...")
            return selected_elements

        # Run wrk to get the service time
        EVAL_LOG.info(
            f"[{mode}] Running latency (service time) tests for {args.latency_duration}s..."
        )
        results[mode]["service time(us)"] = run_wrk_and_get_latency(
            args.latency_duration
        )

        # Run wrk2 to get the tail latency
        EVAL_LOG.info(
            f"[{mode}] Running tail latency tests for {args.latency_duration}s and request rate {args.target_rate*0.4} req/sec..."
        )
        results[mode]["tail latency(us)"] = run_wrk2_and_get_tail_latency(
            args.latency_duration,
            args.target_rate * 0.4,
        )

        # Run wrk2 to get the CPU usage
        EVAL_LOG.info(
            f"[{mode}] Running cpu usage tests for {args.cpu_duration}s and request rate {args.target_rate} req/sec..."
        )
        results[mode]["CPU usage(VCores)"] = run_wrk2_and_get_cpu(
            # ["h2", "h3"],
            ["h2"],
            cores_per_node=ncpu,
            mpstat_duration=args.cpu_duration // 2,
            wrk2_duration=args.cpu_duration,
            target_rate=args.target_rate,
        )

        # Clean up the k8s deployments
        kdestroy()

    EVAL_LOG.info("Dumping report...")
    with open(os.path.join(report_dir, f"report_{curr_trial_num}.yml"), "w") as f:
        f.write(spec)
        f.write("---\n")
        f.write(yaml.dump(results, default_flow_style=False, indent=4))

    return None


if __name__ == "__main__":

    # Some initializaion
    args = parse_args()
    init_logging(args.debug)

    # Some housekeeping
    element_pool = globals()[f"{args.backend}_element_pool"]
    pair_pool = globals()[f"{args.backend}_pair_pool"]
    set_element_pool(element_pool, pair_pool)

    os.system(f"rm {gen_dir} -rf")
    os.makedirs(gen_dir)
    os.makedirs(report_parent_dir, exist_ok=True)
    os.makedirs(report_dir)

    EVAL_LOG.info(f"Pre-compiling all {len(element_pool)} elements...")
    pre_compiler_all_elements(element_pool)

    completed_trials = 0
    total_trials = 0
    failed_configurations = []
    total_time = 0

    while completed_trials < args.trials:
        average_time_per_trial = (
            total_time / completed_trials if completed_trials > 0 else 0
        )
        EVAL_LOG.info(
            f"Running trial # {completed_trials}/{args.trials}. Average time per-trial is {average_time_per_trial:.2f} seconds..."
        )

        total_trials += 1
        start_time = time.time()
        # Run a trial. If failed, it will return the failed configuration. Otherwise, none.
        total_time += time.time() - start_time
        result = run_trial(completed_trials)
        if not result:
            completed_trials += 1
        else:
            failed_configurations.append(result)

    EVAL_LOG.info(
        f"Experiment completed. Total trials = {total_trials}, successful trials = {completed_trials}"
    )
    EVAL_LOG.info(f"Failed configurations: {failed_configurations}")
