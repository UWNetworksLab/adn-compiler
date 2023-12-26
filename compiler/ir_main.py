import argparse
import os
import pathlib
import re
import sys
from pprint import pprint
from typing import Dict

from compiler.config import COMPILER_ROOT
from compiler.element import compile_element_property, gen_code
from compiler.element.backend.mrpc.finalizer import finalize
from compiler.element.backend.mrpc.rustgen import RustContext, RustGenerator
from compiler.element.deploy import install, move_template
from compiler.element.frontend import IRCompiler, Printer
from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.logger import init_logging
from compiler.element.props.flow import FlowGraph

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-e", "--engine", type=str, help="(Engine_name',') *", required=True
    )
    parser.add_argument(
        "-v", "--verbose", help="Print Debug info", required=False, default=False
    )
    parser.add_argument(
        "-d",
        "--deploy",
        help="Deploy to the target directory",
        required=False,
        default=False,
    )
    parser.add_argument(
        "-p",
        "--placement",
        help="Placement of the generated code",
        required=True,
        default="c",
    )
    parser.add_argument("-b", "--backend", help="Backend Code Target", required=True)
    init_logging(True)
    # parser.add_argument("--verbose", help="Print Debug info", action="store_true")
    # parser.add_argument(
    #     "--mrpc_dir",
    #     type=str,
    #     default=f"../../phoenix/experimental/mrpc",
    # )
    # parser.add_argument(
    #     "-o", "--output", type=str, help="Output type: ast, ir, mrpc", default="mrpc"
    # )
    args = parser.parse_args()
    engines = args.engine.split(",")
    backend = args.backend
    LOG.info(f"engines: {engines}")
    verbose = args.verbose
    deploy = args.deploy
    placement = args.placement
    if placement == "c":
        placement = "client"
    elif placement == "s":
        placement = "server"
    else:
        raise Exception("invalid Placement, c/s expected")

    ret = compile_element_property(engines, verbose)
    LOG.info(f"prop: {ret}")
    output_name = "gen" + "".join(engines) + placement
    ret = gen_code(
        engines,
        output_name,
        str(COMPILER_ROOT) + "/generated/" + str(backend),
        backend,
        placement,
        verbose,
    )
    if deploy:
        move_template("/home/banruo/phoenix", output_name)
        install([output_name], "/home/banruo/phoenix")
