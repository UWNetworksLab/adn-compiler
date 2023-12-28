"""
Utility functions for executing commands in remote hosts/containers.
"""
import os
import subprocess
import time
from typing import List

from kubernetes import client, config

from compiler.graph.logger import BACKEND_LOG


def error_handling(res, msg):
    """Output the given error message and the stderr contents if the subprocess exits abnormally.

    Args:
        res (CompletedProcess[bytes]): the returned object from subproces.run().
        msg: error message printed before the stderr contents.
    """
    if res.returncode != 0:
        BACKEND_LOG.error(f"{msg}\nError msg: {res.stderr.decode('utf-8')}")
        raise Exception


def execute_remote_host(host: str, cmd: List[str]) -> str:
    """Execute commands on remote host.

    Args:
        host: hostname.
        cmd: A list including the command and all options.

    Returns:
        The output of the command, or "xxx"if "--dry_run" is provided.
    """
    if os.getenv("DRY_RUN") == "1":
        return "xxx"
    BACKEND_LOG.debug(f"Executing command {' '.join(cmd)} on host {host}...")
    res = subprocess.run(["ssh", host] + cmd, capture_output=True)
    error_handling(res, f"Error when executing command")
    return res.stdout.decode("utf-8")


def execute_remote_container(service: str, host: str, cmd: List[str]) -> str:
    """Execute commands in remote docker container.

    Args:
        service: Service name (determines the container name).
        host: hostname.
        cmd: A list including the command and all arguments.

    Returns:
        The output of the command, or "xxx" if "--dry_run" is provided.
    """
    BACKEND_LOG.debug(f"Executing command {' '.join(cmd)} in {service.lower()}...")
    if os.getenv("DRY_RUN") == "1":
        return "xxx"
    res = subprocess.run(
        ["ssh", host, "docker", "exec", service.lower()] + cmd,
        capture_output=True,
    )
    error_handling(res, f"Error when executing command {cmd} in container")
    return res.stdout.decode("utf-8")


def execute_local(cmd: List[str]) -> str:
    """Execute commands in localhost

    Args:
        cmd: A list including the command and all arguments.

    Returns:
        The output of the command, or "xxx" if "--dry_run" is provided.
    """
    BACKEND_LOG.debug(f"Executing command {' '.join(cmd)}...")
    res = subprocess.run(cmd, capture_output=True)
    error_handling(res, f"Error when executing command {cmd}")
    return res.stdout.decode("utf-8")


def copy_remote_host(host: str, local_path: str, remote_path: str):
    """Copy local files/directories into remote host.

    Args:
        host: hostname.
        local_path: Path to the local file/directory.
        remote_path: The target path in the remote host.
    """
    BACKEND_LOG.debug(f"Copy file {local_path} to {host}")
    if os.getenv("DRY_RUN") == "1":
        return
    res = subprocess.run(
        ["rsync", "-avz", local_path, f"{host}:{remote_path}"], capture_output=True
    )
    error_handling(res, f"Error when rsync-ing file {local_path}")


def copy_remote_container(service: str, host: str, local_path: str, remote_path: str):
    """Copy local files/directories into remote containers.

    Args:
        service: Servie name.
        host: hostname.
        local_path: Path to the local file/directory.
        remote_path: The target path in the remote container.
    """
    BACKEND_LOG.debug(f"Copy file {local_path} to {service.lower()}")
    if os.getenv("DRY_RUN") == "1":
        return
    filename = local_path.split("/")[-1]
    res = subprocess.run(
        ["rsync", "-avz", local_path, f"{host}:/tmp"], capture_output=True
    )
    error_handling(res, f"Error when rsync-ing file {local_path}")
    execute_remote_host(
        host,
        ["docker", "cp", f"/tmp/{filename}", f"{service.lower()}:{remote_path}"],
    )
    execute_remote_host(host, ["rm", "-r", f"/tmp/{filename}"])


def wait_until_running(namespace: str = "default"):
    """Wait until all pods are running. Ususally used after `kubectl delete` to ensure synchronization.

    Args:
        namespace(optional): the pod namespace to monitor.
    """
    config.load_kube_config()

    v1 = client.CoreV1Api()

    # Find the status of echo server and wait for it.
    while True:
        ret = v1.list_namespaced_pod(namespace=namespace)
        status = [
            i.status.phase == "Running" for i in ret.items if "echo" in i.metadata.name
        ]
        if False not in status:
            BACKEND_LOG.debug("kpods check done")
            return
        else:
            time.sleep(2)


def ksync():
    """Restart pods to ensure all changes are synchronized"""
    execute_local(["kubectl", "delete", "pods", "--all"])
    wait_until_running()


def kapply(file: str):
    """Apply changes in file to knodes.

    Args:
        file: configuration filename.
    """
    execute_local(["kubectl", "apply", "-f", file])
    ksync()
