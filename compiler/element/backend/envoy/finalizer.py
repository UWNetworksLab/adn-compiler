import os
from typing import Dict

from compiler.config import COMPILER_ROOT
from compiler.element.backend.envoy.boilerplate import *
from compiler.element.backend.envoy.wasmgen import WasmContext
from compiler.element.backend.envoy.wasmtype import (
    WasmGlobalFunctions,
    WasmSelfFunctions,
)
from compiler.element.logger import ELEMENT_LOG as LOG


def retrieve(ctx: WasmContext, name: str) -> Dict:
    #!todo init
    return {
        "FilterName": name,
        "GlobalVariables": ctx.gen_global_var_def(),
        "GlobalFuncDef": "".join([f.definition for f in WasmGlobalFunctions.values()]),
        "ProtoFuncDef": "".join([f.definition for f in WasmSelfFunctions.values()]),
        "Init": "".join(ctx.init_code),
        "RequestHeaders": "".join(ctx.req_hdr_code),
        "RequestBody": "".join(ctx.req_body_code),
        "ResponseHeaders": "".join(ctx.resp_hdr_code),
        "ResponseBody": "".join(ctx.resp_body_code),
        "ExternalCallResponse": "".join(ctx.external_call_response_code),
    }


def codegen_from_template(output_dir, snippet, lib_name, proto_path):
    # This method generates the backend code from the template
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

    # Add the proto file to the generated code
    with open(f"{template_path}/build.rs", "r") as file:
        build_file = file.read()
    proto = os.path.basename(proto_path)
    build_file = build_file.replace("PROTO_FILENAME", proto)
    with open(f"{output_dir}/build.rs", "w") as file:
        file.write(build_file)

    os.system(f"cp {proto_path} {output_dir}")
    os.system(f"cp {template_path}/rust-toolchain.toml {output_dir}")

    os.system(f"rustfmt --edition 2018  {output_dir}/src/lib.rs")

    LOG.info(
        f"Backend code for {lib_name} generated. You can find the source code at {output_dir}"
    )


def finalize(
    name: str, ctx: WasmContext, output_dir: str, placement: str, proto_path: str
):
    snippet = retrieve(ctx, name)
    codegen_from_template(output_dir, snippet, name, proto_path)
