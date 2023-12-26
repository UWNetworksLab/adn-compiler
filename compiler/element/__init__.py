import argparse
import os
import pathlib
import re
import sys
from pprint import pprint
from typing import Dict, List

from compiler import root_base_dir
from compiler.config import COMPILER_ROOT
from compiler.element.backend.envoy.finalizer import finalize as WasmFinalize
from compiler.element.backend.envoy.wasmgen import WasmContext, WasmGenerator
from compiler.element.backend.mrpc.finalizer import finalize as RustFinalize
from compiler.element.backend.mrpc.rustgen import RustContext, RustGenerator
from compiler.element.frontend import IRCompiler, Printer
from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.optimize.consolidate import consolidate
from compiler.element.props.flow import FlowGraph, Property


def gen_code(
    engine_name: List[str],
    output_name: str,
    output_dir: str,
    backend_name: str,
    placement: str,
    verbose: bool = False,
) -> str:
    assert backend_name == "mrpc" or backend_name == "envoy"
    compiler = IRCompiler()

    if backend_name == "mrpc":
        generator = RustGenerator(placement)
        finalize = RustFinalize
        ctx = RustContext()
    elif backend_name == "envoy":
        generator = WasmGenerator(placement)
        finalize = WasmFinalize
        ctx = WasmContext()

    printer = Printer()

    irs = []
    for name in engine_name:
        LOG.info(f"Parsing {name}")
        with open(os.path.join(root_base_dir, f"examples/element/{name}.adn")) as f:
            spec = f.read()
            ir = compiler.compile(spec)
            p = ir.accept(printer, None)
            if verbose:
                print(p)
            irs.append(ir)

    if len(engine_name) > 1:
        LOG.info("Consolidating IRs")
        consolidated = consolidate(irs)
        p = consolidated.accept(printer, None)
        if verbose:
            LOG.info("Consolidated IR:")
            print(p)
    else:
        consolidated = irs[0]

    LOG.info(f"Generating {backend_name} code")
    consolidated.accept(generator, ctx)

    finalize(output_name, ctx, output_dir, placement)


def compile_element_property(engine_names: List[str], verbose: bool = False) -> Dict:
    compiler = IRCompiler()
    printer = Printer()

    ret = (Property(), Property())
    stateful = False
    for engine_name in engine_names:
        with open(
            os.path.join(root_base_dir, f"examples/element/{engine_name}.adn")
        ) as f:
            spec = f.read()
            ir = compiler.compile(spec)
            p = ir.accept(printer, None)
            if verbose:
                print(p)

            req = FlowGraph().analyze(ir.req, verbose)
            resp = FlowGraph().analyze(ir.resp, verbose)

            ret[0].block = ret[0].block or req.block
            ret[0].copy = ret[0].copy or req.copy
            ret[0].drop = ret[0].drop or req.drop
            ret[0].read = ret[0].read + req.read
            ret[0].write = ret[0].write + req.write
            ret[0].check()

            ret[1].block = ret[1].block or resp.block
            ret[1].copy = ret[1].copy or resp.copy
            ret[1].drop = ret[1].drop or resp.drop
            ret[1].read = ret[1].read + resp.read
            ret[1].write = ret[1].write + resp.write
            ret[1].check()

            stateful = stateful or len(ir.definition.internal) > 0
    ret[0].check()
    ret[1].check()
    record = len(engine_names) == 1 and (
        engine_names[0] == "logging" or engine_names[0] == "metrics"
    )
    return {
        "stateful": stateful,
        "request": {
            "record" if record else "read": ret[0].read,
            "write": ret[0].write,
            "drop": ret[0].drop,
            "block": ret[0].block,
            "copy": ret[0].copy,
        },
        "response": {
            "record" if record else "read": ret[1].read,
            "write": ret[1].write,
            "drop": ret[1].drop,
            "block": ret[1].block,
            "copy": ret[1].copy,
        },
    }
