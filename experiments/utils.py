import os
import random
import re
import statistics
import subprocess
from pathlib import Path

import yaml

from compiler import proto_base_dir
from compiler.graph.logger import EVAL_LOG

# from experiments import EXP_DIR


EXP_DIR = Path(__file__).parent

element_pool = [
    "fault",
    "cache",
    "ratelimit",
    "loadbalance",
    "logging",
    "mutation",
    "accesscontrol",
    "metrics",
    "admissioncontrol",
    "compression",
    "encryption",
]
# TODO: update the configuration dict. Add script to generate random configurations.
element_configs = {
    "fault": None,
    "cache": None,
    "ratelimit": None,
    "loadbalance": None,
    "logging": None,
    "mutation": None,
    "accesscontrol": None,
    "metrics": None,
    "admissioncontrol": None,
    "compression": None,
    "encryption": None,
    "acl": None,
    "bandwidthlimit": None,
    "circuitbreaker": None,
}


def set_element_pool(pool):
    global element_pool
    element_pool = pool


class Element:
    """Represents an element with a name, position, and optional configuration."""

    def __init__(self, name: str, position: str, proto: str, method: str, config=None):
        self.name = name
        self.position = position
        self.config = config
        self.proto = proto
        self.method = method

    def add_config(self, config):
        """Adds or updates the configuration for the element."""
        self.config = config

    def to_dict(self):
        """Convert the Element instance to a dictionary for YAML formatting."""
        element_dict = {"name": self.name, "method": self.method, "proto": self.proto}
        if self.position != "none":
            element_dict["position"] = self.position
        if self.config:
            element_dict["config"] = self.config.split(", ")
        return element_dict

    def __repr__(self):
        return f"Element(Name={self.name}, Position={self.position}, Configurations={self.config})"


def select_random_elements(client: str, server: str, number: int):
    """Selects a random number of elements with random positions."""
    # TODO(xz): also generate random configurations. They can be static for now.
    selected, positions = [], ["C", "S", "C/S"]  # C: client, S: server, C/S: don't care
    for name in random.sample(element_pool, number):
        e = Element(
            name,
            position=random.choice(positions),
            proto=os.path.join(
                proto_base_dir, "ping.proto"
            ),  # TODO: This should be configurable
            method="PingEcho",
            # config=element_configs[name],
        )
        selected.append(e)

    # Sort elements by position (client->client/server->server)
    def sort_key(element: Element):
        order = {"C": 1, "C/S": 2, "S": 3}
        return order.get(element.position, 0)

    sorted_elements = sorted(selected, key=sort_key)

    # Convert elements to YAML format
    yaml_data = {
        "edge": {
            f"{client}->{server}": [element.to_dict() for element in sorted_elements]
        },
    }

    # Export to YAML format
    yaml_str = yaml.dump(yaml_data, default_flow_style=False, indent=4)
    return yaml_str


# Function to convert to microseconds
def convert_to_us(value, unit):
    if unit == "ms":
        return float(value) * 1000
    elif unit == "s":
        return float(value) * 1000000
    else:  # 'us'
        return float(value)


