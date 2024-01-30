from __future__ import annotations

import json
import os
from copy import deepcopy
from pprint import pprint
from typing import Dict, List, Tuple

import yaml

from compiler import graph_base_dir
from compiler.graph.backend import BACKEND_CONFIG_DIR
from compiler.graph.backend.boilerplate import attach_yml
from compiler.graph.backend.utils import *
from compiler.graph.ir import GraphIR
from compiler.graph.logger import GRAPH_BACKEND_LOG


def scriptgen_envoy(
    girs: Dict[str, GraphIR],
    app_name: str,
    app_manifest_dir: str,
    app_edges: List[Tuple[str, str]],
):
    global local_gen_dir
    local_gen_dir = os.path.join(graph_base_dir, "generated")
    os.makedirs(local_gen_dir, exist_ok=True)
    deploy_dir = os.path.join(local_gen_dir, f"{app_name}_deploy")
    os.makedirs(deploy_dir, exist_ok=True)

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

    for file_or_dir in os.listdir(app_manifest_dir):
        if app_name not in file_or_dir:
            execute_local(
                [
                    "cp",
                    "-r",
                    os.path.join(app_manifest_dir, file_or_dir),
                    os.path.join(deploy_dir, file_or_dir),
                ]
            )

    app_manifest_file = os.path.join(app_manifest_dir, f"{app_name}.yaml")
    # Generate the istio manifest file for the application.
    execute_local(
        [
            "istioctl",
            "kube-inject",
            "-f",
            app_manifest_file,
            "-o",
            os.path.join(local_gen_dir, app_name + "_istio.yml"),
        ]
    )
    GRAPH_BACKEND_LOG.info("Generating the istio manifest file for the application...")
    with open(app_manifest_file, "r") as f:
        yml_list_plain = list(yaml.safe_load_all(f))
    # for file in yml_list_plain:
    #     if file["kind"] == "Deployment":
    #         file["spec"]["template"]["metadata"].update(
    #             {"annotations": {"sidecar.istio.io/inject": "false"}}
    #         )
    service_to_hostname = extract_service_pos(yml_list_plain)
    service_to_port_number = extract_service_port(yml_list_plain)
    service_to_label = extract_service_label(yml_list_plain)

    with open(os.path.join(local_gen_dir, app_name + "_istio.yml"), "r") as f:
        yml_list_istio = list(yaml.safe_load_all(f))
    with open(os.path.join(BACKEND_CONFIG_DIR, "webdis_template.yml"), "r") as f:
        webdis_service, webdis_deploy = list(yaml.safe_load_all(f))

    # Extract the list of microservices
    services_all = list()
    for yml in yml_list_istio:
        if yml and "kind" in yml and yml["kind"] == "Service":
            services_all.append(yml["metadata"]["name"])
    services = list(
        filter(
            lambda s: "mongodb" not in s and "memcached" not in s and "jaeger" not in s,
            services_all,
        )
    )

    whitelist_port, blacklist_port = {}, {}
    for sname in services_all:
        whitelist_port[(sname, "C")] = set()
        whitelist_port[(sname, "S")] = set()
        blacklist_port[(sname, "C")] = []
        blacklist_port[(sname, "S")] = []

    # Attach elements to the sidecar pods using volumes
    for gir in girs.values():
        elist = [(e, gir.client) for e in gir.elements["req_client"]] + [
            (e, gir.server) for e in gir.elements["req_server"]
        ]
        for (element, sname) in elist:
            placement = "C" if sname == gir.client else "S"
            whitelist_port[(sname, placement)].add(service_to_port_number[gir.server])

            # If the element is stateful and requires strong consistency, deploy a webdis instance
            if (
                # hasattr(element, "_prop") and
                element.prop[  # The element has no property when no-optimize flag is set
                    "state"
                ][
                    "stateful"
                ]
                == True
                and element.prop["state"]["consistency"] in ["strong", "weak"]
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
                webdis_deploy_copy["spec"]["template"]["spec"].update(
                    {"nodeName": service_to_hostname[sname]}
                )
                yml_list_istio.append(webdis_service_copy)
                yml_list_istio.append(webdis_deploy_copy)

            # Copy the wasm binary to the remote host
            copy_remote_host(
                service_to_hostname[sname], f"/tmp/{element.lib_name}.wasm", "/tmp/"
            )

            # Find the corresponding service in the manifest
            target_service_yml = find_target_yml(yml_list_istio, sname)

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

    if os.getenv("ADN_NO_OPTIMIZE") != "1":
        # has optimization: exclude ports that has no element attached to
        for client, server in app_edges:
            port_number = service_to_port_number[server]
            if port_number not in whitelist_port[(client, "C")]:
                blacklist_port[(client, "C")].append(port_number)
            if port_number not in whitelist_port[(server, "S")]:
                blacklist_port[(server, "S")].append(port_number)
        # bypass frontend ingress sidecar
        if "frontend" in services:
            blacklist_port[("frontend", "S")].append(service_to_port_number["frontend"])
        for (sname, placement), portlist in blacklist_port.items():
            if portlist != []:
                annotation_name = (
                    "traffic.sidecar.istio.io/excludeOutboundPorts"
                    if placement == "C"
                    else "traffic.sidecar.istio.io/excludeInboundPorts"
                )
                target_service_yml = find_target_yml(yml_list_istio, sname)
                target_service_yml["spec"]["template"]["metadata"][
                    "annotations"
                ].update({annotation_name: ",".join(portlist)})
    else:
        # no optimization: keep everything unchanged so that no sidecar will be bypassed
        # TODO: bypass frontend ingress sidecar for ping-pong-app
        pass

    # if os.getenv("ADN_NO_OPTIMIZE") != "1":
    #     # has optimization: add whitelist annotations, ports not included in whitelist will be bypassed
    #     for (sname, placement), portset in whitelist_port.items():
    #         annotation_name = "traffic.sidecar.istio.io/includeOutboundPorts" if placement == "C" else "traffic.sidecar.istio.io/includeInboundPorts"
    #         target_service_yml = find_target_yml(yml_list_istio, sname)
    #         target_service_yml["spec"]["template"]["metadata"]["annotations"].update({
    #             # annotation_name: ','.join(list(portset))
    #             annotation_name: ''
    #         })
    # else:
    #     # no optimization: keep everything unchanged so that no sidecar will be bypassed
    #     pass

    # Adjust replica count
    replica = os.getenv("SERVICE_REPLICA")
    if replica is not None:
        for sname in services:
            target_yml = find_target_yml(yml_list_istio, sname)
            target_yml["spec"]["replicas"] = int(replica)

    # Dump the final manifest file (somehow there is a None)
    yml_list_istio = [yml for yml in yml_list_istio if yml is not None]
    with open(os.path.join(deploy_dir, "install.yml"), "w") as f:
        yaml.dump_all(yml_list_istio, f, default_flow_style=False)
    # TODO: we probably should just pipe the output of istioctl
    execute_local(["rm", os.path.join(local_gen_dir, app_name + "_istio.yml")])

    # Generate script to attach elements.
    attach_all_yml = ""
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
                "port": service_to_port_number[gir.server],
                "vmid": f"vm.sentinel.{e.lib_name}-{placement}",
                "filename": f"/etc/{e.lib_name}.wasm",
                "service_label": service_to_label[sname],
            }
            attach_all_yml += attach_yml.format(**contents)
    with open(os.path.join(deploy_dir, "attach_all_elements.yml"), "w") as f:
        f.write(attach_all_yml)

    GRAPH_BACKEND_LOG.info(
        "Element compilation and manifest generation complete. The generated files are in the 'generated' directory."
    )
    GRAPH_BACKEND_LOG.info(
        f"To deploy the application and attach the elements, run kubectl apply -Rf {deploy_dir}"
    )
