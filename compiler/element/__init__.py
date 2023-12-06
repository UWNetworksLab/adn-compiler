import argparse
import os
import pathlib
import re
import sys
from pprint import pprint
from typing import Dict

from compiler import root_base_dir
from compiler.config import COMPILER_ROOT
from compiler.element.backend.finalizer import finalize
from compiler.element.backend.rustgen import RustContext, RustGenerator
from compiler.element.frontend import IRCompiler, Printer
from compiler.element.props.flow import FlowGraph


def gen_code(
    engine_name: str,
    output_name: str,
    output_dir: str,
    backend_name: str,
    placement: str,
    verbose: bool = False,
) -> str:
    assert backend_name == "mrpc"
    compiler = IRCompiler()
    printer = Printer()
    generator = RustGenerator(placement)
    ctx = RustContext()

    with open(
        os.path.join(root_base_dir, f"examples/match_action/{engine_name}.adn")
    ) as f:
        spec = f.read()
        ir = compiler.compile(spec)
        p = ir.accept(printer, None)
        if verbose:
            print(p)

        ir.accept(generator, ctx)

        finalize(output_name, ctx, output_dir, placement)


def compile_element_property(engine_name: str, verbose: bool = False) -> Dict:
    compiler = IRCompiler()
    printer = Printer()

    with open(
        os.path.join(root_base_dir, f"examples/match_action/{engine_name}.adn")
    ) as f:
        spec = f.read()
        ir = compiler.compile(spec)
        p = ir.accept(printer, None)
        if verbose:
            print(p)

        req = FlowGraph().analyze(ir.req, verbose)
        resp = FlowGraph().analyze(ir.resp, verbose)
        req.check()
        resp.check()
        stateful = len(ir.definition.internal) > 0
        return {
            "stateful": stateful,
            "request": {
                "read": req.read,
                "write": req.write,
                "drop": req.drop,
                "block": req.block,
                "copy": req.copy,
            },
            "response": {
                "read": resp.read,
                "write": resp.write,
                "drop": resp.drop,
                "block": resp.block,
                "copy": resp.copy,
            },
        }
