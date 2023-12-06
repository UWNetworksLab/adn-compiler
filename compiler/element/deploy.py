import os
import subprocess
import sys
from typing import List

import tomli
import tomli_w
from config import COMPILER_ROOT

from compiler.element.logger import ELEMENT_LOG as LOG


def to_cargo_toml(name: str) -> str:
    return name.replace("_", "-")


def modify_load(engine: str) -> str:
    name = engine.split("-")
    firstcap = [i.capitalize() for i in name]
    firstcap = "".join(firstcap)
    rlib = engine.replace("-", "_")
    rlib = rlib.lower()
    return f"""
[[addons]]
name = "{firstcap}"
lib_path = "plugins/libphoenix_{rlib}.rlib"
config_string = \'\'\'
\'\'\'
"""


def move_template(phoenix_dir, template_name):
    original_api = phoenix_dir + "/experimental/mrpc/phoenix-api/policy"
    mrpc_plugin = phoenix_dir + "/experimental/mrpc/generated/plugin"
    mrpc_api = phoenix_dir + "/experimental/mrpc/generated/api"
    mrpc_toml = phoenix_dir + "/experimental/mrpc/generated/toml"

    prefix_api = str(COMPILER_ROOT) + "/generated/api/" + template_name
    prefix_plugin = str(COMPILER_ROOT) + "/generated/plugin/" + template_name
    prefix_toml = str(COMPILER_ROOT) + "/generated/toml/" + template_name

    os.system(f"mkdir -p {mrpc_api}")
    os.system(f"rm -rf {mrpc_api}/{template_name}")
    os.system(f"cp -r {original_api}/logging {mrpc_api}/{template_name}")
    os.system(f"rm {mrpc_api}/{template_name}/Cargo.toml")
    os.system(f"cp {prefix_api}/Cargo.toml {mrpc_api}/{template_name}/Cargo.toml")

    os.system(f"mkdir -p {mrpc_plugin}")
    os.system(f"rm -rf {mrpc_plugin}/{template_name}")
    os.system(f"mkdir -p {mrpc_plugin}/{template_name}/src")
    os.system(f"cp {prefix_plugin}/Cargo.toml {mrpc_plugin}/{template_name}/Cargo.toml")
    os.system(
        f"cp {prefix_plugin}/src/config.rs {mrpc_plugin}/{template_name}/src/config.rs"
    )
    os.system(f"cp {prefix_plugin}/src/lib.rs {mrpc_plugin}/{template_name}/src/lib.rs")
    os.system(
        f"cp {prefix_plugin}/src/module.rs {mrpc_plugin}/{template_name}/src/module.rs"
    )
    os.system(
        f"cp {prefix_plugin}/src/engine.rs {mrpc_plugin}/{template_name}/src/engine.rs"
    )
    os.system(
        f"cp {prefix_plugin}/src/proto.rs {mrpc_plugin}/{template_name}/src/proto.rs"
    )

    os.system(f"mkdir -p {mrpc_toml}")
    os.system(f"rm -rf {mrpc_toml}/{template_name}")
    os.system(f"cp -r {prefix_toml} {mrpc_toml}/{template_name}")

    LOG.info("Template {} moved to mrpc folder".format(template_name))


def install(engine_name: List[str], phoenix_dir: str):
    os.chdir(str(COMPILER_ROOT) + "/generated")
    LOG.info("Deploying to mRPC...")

    # engines = []
    # for engine in engine_name:
    #     name = f"gen_{engine}_{len(engines)}"
    #     engines.append(name)
    engines = engine_name
    engines = [to_cargo_toml(i) for i in engines]

    api = [f"generated/api/{i}" for i in engines]

    plugins = [f"generated/plugin/{i}" for i in engines]

    dep = [(f"phoenix-api-policy-{i}", {"path": f"generated/api/{i}"}) for i in engines]

    res = os.system(f"cp {phoenix_dir}/experimental/mrpc/Cargo.toml ./Cargo.toml")
    if res != 0:
        LOG.error("Error on copying Cargo.toml")
        exit(1)

    with open("Cargo.toml", "r") as f:
        cargo_toml = tomli.loads(f.read())

    members = cargo_toml["workspace"]["members"]
    members = members + api + plugins
    cargo_toml["workspace"]["members"] = members
    depends = cargo_toml["workspace"]["dependencies"]
    depends.update({i[0]: i[1] for i in dep})

    with open("Cargo2.toml", "w") as f:
        f.write(tomli_w.dumps(cargo_toml))
    res = os.system(f"cp ./Cargo2.toml {phoenix_dir}/experimental/mrpc/Cargo.toml")
    if res != 0:
        LOG.error("Error on copying updated Cargo.toml")
        exit(1)

    with open("load-mrpc-plugins-gen.toml", "w") as f:
        for e in engines:
            app = modify_load(e)
            f.write(app)

    res = os.system(
        f"cp ./load-mrpc-plugins-gen.toml {phoenix_dir}/experimental/mrpc/generated/load-mrpc-plugins-gen.toml"
    )
    if res != 0:
        LOG.error("Error on copying updated load-mrpc-plugins-gen.toml")
        exit(1)

    os.chdir(f"{phoenix_dir}/experimental/mrpc")
    for e in engines:
        LOG.info(f"Compiling mRPC Plugin: {e}")
        res = subprocess.run(
            ["cargo", "make", "build-mrpc-plugin-single", e], capture_output=True
        )
        if res.returncode != 0:
            LOG.error(f"Error on compiling mRPC Plugin: {res}")
            exit(1)
        # os.system(f"cargo make build-mrpc-plugin-single {e}")

    LOG.info("Installing mRPC Plugin...")
    res = subprocess.run(["cargo", "make", "deploy-plugins"], capture_output=True)
    if res.returncode != 0:
        LOG.error("Error on installing mRPC Plugin")
        exit(1)

    os.chdir(phoenix_dir)

    res = subprocess.run(
        [
            "cargo",
            "run",
            "--release",
            "--bin",
            "upgrade",
            "--",
            "--config",
            "./experimental/mrpc/generated/load-mrpc-plugins-gen.toml",
        ],
        capture_output=True,
    )
    if res.returncode != 0:
        LOG.error("Error on upgrading mRPC Plugin")

    LOG.info("Deployed to mRPC!")


# print("Cleaning up...")
# os.chdir("..")
# os.system("cp ./Cargo.toml ./phoenix/experimental/mrpc/Cargo.toml")
