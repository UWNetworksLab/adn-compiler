import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List

import yaml
from rich.columns import Columns
from rich.console import Console

# set up $PYTHONPATH and environment variables
sys.path.append(str(Path(__file__).parent.parent.absolute()))
sys.path.append(str(Path(__file__).parent.absolute()))
os.environ["PHOENIX_DIR"] = os.path.join(os.getenv("HOME"), "phoenix")

from compiler import *
from compiler.element import gen_code
from compiler.graph.backend import scriptgen
from compiler.graph.frontend import GraphParser
from compiler.graph.ir import GraphIR
from compiler.graph.logger import GRAPH_LOG, init_logging
from compiler.graph.pseudo_element_compiler import pseudo_compile

console = Console()
gir_summary = dict()


def parse_args():
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s",
        "--spec_path",
        help="Path to user specification file",
        type=str,
        required=True,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="If added, request graphs (i.e., element chains) on each edge will be printed on the terminal",
        action="store_true",
    )
    parser.add_argument(
        "--pseudo_property",
        help="If added, use hand-coded properties instead of auto-generated ones",
        action="store_true",
    )
    parser.add_argument(
        "--pseudo_impl",
        help="If added, use hand-coded impl instead of auto-generated ones",
        action="store_true",
    )
    parser.add_argument(
        "-b",
        "--backend",
        help="Backend name",
        type=str,
        required=True,
        choices=["mrpc", "envoy"],
    )
    parser.add_argument(
        "--mrpc_dir",
        help="Path to mrpc repo",
        type=str,
        default=os.path.join(os.getenv("HOME"), "phoenix/experimental/mrpc"),
    )
    parser.add_argument(
        "--dry_run",
        help="If added, the compilation terminates after optimization (i.e., no backend scriptgen)",
        action="store_true",
    )
    parser.add_argument(
        "--no_optimize",
        help="If added, no optimization will be applied to GraphIR",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--replica",
        type=str,
        help="#replica for each service",
        default="1",
    )
    parser.add_argument("--debug", help="Print debug info", action="store_true")

    return parser.parse_args()


def compile_impl(
    engine_name: List[str],
    gen_dir: str,
    backend: str,
    placement: str,
    proto: str,
    method: str,
):
    gen_name = "".join(engine_name)[:24]
    if backend == "mrpc":
        gen_dir = os.path.join(gen_dir, f"{gen_name}_{placement}_{backend}")
    else:
        gen_dir = os.path.join(gen_dir, f"{gen_name}_{backend}")
    proto_path = os.path.join(proto_base_dir, proto)
    os.system(f"mkdir -p {gen_dir}")
    gen_code(engine_name, gen_name, gen_dir, backend, placement, proto_path, method)


def generate_element_impl(graphirs: Dict[str, GraphIR], pseudo_impl: bool):
    compiled_name = set()
    gen_dir = os.path.join(graph_base_dir, "generated")
    os.system(f"rm {gen_dir} -rf")
    for gir in graphirs.values():  # For each edge in the application
        elist = [(e, "client") for e in gir.elements["req_client"]] + [
            (e, "server") for e in gir.elements["req_server"]
        ]
        for (element, placement) in elist:
            # For each element in the edge
            identifier = element.lib_name + placement
            if identifier not in compiled_name:
                if pseudo_impl:
                    pseudo_compile(element.lib_name, gen_dir, args.backend, placement)
                else:
                    compile_impl(
                        element.name,
                        gen_dir,
                        args.backend,
                        placement,
                        element.proto,
                        element.method,
                    )
                compiled_name.add(identifier)


def print_gir_summary(graphirs: Dict[str, GraphIR]):
    GRAPH_LOG.info("Graph IR summary:")
    for gir in graphirs.values():
        gir_summary[gir.name]["post-optimized"] = gir.to_rich()
        # gir_summary[gir.name]["property"] = {}
        # for element in gir.elements["req_client"] + gir.elements["req_server"]:
        #     gir_summary[gir.name]["property"][element.deploy_name] = element.prop
    for gname, summary in gir_summary.items():
        console.print()
        console.print(gname, style="underline bold italic")
        console.print(Columns(["\n :snail: :\n"] + summary["pre-optimized"]))
        console.print(Columns(["\n :rocket: :\n"] + summary["post-optimized"]))
        # if args.debug:
        #     console.print("Properties:")
        #     for ename, prop in summary["property"].items():
        #         console.print(f"{ename}: {prop['request']}")


def main(args):
    # Step 1: Parse the spec file and generate graph IRs (see examples/graph_spec for details about spec format)
    GRAPH_LOG.info(f"Parsing graph spec file {args.spec_path}...")
    parser = GraphParser()
    graphirs, app_name, app_manifest_file = parser.parse(args.spec_path)

    if args.verbose:
        for gir in graphirs.values():
            if gir.name not in gir_summary:
                gir_summary[gir.name] = {"pre-optimized": [], "post-optimized": []}
            gir_summary[gir.name]["pre-optimized"] = gir.to_rich()

    # Step 2: Generate element properties via element compiler and optimize the graph IR.
    GRAPH_LOG.info("Generating element properties and optimizing the graph IR...")
    for gir in graphirs.values():
        # Each gir represests an edge in the application (a pair of communicating services)
        # pseudo_property is set to True when we want to use hand-coded properties instead of auto-generated ones
        for element in gir.elements["req_client"] + gir.elements["req_server"]:
            element.set_property_source(args.pseudo_property)
        if not args.no_optimize:
            gir.optimize()

    # Step 3: Generate backend code for the elements and deployment scripts.
    if not args.dry_run:
        GRAPH_LOG.info(
            "Generating backend code for the elements and deployment scripts..."
        )
        # Step 3.1: Generate backend code for the elements
        # pseudo_impl is set to True when we want to use hand-coded impl instead of auto-generated ones
        generate_element_impl(graphirs, args.pseudo_impl)
        # Step 3.2: Generate deployment scripts
        scriptgen(graphirs, args.backend, app_name, app_manifest_file)

    # Dump graphir summary (in yaml)
    gen_dir = os.path.join(graph_base_dir, "generated")
    graphir_summary = {"graphir": []}
    for gir in graphirs.values():
        graphir_summary["graphir"].append(str(gir))
    # We should safe them as yaml file, but it messes up the kubectl apply command.
    with open(os.path.join(gen_dir, "gir_summary"), "w") as f:
        f.write(yaml.dump(graphir_summary, default_flow_style=False, indent=4))

    # graphir rich display in terminal
    if args.verbose:
        print_gir_summary(graphirs)


if __name__ == "__main__":
    args = parse_args()
    init_logging(args.debug)

    os.environ["SERVICE_REPLICA"] = args.replica
    if args.dry_run:
        os.environ["DRY_RUN"] = "1"
    if args.no_optimize:
        os.environ["ADN_NO_OPTIMIZE"] = "1"

    main(args)
