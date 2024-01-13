from __future__ import annotations

import copy
from enum import Enum
from typing import List, Optional

from compiler.element.backend.envoy import *
from compiler.element.logger import ELEMENT_LOG as LOG


class WasmType:
    def __init__(self, name: str):
        self.name = name

    def __str__(self) -> str:
        return self.name

    def is_basic(self) -> bool:
        return False

    def is_con(self) -> bool:
        return False

    def gen_init(self) -> str:
        raise NotImplementedError

    def gen_get(self, args, ename):
        raise NotImplementedError

    def gen_set(self, args, ename, current_procedure):
        raise NotImplementedError

    def gen_delete(self, args):
        raise NotImplementedError

    def gen_size(self):
        raise NotImplementedError


class WasmBasicType(WasmType):
    def __init__(self, name: str, init_val: Optional[str] = None):
        super().__init__(name)
        self.init_val = init_val

    def is_basic(self) -> bool:
        return True

    def gen_init(self) -> str:
        match self.name:
            case "String":
                return "String::new()"
            case "f32":
                return "0.0"
            case "f64":
                return "0.0"
            case _:
                return "0"


class WasmVecType(WasmType):
    def __init__(self, elem_type: WasmType) -> None:
        super().__init__(f"Vec<{elem_type.name}>")
        self.con = "Vec"
        self.elem_type = elem_type

    def gen_init(self) -> str:
        return f"{self.con}::new()"

    def gen_get(self, args: List[str], ename: str) -> str:
        assert len(args) == 1
        return f".get({args[0]})"

    def gen_set(self, args: List[str], ename: str, current_procedure: str) -> str:
        assert len(args) == 2
        if args[0].endswith(".len()"):
            return f".push({args[1]})"
        else:
            return f".set({args[0]}, {args[1]})"

    def gen_delete(self, args):
        assert len(args) == 1
        return f".remove({args[0]})"

    def gen_size(self) -> str:
        return f".len()"


class WasmSyncVecType(WasmType):
    # TODO: Implement sync vector type
    def __init__(self, elem: WasmType) -> None:
        self.con = "Vec"
        self.elem = elem


class WasmMapType(WasmType):
    def __init__(self, key: WasmType, value: WasmType) -> None:
        # e.g., HashMap<String, String>
        super().__init__(f"HashMap<{key.name}, {value.name}>")
        self.con = "HashMap"
        self.key = key
        self.value = value

    def gen_init(self) -> str:
        return f"{self.con}::new()"

    def gen_get(self, args: List[str], ename: str) -> str:
        assert len(args) == 1
        return f".get(&{args[0]})"

    def gen_set(self, args: List[str], ename: str, current_procedure: str) -> str:
        assert len(args) == 2
        return f".insert({args[0]}, {args[1]})"


class WasmSyncMapType(WasmType):
    # Sync State needs to call external storage to get the latest value.
    def __init__(self, key: WasmType, value: WasmType) -> None:
        self.key = key
        self.value = value

    def gen_get(self, args: List[str], ename: str) -> str:
        assert len(args) == 1
        return f"""self.dispatch_http_call(
                        "webdis-service-{ename}", // or your service name
                        vec![
                            (":method", "GET"),
                            (":path", &format!("/GET/{{}}", {args[0]})),
                            (":authority", "webdis-service-{ename}"), // Replace with the appropriate authority if needed
                        ],
                        None,
                        vec![],
                        Duration::from_secs(5),
                    )
                    .unwrap();
                    return Action::Pause"""

    def gen_set(self, args: List[str], ename: str, current_procedure: str) -> str:
        assert len(args) == 2
        return_stmt = (
            ""
            if current_procedure in [FUNC_INIT, FUNC_EXTERNAL_RESPONSE]
            else "return Action::Pause;"
        )
        return (
            f"""self.dispatch_http_call(
                        "webdis-service-{ename}", // or your service name
                        vec![
                            (":method", "GET"),
                            (":path", &format!("/SET/{{}}/{{}}", {args[0]}, {args[1]})),
                            // (":path", "/SET/redis/hello"),
                            (":authority", "webdis-service-{ename}"), // Replace with the appropriate authority if needed
                        ],
                        None,
                        vec![],
                        Duration::from_secs(5),
                    )
                    .unwrap();
                    """
            + return_stmt
        )


