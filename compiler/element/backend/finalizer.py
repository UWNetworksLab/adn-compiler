import os
import sys
from pprint import pprint
from string import Formatter
from typing import Dict, List

from compiler.config import COMPILER_ROOT
from compiler.element.backend.boilerplate import *
from compiler.element.backend.protobuf import HelloProto
from compiler.element.backend.rustgen import RustContext
from compiler.element.backend.rusttype import RustGlobalFunctions
from compiler.element.logger import ELEMENT_LOG as LOG

# name: table_rpc_events
# type: Vec<struct_rpc_events>
# init: table_rpc_events = Vec::new()


def gen_global_function_includes() -> str:
    prefix = "use crate::engine::{"
    middle = ""
    for (k, v) in RustGlobalFunctions.items():
        name = v.name
        middle += f"{name},"
    suffix = "};"
    return prefix + middle + suffix


def gen_def() -> List[str]:
    ret = []
    for _, func in RustGlobalFunctions.items():
        ret.append(func.gen_def())
    ret = ret + HelloProto.gen_readonly_def() + HelloProto.gen_modify_def()
    return ret


def retrieve_info(ctx: RustContext):
    proto = "hello"
    proto_fc = "Hello"
    info = {
        "ProtoDefinition": proto,
        # todo! field name should be configurable
        # todo! multiple type should be supported
        "ProtoGetters": f"""
        """,
        "ProtoRpcRequestType": f"{proto}::{proto_fc}Request",
        "ProtoRpcResponseType": f"{proto}::{proto_fc}Response",
        "GlobalFunctionInclude": gen_global_function_includes(),
        "InternalStatesDefinition": "\n".join(gen_def()),
        "InternalStatesDeclaration": "\n".join(
            [f"use crate::engine::{i};" for i in ctx.gen_struct_names()]
        ),
        "InternalStatesOnBuild": "\n".join(ctx.gen_init_localvar())
        + "\n".join(ctx.init_code),
        "InternalStatesOnRestore": "\n".join(ctx.gen_init_localvar())
        + "\n".join(ctx.init_code),
        "InternalStatesOnDecompose": "",
        "InternalStatesInConstructor": "\n".join(
            [f"{i}," for i in ctx.gen_internal_names()]
        ),
        "InternalStatesInStructDefinition": "\n".join(
            [f"pub(crate) {i}," for i in ctx.gen_struct_declaration()]
        ),
        "RpcRequest": "".join(ctx.req_code),
        # !todo resp
        "RpcResponse": "".join(ctx.resp_code),
    }

    return info


api_lib_rs = "pub mod control_plane;"
api_control_plane_rs = """use serde::{Deserialize, Serialize};

type IResult<T> = Result<T, phoenix_api::Error>;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Request {
    NewConfig(),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ResponseKind {}

#[derive(Debug, Serialize, Deserialize)]
pub struct Response(pub IResult<ResponseKind>);
"""


def gen_template(
    placement,
    output_dir,
    ctx,
    template_name,
    template_name_toml,
    template_name_first_cap,
    template_name_all_cap,
):
    api_dir = os.path.join(output_dir, f"api/{template_name}")
    api_dir_src = os.path.join(api_dir, "src")
    plugin_dir = os.path.join(output_dir, f"plugin/{template_name}")
    plugin_dir_src = os.path.join(plugin_dir, "src")
    toml_dir = os.path.join(output_dir, f"toml/{template_name}")
    os.system(f"mkdir -p {api_dir_src}")
    os.system(f"mkdir -p {plugin_dir_src}")
    os.system(f"mkdir -p {toml_dir}")
    ctx["TemplateName"] = template_name
    ctx["TemplateNameFirstCap"] = template_name_first_cap
    ctx["TemplateNameAllCap"] = template_name_all_cap
    ctx["TemplateNameCap"] = template_name_first_cap
    config_path = os.path.join(plugin_dir_src, "config.rs")
    lib_path = os.path.join(plugin_dir_src, "lib.rs")
    module_path = os.path.join(plugin_dir_src, "module.rs")
    engine_path = os.path.join(plugin_dir_src, "engine.rs")
    proto_path = os.path.join(plugin_dir_src, "proto.rs")
    with open(config_path, "w") as f:
        f.write(config_rs.format(Include=include, **ctx))
    with open(lib_path, "w") as f:
        f.write(lib_rs.format(Include=include, **ctx))
    with open(module_path, "w") as f:
        if placement == "client":
            f.write(module_sender_rs.format(Include=include, **ctx))
        elif placement == "server":
            f.write(module_receiver_rs.format(Include=include, **ctx))
    with open(engine_path, "w") as f:
        # print([i[1] for i in Formatter().parse(engine_rs)  if i[1] is not None])
        if placement == "client":
            f.write(engine_sender_rs.format(Include=include, **ctx))
        elif placement == "server":
            f.write(engine_receiver_rs.format(Include=include, **ctx))

    with open(proto_path, "w") as f:
        f.write(proto_rs)
    with open(os.path.join(plugin_dir, "Cargo.toml"), "w") as f:
        f.write(policy_toml.format(TemplateName=template_name_toml))
    with open(os.path.join(api_dir_src, "control_plane.rs"), "w") as f:
        f.write(api_control_plane_rs)
    with open(os.path.join(api_dir_src, "lib.rs"), "w") as f:
        f.write(api_lib_rs)
    with open(os.path.join(api_dir, "Cargo.toml"), "w") as f:
        f.write(api_toml.format(TemplateName=template_name_toml))

    gen_attach_detach(
        toml_dir,
        {
            "Me": template_name_first_cap,
            "Prev": "Mrpc",
            "Next": "TcpRpcAdapter",
            "Group": '["MrpcEngine", "TcpRpcAdapterEngine"]',
        },
    )

    os.system(f"rustfmt --edition 2018  {config_path}")
    os.system(f"rustfmt --edition 2018  {lib_path}")
    os.system(f"rustfmt --edition 2018  {module_path}")
    os.system(f"rustfmt --edition 2018  {engine_path}")
    os.system(f"rustfmt --edition 2018  {proto_path}")

    LOG.info("Template {} generated".format(template_name))


def finalize(name: str, ctx: RustContext, output_dir: str, placement: str):
    name = name
    if name == "logging":
        template_name = "logging"
        template_name_toml = "logging"
        template_name_first_cap = "Logging"
        template_name_all_cap = "LOGGING"
    elif name == "acl":
        template_name = "acl"
        template_name_toml = "acl"
        template_name_first_cap = "Acl"
        template_name_all_cap = "ACL"
    elif name == "fault":
        template_name = "fault"
        template_name_toml = "fault"
        template_name_first_cap = "Fault"
        template_name_all_cap = "FAULT"
    else:
        name = name.split("_")
        template_name = "_".join(name)
        template_name_toml = "-".join(name)
        cap = [i[0].upper() + i[1:] for i in name]
        template_name_first_cap = "".join(cap)
        template_name_all_cap = "_".join(name).upper()

    info = retrieve_info(ctx)
    gen_template(
        placement,
        output_dir,
        info,
        template_name,
        template_name_toml,
        template_name_first_cap,
        template_name_all_cap,
    )


def gen_attach_detach(name: str, ctx):
    with open(f"{name}/attach.toml", "w") as f:
        f.write(attach_toml.format(**ctx))

    with open(f"{name}/detach.toml", "w") as f:
        f.write(detach_toml.format(**ctx))