def run_wrk_and_get_latency(duration=20):
    # # TODO: Add script
    cmd = [
        os.path.join(EXP_DIR, "wrk/wrk"),
        "-t 1",
        "-c 1",
        "http://10.96.88.88:8080/ping-echo",
        f"-d {duration}",
        "-L",
    ]
    proc = subprocess.Popen(
        " ".join(cmd),
        shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for the command to complete
    stdout_data, stderr_data = proc.communicate()

    # Check if there was an error
    if proc.returncode != 0:
        print("Error executing wrk command:")
        print(stderr_data.decode())
    else:
        # Parse the output
        output = stdout_data.decode()

        # Regular expressions to find the results
        latency_50_pattern = r"50%\s+(\d+\.?\d*)(us|ms|s)"
        latency_99_pattern = r"99%\s+(\d+\.?\d*)(us|ms|s)"
        avg_latency_pattern = r"Latency\s+(\d+\.?\d*)(us|ms|s)"
        req_sec_pattern = r"Requests/sec:\s+(\d+\.?\d*)"

        # Search for patterns and convert to microseconds
        latency_50_match = re.search(latency_50_pattern, output)
        latency_50 = (
            convert_to_us(*latency_50_match.groups())
            if latency_50_match
            else "Not found"
        )

        latency_99_match = re.search(latency_99_pattern, output)
        latency_99 = (
            convert_to_us(*latency_99_match.groups())
            if latency_99_match
            else "Not found"
        )

        avg_latency_match = re.search(avg_latency_pattern, output)
        avg_latency = (
            convert_to_us(*avg_latency_match.groups())
            if avg_latency_match
            else "Not found"
        )

        req_sec = re.search(req_sec_pattern, output)
        req_sec = req_sec.group(1) if req_sec else "Not found"

        return {
            "p50": float(latency_50),
            "p99": float(latency_99),
            "avg": float(avg_latency),
            "rps": float(req_sec),
        }


def get_virtual_cores(node_names, core_count, duration):
    total_util = []
    for node_name in node_names:
        cmd = ["ssh", node_name, "mpstat", "1", str(duration)]
        result = subprocess.run(cmd, stdout=subprocess.PIPE)
        result_average = result.stdout.decode("utf-8").split("\n")[-2].split()
        per_node_util = 100.00 - float(result_average[-1])
        total_util.append(per_node_util)

    virtual_cores = sum(total_util) * core_count / 100
    return virtual_cores


def run_wrk2_and_get_cpu(
    node_names,
    cores_per_node=64,
    mpstat_duration=30,
    wrk2_duration=60,
    target_rate=2000,
):
    cmd = [
        os.path.join(EXP_DIR, "wrk/wrk2"),
        "-t 10",
        "-c 100",
        "http://10.96.88.88:8080/ping-echo",
        "-d DURATION".replace("DURATION", str(wrk2_duration)),
        "-R " + str(target_rate),
    ]
    proc = subprocess.Popen(
        " ".join(cmd),
        shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    vcores = round(get_virtual_cores(node_names, cores_per_node, mpstat_duration), 2)

    stdout_data, stderr_data = proc.communicate()

    # Check if there was an error
    if proc.returncode != 0:
        print("Error executing wrk2 command:")
        print(stderr_data.decode())
    else:
        # Parse the output
        output = stdout_data.decode()

        req_sec_pattern = r"Requests/sec:\s+(\d+\.?\d*)"

        req_sec = re.search(req_sec_pattern, output)
        req_sec = req_sec.group(1) if req_sec else "Not found"

        # Check if the target request rate is achieved
        if float(req_sec) < target_rate * 0.95:
            EVAL_LOG.warning(
                "Warning: the target request rate is not achieved. Target: "
                + str(target_rate)
                + ", achieved: "
                + str(req_sec)
                + "."
            )

    return vcores


def run_wrk2_and_get_tail_latency(
    wrk2_duration=20,
    target_rate=1000,
):
    cmd = [
        os.path.join(EXP_DIR, "wrk/wrk2"),
        "-t 10",
        "-c 100",
        "http://10.96.88.88:8080/ping-echo",
        "-d DURATION".replace("DURATION", str(wrk2_duration)),
        "-R " + str(target_rate),
        "-L ",
    ]
    proc = subprocess.Popen(
        " ".join(cmd),
        shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for the command to complete
    stdout_data, stderr_data = proc.communicate()

    # Check if there was an error
    if proc.returncode != 0:
        print("Error executing wrk2 command:")
        print(stderr_data.decode())
    else:
        # Parse the output
        output = stdout_data.decode()

        # Regular expressions to find the results
        latency_50_pattern = r"50.000%\s+(\d+\.?\d*)(us|ms|s)"
        latency_99_pattern = r"99.000%\s+(\d+\.?\d*)(us|ms|s)"
        avg_latency_pattern = r"Latency\s+(\d+\.?\d*)(us|ms|s)"
        req_sec_pattern = r"Requests/sec:\s+(\d+\.?\d*)"

        # Search for patterns and convert to microseconds
        latency_50_match = re.search(latency_50_pattern, output)
        latency_50 = (
            convert_to_us(*latency_50_match.groups())
            if latency_50_match
            else "Not found"
        )

        latency_99_match = re.search(latency_99_pattern, output)
        latency_99 = (
            convert_to_us(*latency_99_match.groups())
            if latency_99_match
            else "Not found"
        )

        avg_latency_match = re.search(avg_latency_pattern, output)
        avg_latency = (
            convert_to_us(*avg_latency_match.groups())
            if avg_latency_match
            else "Not found"
        )

        req_sec = re.search(req_sec_pattern, output)
        req_sec = req_sec.group(1) if req_sec else "Not found"

        if float(req_sec) < target_rate * 0.95:
            EVAL_LOG.warning(
                "Warning: the target request rate is not achieved. Target: "
                + str(target_rate)
                + ", achieved: "
                + str(req_sec)
                + "."
            )

        return {
            "p50": float(latency_50),
            "p99": float(latency_99),
            "avg": float(avg_latency),
            "rps": float(req_sec),
        }


if __name__ == "__main__":
    run_wrk2_and_get_tail_latency()
