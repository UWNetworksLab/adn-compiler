"""
The file implements Mrpc backend, which is responsible for reconfiguring phoenixos,
installing new elements, and generating attach/detach scripts.
"""
from __future__ import annotations

import os
from collections import defaultdict
from typing import Dict, List

import tomli
import tomli_w

from compiler import graph_base_dir
from compiler.graph.backend import BACKEND_CONFIG_DIR
from compiler.graph.backend.boilerplate import addon_loader, attach_mrpc, detach_mrpc
from compiler.graph.backend.config import service_pos_dict, sids
from compiler.graph.backend.utils import copy_remote_container, execute_remote_container
from compiler.graph.ir import GraphIR
from compiler.graph.ir.element import AbsElement

attach_cmd, detach_cmd = [], []


def gen_attach_detach(
    service: str,
    host: str,
    pid: str,
    sid: str,
    req_chain: List[AbsElement],
    res_chain: List[AbsElement],
    pos: str,
):
    """Generate Mrpc attach/detach scripts and copy them to target containers.

    Args:
        service: Service name.
        host: hostname that the service is deployed on.
        pid: pid of the service.
        sid: sid of the thread where scripts should be deployed.
        req_chain: List of elements on the request chain.
        res_chain: List of elements on the response chain.
        pos: "client" or "server", which affects the order of Mrpc engines.
    """
    assert pos in ["client", "server"], "invalid position"
    pre = "Mrpc" if pos == "client" else "TcpRpcAdapter"
    installed = {"Mrpc", "TcpRpcAdapter"}
    group_list = ["Mrpc", "TcpRpcAdapter"]
    for element in req_chain:
        attach_filename = os.path.join(
            local_gen_dir, f"attach-{service}-{pos}-{element.desc}.toml"
        )
        detach_filename = os.path.join(
            local_gen_dir, f"detach-{service}-{pos}-{element.desc}.toml"
        )
        if pos == "client":
            contents = {
                "current": element.deploy_name,
                "tx_prev": pre,
                "tx_nxt": "TcpRpcAdapter",
                "rx_prev": "TcpRpcAdapter",
                "rx_nxt": pre,
                "group": [f"{ename}Engine" for ename in group_list],
                "config": element.configs,
            }
        else:
            contents = {
                "current": element.deploy_name,
                "tx_prev": "Mrpc",
                "tx_nxt": pre,
                "rx_prev": pre,
                "rx_nxt": "Mrpc",
                "group": [f"{ename}Engine" for ename in group_list],
                "config": element.configs,
            }
        # Find the currently installed prev/next element on the response chain.
        # for res_ele in res_chain:
        #     if res_ele.desc == element.desc:
        #         break
        #     if res_ele.desc in installed:
        #         contents["res_next"] = res_ele.deploy_name
        # for res_ele in res_chain[::-1]:
        #     if res_ele.desc == element.desc:
        #         break
        #     if res_ele.desc in installed:
        #         contents["res_prev"] = res_ele.deploy_name
        attach_script = attach_mrpc.format(**contents)
        detach_script = detach_mrpc.format(**contents)
        open(attach_filename, "w").write(attach_script)
        open(detach_filename, "w").write(detach_script)
        copy_remote_container(
            service, host, attach_filename, "/root/phoenix/experimental/mrpc/generated/"
        )
        copy_remote_container(
            service, host, detach_filename, "/root/phoenix/experimental/mrpc/generated/"
        )
        attach_cmd.append(
            f"ssh {host} docker exec {service.lower()} cargo run --release --bin addonctl -- --config experimental/mrpc/generated/{attach_filename.split('/')[-1]} --pid {pid} --sid {sid}"
        )
        detach_cmd.append(
            f"ssh {host} docker exec {service.lower()} cargo run --release --bin addonctl -- --config experimental/mrpc/generated/{detach_filename.split('/')[-1]} --pid {pid} --sid {sid}"
        )
        installed.add(element.desc)
        group_list = group_list[:-1] + [element.deploy_name] + group_list[-1:]
        pre = element.deploy_name