class WasmRpcType(WasmType):
    def __init__(self, name: str, fields: List[(str, WasmType)]):
        super().__init__(name)
        self.fields = fields

    def gen_get(self, args: List[str], ename: str) -> str:
        assert len(args) == 1
        return "." + args[0].strip('"')


class WasmFunctionType(WasmType):
    def __init__(
        self,
        name: str,
        args: List[WasmType],
        ret: WasmType,
        use_self: bool,
        definition: str,
    ):
        super().__init__(name)
        self.args = args
        self.ret = ret
        self.definition = definition
        self.use_self = use_self

    def __str__(self) -> str:
        return f"{self.name}({', '.join([str(i) for i in self.args])}) -> {self.ret}"

    def gen_def(self) -> str:
        return self.definition

    def gen_call(self, args: Optional[List[str]] = []) -> str:
        if self.use_self:
            args = ["self"] + args
        return f"{self.name}({', '.join(args)})"


class WasmRwLock(WasmType):
    def __init__(self, inner: WasmType):
        self.name = "RwLock"
        self.inner = inner

    def __str__(self) -> str:
        return "RwLock<" + str(self.inner) + ">"

    def gen_init(self) -> str:
        return f"RwLock::new({self.inner.gen_init()})"

    def gen_get(self) -> str:
        return f""


class WasmMutex(WasmType):
    def __init__(self, inner: WasmType):
        self.name = "Mutex"
        self.inner = inner

    def __str__(self) -> str:
        return "Mutex<" + str(self.inner) + ">"

    def gen_init(self) -> str:
        return f"Mutex::new({self.inner.gen_init()})"

    def gen_get(self) -> str:
        return f""


class WasmVariable:
    def __init__(
        self,
        name: str,
        wasm_type: WasmType,
        temp: bool,
        rpc: bool,
        atomic: bool,
        inner: bool,
        consistency: str = None,
        combiner: str = "LWW",
        persistence: bool = False,
        init: Optional[str] = None,
    ) -> None:
        self.name = name
        self.type = wasm_type
        self.temp = temp
        self.rpc = rpc
        self.atomic = atomic
        self.inner = inner
        # if consistency is set to True, it means that this variable needs to be synchronized across all element instances.
        # Thus, we need to access a remote storage on every call.
        self.consistency = consistency
        # Combiner function for this variable. If not set, the default combiner function (last writer wins) is used.
        self.combiner = combiner
        # if persistence is set to True, it means that this variable needs to be persisted.
        self.persistence = persistence

        if init is None:
            self.init = ""
        else:
            self.init = init

    def __str__(self) -> str:
        return f"{'mut ' if self.mut else ''}{self.name}: {self.type}"

    def is_unwrapped(self) -> bool:
        return not self.temp and not self.atomic

    def gen_init_localvar(self) -> str:
        return f"let mut {self.name} = {self.init};"

    def gen_init_self(self) -> str:
        if self.is_unwrapped():
            return f"{self.name} = {self.init};"
        else:
            return f"""
                let mut {self.name}_inner = {self.name}.lock().unwrap();\n
                {self.name}_inner = {self.init};\n
        """

    def gen_init_global(self) -> str:
        assert self.atomic


