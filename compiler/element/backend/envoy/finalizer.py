import os
import sys
from pprint import pprint
from string import Formatter
from typing import Dict, List

from compiler.config import COMPILER_ROOT
from compiler.element.backend.envoy.boilerplate import *
from compiler.element.backend.envoy.wasmgen import WasmContext
from compiler.element.backend.envoy.wasmtype import WasmGlobalFunctions
from compiler.element.logger import ELEMENT_LOG as LOG


def retrieve(ctx: WasmContext, name: str) -> Dict:
    #!todo init
    return {
        "FilterName": name,
        "GlobalVariables": ctx.gen_global_var_def(),
        "GlobalFuncDef": "".join([f.definition for f in WasmGlobalFunctions.values()]),
        "Init": "".join(ctx.init_code),
        "RequestHeaders": "".join(ctx.req_hdr_code),
        "RequestBody": "".join(ctx.req_body_code),
        "ResponseHeaders": "".join(ctx.resp_hdr_code),
        "ResponseBody": "".join(ctx.resp_body_code),
    }


def gen_template(_placement, output_dir, snippet, lib_name):
    os.system(f"rm -rf {output_dir}")
    os.system(f"mkdir -p {output_dir}")
    os.system(f"mkdir -p {output_dir}/src")

    with open(f"{output_dir}/src/lib.rs", "w") as f:
        f.write(lib_rs.format(**snippet))
    with open(f"{output_dir}/Cargo.toml", "w") as f:
        f.write(cargo_toml.format(**snippet))
    with open(f"{output_dir}/build.sh", "w") as f:
        f.write(build_sh.format(**snippet))

    template_path = os.path.join(COMPILER_ROOT, "element/backend/envoy/templates")
    os.system(f"cp {template_path}/build.rs {output_dir}")
    os.system(f"cp {template_path}/ping.proto {output_dir}")
    os.system(f"cp {template_path}/pong.proto {output_dir}")
    os.system(f"cp {template_path}/rust-toolchain.toml {output_dir}")

    os.system(f"rustfmt --edition 2018  {output_dir}/src/lib.rs")

    LOG.info("Template {} generated".format(lib_name))


def finalize(name: str, ctx: WasmContext, output_dir: str, placement: str):
    snippet = retrieve(ctx, name)
    gen_template(placement, output_dir, snippet, name)
