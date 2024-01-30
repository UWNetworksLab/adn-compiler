import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

sys.path.append(str(Path(__file__).parent.parent.absolute()))

from compiler import graph_base_dir
from compiler.graph.backend.utils import *
from compiler.graph.logger import EVAL_LOG, init_logging
from experiments import EXP_DIR, ROOT_DIR
from experiments.utils_overhead import *

node_pool = ["h2"]

# Some elements
envoy_element_pool = [
    "cachestrong",
    "fault",
    "ratelimit",
    "lbstickystrong",
    "logging",
    "mutation",
    "aclstrong",
    "metrics",
    "admissioncontrol",
    "zzencrypt-aadecrypt",
    "bandwidthlimit",
    "circuitbreaker",
]

envoy_pair_pool = [
    "zzencrypt-aadecrypt",
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
    "envoy": """app_name: "ping-pong-app"
app_structure:
-   "frontend->ping"
""",
    "mrpc": """app_name: "rpc_echo_bench"
app_structure:
-   "rpc_echo_frontend->rpc_echo_server"
""",
}

gen_dir = os.path.join(EXP_DIR, "generated_compiler_overhead")
report_parent_dir = os.path.join(EXP_DIR, "report_compiler_overhead")
current_time = datetime.now().strftime("%m_%d_%H_%M_%S")
report_dir = os.path.join(report_parent_dir, "trial_" + current_time)
wrk_script_path = os.path.join(EXP_DIR, "wrk/ping.lua")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-b", "--backend", type=str, required=True, choices=["mrpc", "envoy"]
    )
    parser.add_argument("--debug", help="Print backend debug info", action="store_true")
    parser.add_argument(
        "-t", "--trials", help="number of trails to run", type=int, default=5
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


def generate_user_spec(backend: str, element_name: str, path: str):
    assert path.endswith(".yml"), "wrong user spec format"
    (selected_elements, selected_yml_str,) = select_random_elements(
        app_structure[backend]["client"], app_structure[backend]["server"], element_name
    )
    spec = yml_header[backend] + selected_yml_str
    with open(path.replace(".yml", ".yml"), "w") as f:
        f.write(spec)
    return selected_elements, spec


def run_trial(curr_trial_num) -> List[Element]:
    # Step 1: Generate a random user specification based on the backend and number of elements
    EVAL_LOG.info(f"Randomly generate user specification, backend = {args.backend}...")

    for element_name in envoy_element_pool:

        selected_elements, spec = generate_user_spec(
            args.backend,
            element_name,
            os.path.join(gen_dir, "randomly_generated_spec.yml"),
        )
        EVAL_LOG.info(f"Selected Elements and their config: {selected_elements}")

        ncpu = int(execute_local(["nproc"]))
        results = {
            "autogen": {},
            "handwritten": {},
        }
        for mode in results.keys():
            spec_path = "generated_compiler_overhead/randomly_generated_spec.yml"

            # Compile the elements
            compile_cmd = [
                "python3.10",
                os.path.join(ROOT_DIR, "compiler/main.py"),
                "--spec",
                os.path.join(EXP_DIR, spec_path),
                "--backend",
                args.backend,
                "--replica",
                "10",
            ]

            compile_cmd.extend(["--opt_level", "no"])
            if mode == "handwritten":
                compile_cmd.extend(["--pseudo_impl"])

            EVAL_LOG.info(f"[{mode}] Compiling spec...")
            execute_local(compile_cmd)

            # Save the generated Graph IR
            with open(os.path.join(graph_base_dir, "generated/gir_summary"), "r") as f:
                yml_list_plain = list(yaml.safe_load_all(f))
            results[mode]["graphir"] = yml_list_plain[0]["graphir"][0]

            EVAL_LOG.info(
                f"[{mode}] Printing final GraphIR: {results[mode]['graphir']}"
            )

            EVAL_LOG.info(
                f"[{mode}] Backend code and deployment script generated. Deploying the application..."
            )

            # Clean up the k8s deployments
            kdestroy()

            # Deploy the application and elements. Wait until they are in running state...
            kapply_and_sync(
                os.path.join(graph_base_dir, "generated", "ping-pong-app_deploy")
            )
            EVAL_LOG.info(f"[{mode}] Application deployed...")
            time.sleep(10)

            # Perform some basic testing to see if the application is healthy
            if test_application():
                EVAL_LOG.info(f"Application is healthy...")
            else:
                EVAL_LOG.warning(f"Application is unhealthy. Restarting the trial...")
                return selected_elements, "Application Health Check Failed"

            # Run wrk to get the service time
            EVAL_LOG.info(
                f"[{mode}] Running latency (service time) tests for {args.latency_duration}s..."
            )
            results[mode]["service time(us)"] = run_wrk_and_get_latency(
                wrk_script_path, args.latency_duration
            )

            if not results[mode]["service time(us)"]:
                EVAL_LOG.warning(
                    f"[{mode}] service time test (wrk) returned an error. Restarting the trial..."
                )
                return selected_elements, "Service Time Test Failed"

            # Run wrk2 to get the tail latency
            EVAL_LOG.info(
                f"[{mode}] Running tail latency tests for {args.latency_duration}s and request rate {args.target_rate*0.4} req/sec..."
            )
            results[mode]["tail latency(us)"] = run_wrk2_and_get_tail_latency(
                wrk_script_path,
                args.latency_duration,
                args.target_rate,
            )

            if not results[mode]["tail latency(us)"]:
                EVAL_LOG.warning(
                    f"[{mode}] Tail latency test (wrk2) returned an error. Restarting the trial..."
                )
                return selected_elements, "Tail Latency Test Failed"

            # Run wrk2 to get the CPU usage
            EVAL_LOG.info(
                f"[{mode}] Running cpu usage tests for {args.cpu_duration}s and request rate {args.target_rate*1.0} req/sec..."
            )
            results[mode]["CPU usage(VCores)"] = run_wrk2_and_get_cpu(
                node_pool,
                wrk_script_path,
                cores_per_node=ncpu,
                mpstat_duration=args.cpu_duration // 2,
                wrk2_duration=args.cpu_duration,
                target_rate=args.target_rate,
            )

            if not results[mode]["CPU usage(VCores)"]:
                EVAL_LOG.warning(
                    f"[{mode}] CPU usage test (wrk2) returned an error. Restarting the trial..."
                )
                return selected_elements, "CPU Usage Test Failed"

            # Clean up the k8s deployments
            kdestroy()

        EVAL_LOG.info("Dumping report...")
        with open(
            os.path.join(report_dir, f"report_{element_name}_{curr_trial_num}.yml"), "w"
        ) as f:
            f.write(spec)
            f.write("---\n")
            f.write(yaml.dump(results, default_flow_style=False, indent=4))

    return None, None


if __name__ == "__main__":

    # Some initializaion
    args = parse_args()
    init_logging(args.debug)

    element_pool = globals()[f"{args.backend}_element_pool"]
    pair_pool = globals()[f"{args.backend}_pair_pool"]
    set_element_pool(element_pool, pair_pool)

    os.environ["ELEMENT_SPEC_BASE_DIR"] = os.path.join(
        EXP_DIR, "elements/ping_elements"
    )

    os.system(f"rm {gen_dir} -rf")
    os.makedirs(gen_dir)
    os.makedirs(report_parent_dir, exist_ok=True)
    os.makedirs(report_dir)

    completed_trials = 0
    total_trials = 0
    failed_configurations = []
    total_time = 0

    # Disable mtls for istio
    kapply_and_sync(os.path.join(ROOT_DIR, "utils"))

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
        failed_configuration, reason = run_trial(completed_trials)
        total_time += time.time() - start_time
        if not failed_configuration:
            completed_trials += 1
        else:
            failed_configurations.append([failed_configuration, reason])

    EVAL_LOG.info(
        f"Experiment completed. Total trials = {total_trials}, successful trials = {completed_trials}, average time per-trial = {total_time/completed_trials:.2f} seconds."
    )
    EVAL_LOG.info(f"Report saved to {report_dir}")
    EVAL_LOG.info(f"Failed configurations: {failed_configurations}")