WasmGlobalFunctions = {
    "encrypt": WasmFunctionType(
        "gen_encrypt",
        [WasmType("&str"), WasmType("&str")],
        WasmBasicType("String"),
        False,
        """pub fn gen_encrypt(a: &str, b: &str) -> String {
            let mut ret = String::new();
            for (x, y) in a.bytes().zip(b.bytes()) {
                ret.push((x ^ y) as char);
            }
            ret
        }""",
    ),
    "decrypt": WasmFunctionType(
        "gen_decrypt",
        [WasmType("&str"), WasmType("&str")],
        WasmBasicType("String"),
        False,
        """pub fn gen_decrypt(a: &str, b: &str) -> String {
            let mut ret = String::new();
            for (x, y) in a.bytes().zip(b.bytes()) {
                ret.push((x ^ y) as char);
            }
            ret
    }""",
    ),
    "update_window": WasmFunctionType(
        "gen_update_window",
        [WasmBasicType("u64"), WasmBasicType("u64")],
        WasmBasicType("u64"),
        False,
        "pub fn gen_update_window(a: u64, b: u64) -> u64 { a.max(b) }",
    ),
    "current_time": WasmFunctionType(
        "gen_current_timestamp",
        [],
        WasmBasicType("f64"),
        True,
        """pub fn gen_current_timestamp(ctx: & impl Context) -> f64 {
            DateTime::<Utc>::from(ctx.get_current_time()).timestamp() as f64
        }""",
    ),
    "time_diff": WasmFunctionType(
        "gen_time_difference",
        [WasmBasicType("f64"), WasmBasicType("f64")],
        WasmBasicType("f64"),
        False,
        "pub fn gen_time_difference(a: f64, b: f64) -> f64 { a - b }",
    ),
    "random_f64": WasmFunctionType(
        "gen_random_f64",
        [WasmBasicType("f64"), WasmBasicType("f64")],
        WasmBasicType("f64"),
        False,
        "pub fn gen_random_f64(l: f64, r: f64) -> f64 { rand::random::<f64>() }",
    ),
    "random_u32": WasmFunctionType(
        "gen_random_u32",
        [WasmBasicType("u32"), WasmBasicType("u32")],
        WasmBasicType("u32"),
        False,
        "pub fn gen_random_u32(l: u32, r: u32) -> u32 { rand::random::<u32>() }",
    ),
    "min_u64": WasmFunctionType(
        "gen_min_u64",
        [WasmBasicType("u64"), WasmBasicType("u64")],
        WasmBasicType("u64"),
        False,
        "pub fn gen_min_u64(a: u64, b: u64) -> u64 { a.min(b) }",
    ),
    "min_f64": WasmFunctionType(
        "gen_min_f64",
        [WasmBasicType("f64"), WasmBasicType("f64")],
        WasmBasicType("f64"),
        False,
        "pub fn gen_min_f64(a: f64, b: f64) -> f64 { a.min(b) }",
    ),
    "max_f64": WasmFunctionType(
        "gen_max_f64",
        [WasmBasicType("f64"), WasmBasicType("f64")],
        WasmBasicType("f64"),
        False,
        "pub fn gen_max_f64(a: f64, b: f64) -> f64 { a.max(b) }",
    ),
    "encrypt": WasmFunctionType(
        "gen_encrypt",
        [WasmType("&str"), WasmType("&str")],
        WasmBasicType("String"),
        False,
        """pub fn gen_encrypt(a: &str, b: &str) -> String {
            let mut ret = String::new();
            for (x, y) in a.bytes().zip(b.bytes()) {
                ret.push((x ^ y) as char);
            }
            ret
        }""",
    ),
}


WasmSelfFunctions = {
    "request_modify": WasmFunctionType(
        "PingEcho_request_modify_body",
        [WasmBasicType("&str")],
        WasmBasicType("()"),
        False,
        """
            pub fn PingEcho_request_modify_body(&mut self, req: &mut ping::PingEchoRequest, value: String) -> () {
                let mut new_body = Vec::new();
                req.body = value.to_string();
                req.encode(&mut new_body).expect("Failed to encode");
                let new_body_length = new_body.len() as u32;
                let mut grpc_header = Vec::new();
                grpc_header.push(0); // Compression flag
                grpc_header.extend_from_slice(&new_body_length.to_be_bytes());
                grpc_header.append(&mut new_body);
                self.set_http_request_body(0, grpc_header.len(), &grpc_header);
            }
        """,
    ),
    "response_modify": WasmFunctionType(
        "PingEcho_response_modify_body",
        [WasmBasicType("&str")],
        WasmBasicType("()"),
        False,
        """
            pub fn PingEcho_response_modify_body(&mut self, req: &mut ping::PingEchoResponse, value: String) -> () {
                let mut new_body = Vec::new();
                req.body = value.to_string();
                req.encode(&mut new_body).expect("Failed to encode");
                let new_body_length = new_body.len() as u32;
                let mut grpc_header = Vec::new();
                grpc_header.push(0); // Compression flag
                grpc_header.extend_from_slice(&new_body_length.to_be_bytes());
                grpc_header.append(&mut new_body);
                self.set_http_request_body(0, grpc_header.len(), &grpc_header);
            }
        """,
    ),
}
