import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List

from rich.columns import Columns
from rich.console import Console

# set up $PYTHONPATH and environment variables
sys.path.append(str(Path(__file__).parent.parent.absolute()))
sys.path.append(str(Path(__file__).parent.absolute()))
os.environ["PHOENIX_DIR"] = os.path.join(os.getenv("HOME"), "phoenix")

from compiler import compiler_base_dir, graph_base_dir
from compiler.element import gen_code
from compiler.graph.backend import scriptgen
from compiler.graph.frontend import GCParser
from compiler.graph.ir import GraphIR
from compiler.graph.logger import IR_LOG, init_logging
from compiler.graph.pseudo_element_compiler import pseudo_compile

console = Console()
gir_summary = dict()


def compile_impl(
    engine_name: List[str],
    gen_dir: str,
    backend: str,
    placement: str,
    proto: str,
    method: str,
):
    gen_name = "".join(engine_name)
    if backend == "mrpc":
        gen_dir = os.path.join(gen_dir, f"{gen_name}_{placement}_{backend}")
    else:
        gen_dir = os.path.join(gen_dir, f"{gen_name}_{backend}")
    proto = os.path.join(compiler_base_dir, "../examples/proto", proto)
    os.system(f"mkdir -p {gen_dir}")
    gen_code(engine_name, gen_name, gen_dir, backend, placement, proto, method)


def generate_element_impl(graphirs: Dict[str, GraphIR], pseudo_impl: bool):
    compiled_name = set()
    gen_dir = os.path.join(graph_base_dir, "gen")
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
                        # os.path.join(compiler_base_dir, "element/backend", args.backend, "templates", element.proto),
                        element.proto,
                        element.method,
                    )
                compiled_name.add(identifier)


def print_gir_summary(graphirs: Dict[str, GraphIR]):
    IR_LOG.info("GraphIR summary:")
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
    # Step 1: Parsing
    # parse the spec file and generate graph ir
    # see examples/graph_spec for details about spec format
    parser = GCParser()
    graphirs, app_name = parser.parse(args.spec_path)

    if args.verbose:
        for gir in graphirs.values():
            if gir.name not in gir_summary:
                gir_summary[gir.name] = {"pre-optimized": [], "post-optimized": []}
            gir_summary[gir.name]["pre-optimized"] = gir.to_rich()

    # Step 2: Property Generation & Optimization
    if not args.no_optimize:
        for gir in graphirs.values():
            # each gir is an edge
            # if args.pseudo_property == True:
            #     the graph compiler uses hand-coded properties
            # else:
            #     the graph compiler calls the element compiler to generate properties
            gir.optimize(args.pseudo_property)

    if not args.dry_run:
        # args.dry_run == False => Generate and run backend-specific scripts & commands
        # Step 3: Generate element implementation
        # if args.pseudo_impl == True:
        #     the graph compiler uses hand-coded element impl in phoenix repo
        # else:
        #     the graph compiler calls the element compiler to generate impl
        generate_element_impl(graphirs, args.pseudo_impl)
        # Step 4: Generate deployment scripts
        scriptgen(graphirs, args.backend, app_name)

    if args.verbose:
        print_gir_summary(graphirs)


if __name__ == "__main__":
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
    args = parser.parse_args()
    init_logging(args.debug)

    os.environ["SERVICE_REPLICA"] = args.replica
    if args.dry_run:
        os.environ["DRY_RUN"] = "1"

    main(args)
