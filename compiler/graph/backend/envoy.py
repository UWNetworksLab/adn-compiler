from __future__ import annotations

import os
from copy import deepcopy
from typing import Dict

import yaml

from compiler import graph_base_dir
from compiler.graph.backend import BACKEND_CONFIG_DIR
from compiler.graph.backend.boilerplate import attach_yml
from compiler.graph.backend.config import port_dict, service_pos_dict
from compiler.graph.backend.utils import *
from compiler.graph.ir import GraphIR
from compiler.graph.logger import GRAPH_BACKEND_LOG


def scriptgen_envoy(girs: Dict[str, GraphIR], app: str, app_manifest_file: str):
    global local_gen_dir
    local_gen_dir = os.path.join(graph_base_dir, "generated")
    os.makedirs(local_gen_dir, exist_ok=True)

    # Compile each element
    GRAPH_BACKEND_LOG.info("Compiling elements for Envoy. This might take a while...")
    compiled_elements = set()
    for gir in girs.values():
        for element in gir.elements["req_client"] + gir.elements["req_server"]:
            if element.lib_name not in compiled_elements:
                compiled_elements.add(element.lib_name)
                impl_dir = os.path.join(local_gen_dir, f"{element.lib_name}_envoy")
                # Compile
                execute_local(
                    [
                        "cargo",
                        "build",
                        "--target=wasm32-wasi",
                        "--manifest-path",
                        os.path.join(impl_dir, "Cargo.toml"),
                        "--release",
                    ]
                )
                # copy binary to /tmp
                execute_local(
                    [
                        "cp",
                        os.path.join(
                            impl_dir,
                            f"target/wasm32-wasi/release/{element.lib_name}.wasm",
                        ),
                        "/tmp",
                    ]
                )

    # Generate the istio manifest file for the application.
    execute_local(
        [
            "istioctl",
            "kube-inject",
            "-f",
            app_manifest_file,
            "-o",
            os.path.join(local_gen_dir, app + "_istio.yml"),
        ]
    )
    GRAPH_BACKEND_LOG.info("Generating the istio manifest file for the application...")
    with open(os.path.join(BACKEND_CONFIG_DIR, app_manifest_file), "r") as f:
        yml_list_plain = list(yaml.safe_load_all(f))
    service_to_hostname = extract_service_pos(yml_list_plain)

    with open(os.path.join(local_gen_dir, app + "_istio.yml"), "r") as f:
        yml_list_istio = list(yaml.safe_load_all(f))
    with open(os.path.join(BACKEND_CONFIG_DIR, "webdis_template.yml"), "r") as f:
        webdis_service, webdis_deploy = list(yaml.safe_load_all(f))

    # Extract the list of microservices
    services = list()
    for yml in yml_list_istio:
        if yml and "kind" in yml and yml["kind"] == "Service":
            services.append(yml["metadata"]["name"])

    # element_deploy_count counts the number of elements attached to each service.
    element_deploy_count = {sname: 0 for sname in services}

    # Attach elements to the sidecar pods using volumes
    for gir in girs.values():
        elist = [(e, gir.client) for e in gir.elements["req_client"]] + [
            (e, gir.server) for e in gir.elements["req_server"]
        ]
        for (element, sname) in elist:
            # If the element is stateful and requires strong consistency, deploy a webdis instance
            if (
                hasattr(element, "_prop")
                and element.prop[  # The element has no property when no-optimize flag is set
                    "state"
                ][
                    "stateful"
                ]
                == True
                and element.prop["state"]["consistency"] == "strong"
            ):
                # Add webdis config
                webdis_service_copy, webdis_deploy_copy = deepcopy(
                    webdis_service
                ), deepcopy(webdis_deploy)
                webdis_service_copy["metadata"][
                    "name"
                ] = f"webdis-service-{element.lib_name}"
                webdis_deploy_copy["metadata"][
                    "name"
                ] = f"webdis-test-{element.lib_name}"
                yml_list_istio.append(webdis_service_copy)
                yml_list_istio.append(webdis_deploy_copy)

            # Increment the element deploy count
            element_deploy_count[sname] += 1

            # Copy the wasm binary to the remote host
            copy_remote_host(
                service_to_hostname[sname], f"/tmp/{element.lib_name}.wasm", "/tmp/"
            )

            # Find the corresponding service in the manifest
            target_service_yml = find_target_yml(locals()["yml_list_istio"], sname)

            # Attach the element to the sidecar using volumes
            target_service_yml["spec"]["template"]["spec"]["containers"][1][
                "volumeMounts"
            ].append(
                {
                    "mountPath": f"/etc/{element.lib_name}.wasm",
                    "name": f"{element.lib_name}-wasm",
                }
            )
            target_service_yml["spec"]["template"]["spec"]["volumes"].append(
                {
                    "hostPath": {
                        "path": f"/tmp/{element.lib_name}.wasm",
                        "type": "File",
                    },
                    "name": f"{element.lib_name}-wasm",
                }
            )

    # if a service has no elment attached, turn off its sidecar
    for sname in services:
        if element_deploy_count[sname] == 0:
            target_yml = find_target_yml(locals()["yml_list_istio"], sname)
            target_yml.clear()
            target_yml.update(find_target_yml(locals()["yml_list_plain"], sname))

    # Adjust replica count
    replica = os.getenv("SERVICE_REPLICA")
    if replica is not None:
        for sname in services:
            target_yml = find_target_yml(locals()["yml_list_istio"], sname)
            target_yml["spec"]["replicas"] = int(replica)

    # Dump the final manifest file (somehow there is a None)
    yml_list_istio = [yml for yml in yml_list_istio if yml is not None]
    with open(os.path.join(local_gen_dir, "install.yml"), "w") as f:
        yaml.dump_all(yml_list_istio, f, default_flow_style=False)
    # TODO: we probably should just pipe the output of istioctl
    execute_local(["rm", os.path.join(local_gen_dir, app + "_istio.yml")])

    # Generate script to attach elements.
    for gir in girs.values():
        elist = [(e, gir.client, "client") for e in gir.elements["req_client"]] + [
            (e, gir.server, "server") for e in gir.elements["req_server"]
        ]
        for (e, sname, placement) in elist:
            contents = {
                "metadata_name": f"{e.lib_name}-{sname}-{placement}",
                "name": f"{e.lib_name}-{placement}",
                "ename": e.lib_name,
                "service": sname,
                "bound": "SIDECAR_OUTBOUND"
                if placement == "client"
                else "SIDECAR_INBOUND",
                "port": port_dict[app][gir.server],
                "vmid": f"vm.sentinel.{e.lib_name}-{placement}",
                "filename": f"/etc/{e.lib_name}.wasm",
            }
            attach_path = os.path.join(
                local_gen_dir, f"{e.lib_name}-{placement}-{sname}.yml"
            )
            with open(attach_path, "w") as f:
                f.write(attach_yml.format(**contents))

    GRAPH_BACKEND_LOG.info(
        "Element compilation and manifest generation complete. The generated files are in the 'generated' directory."
    )
    GRAPH_BACKEND_LOG.info(
        f"To deploy the application and attach the elements, run kubectl apply -f {local_gen_dir}"
    )