def gen_install(elements: List[AbsElement], service: str, host: str, placement: str):
    """Reconfigure phoenixos and install new elements in containers

    Args:
        elements: List of new elements to be deployed.
        service: Service name.
        host: hostname.
        placement: "client" or "server".
    """
    lib_names = list({element.lib_name for element in elements})
    dep = [
        (f"phoenix-api-policy-{lname}", {"path": f"generated/api/{lname}"})
        for lname in lib_names
    ]

    # update Cargo.toml
    with open(os.path.join(BACKEND_CONFIG_DIR, "Cargo_template.toml"), "r") as f:
        cargo_toml = tomli.loads(f.read())

    members: List[str] = cargo_toml["workspace"]["members"]
    for lname in lib_names:
        members.append(f"generated/api/{lname}")
        members.append(f"generated/plugin/{lname}")
        # TODO: the final version won't include initial engines in Cargo.toml
        # currently, we have to remove existing engines having the same name
        # as the new engine in Cargo.toml.
        dup_pkg = f"phoenix-api/policy/{lname}"
        if dup_pkg in members:
            members.remove(dup_pkg)
            members.remove(f"plugin/policy/{lname}")
    cargo_toml["workspace"]["dependencies"].update({i[0]: i[1] for i in dep})

    with open(os.path.join(local_gen_dir, "Cargo.toml"), "w") as f:
        f.write(tomli_w.dumps(cargo_toml))

    # update load-mrpc-plugins
    with open(os.path.join(local_gen_dir, "load-mrpc-plugins-gen.toml"), "w") as f:
        for element in elements:
            f.write(
                addon_loader.format(
                    name=element.desc, rlib=element.lib_name, config=element.configs
                )
            )

    container_gen_dir = "/root/phoenix/experimental/mrpc/generated"
    execute_remote_container(service, host, ["mkdir", "-p", container_gen_dir])
    execute_remote_container(service, host, ["rm", "-rf", f"{container_gen_dir}"])
    execute_remote_container(service, host, ["mkdir", "-p", f"{container_gen_dir}/api"])
    execute_remote_container(
        service, host, ["mkdir", "-p", f"{container_gen_dir}/plugin"]
    )
    # Overwrite Cargo.toml
    copy_remote_container(
        service,
        host,
        f"{graph_base_dir}/gen/Cargo.toml",
        "/root/phoenix/experimental/mrpc/Cargo.toml",
    )
    # Copy load-mrpc-plugins.toml
    copy_remote_container(
        service,
        host,
        f"{graph_base_dir}/gen/load-mrpc-plugins-gen.toml",
        f"{container_gen_dir}/load-mrpc-plugins-gen.toml",
    )
    for lname in lib_names:
        # Copy engine source code into the service container.
        copy_remote_container(
            service,
            host,
            f"{graph_base_dir}/gen/{lname}_{placement}_mrpc/api/{lname}",
            f"{container_gen_dir}/api/{lname}",
        )
        copy_remote_container(
            service,
            host,
            f"{graph_base_dir}/gen/{lname}_{placement}_mrpc/plugin/{lname}",
            f"{container_gen_dir}/plugin/{lname}",
        )
    # Compile & deploy engines.
    # execute_remote_container(
    #     service,
    #     host,
    #     ["cargo", "make", "--cwd", "experimental/mrpc", "build-mrpc-plugins"],
    # )
    # execute_remote_container(
    #     service, host, ["cargo", "make", "--cwd", "experimental/mrpc", "deploy-plugins"]
    # )
    # Upgrade phoenixos.
    execute_remote_container(
        service,
        host,
        [
            "cargo",
            "run",
            "--release",
            "--bin",
            "upgrade",
            "--",
            "--config",
            "experimental/mrpc/generated/load-mrpc-plugins-gen.toml",
        ],
    )


def scriptgen_mrpc(girs: Dict[str, GraphIR], app: str):
    """Upgrade phoenixos, install new engiens, and generate attach/detach scripts.

    Args:
        girs: A dictionary mapping edge name to corresponding graphir.
        service_pos: A dictionary mapping service name to hostname.
    """
    global local_gen_dir
    local_gen_dir = os.path.join(graph_base_dir, "gen")
    os.makedirs(local_gen_dir, exist_ok=True)

    service_pos = service_pos_dict[app]

    # Collect list of elements deployed on each service.
    service_elements_client: Dict[str, List[AbsElement]] = defaultdict(list)
    service_elements_server: Dict[str, List[AbsElement]] = defaultdict(list)
    for gir in girs.values():
        service_elements_client[gir.client].extend(gir.elements["req_client"])
        service_elements_server[gir.server].extend(gir.elements["req_server"])
    service_elements_client = {
        key: value for key, value in service_elements_client.items() if value
    }
    service_elements_server = {
        key: value for key, value in service_elements_server.items() if value
    }

    for service, elements in service_elements_client.items():
        gen_install(elements, service, service_pos[service], "client")
    for service, elements in service_elements_server.items():
        gen_install(elements, service, service_pos[service], "server")

    pids = dict()
    for service, host in service_pos.items():
        pid_str = execute_remote_container(
            service, host, ["pgrep", "-f", service.lower()]
        )
        pids[service] = pid_str.strip()

    # For each graphir, generate attach/detach scripts.
    for gir in girs.values():
        if len(gir.elements["req_client"]) > 0:
            gen_attach_detach(
                gir.client,
                service_pos[gir.client],
                pids[gir.client],
                sids[app][(gir.client, gir.server, "client")],
                gir.elements["req_client"],
                gir.elements["res_client"],
                "client",
            )
        if len(gir.elements["req_server"]) > 0:
            gen_attach_detach(
                gir.server,
                service_pos[gir.server],
                pids[gir.server],
                sids[app][(gir.client, gir.server, "server")],
                gir.elements["req_server"],
                gir.elements["res_server"],
                "server",
            )

    attach_all_path = os.path.join(local_gen_dir, "attach_all.sh")
    detach_all_path = os.path.join(local_gen_dir, "detach_all.sh")
    with open(attach_all_path, "w") as f:
        f.write("#!/bin/bash\n")
        f.write("\n".join(attach_cmd))
    with open(detach_all_path, "w") as f:
        f.write("#!/bin/bash\n")
        f.write("\n".join(detach_cmd[::-1]))
    os.system(f"chmod +x {attach_all_path}")
    os.system(f"chmod +x {detach_all_path}")
