from __future__ import annotations

import copy
from enum import Enum
from typing import List, Optional

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

    def gen_get(self, args):
        raise NotImplementedError

    def gen_set(self, args):
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
    def __init__(self, con: str, elem: WasmType) -> None:
        super().__init__(f"{con}<{elem.name}>")
        self.con = con
        self.elem = elem

    def gen_init(self) -> str:
        return f"{self.con}::new()"

    def gen_get(self, args: List[str]) -> str:
        assert len(args) == 1
        return f".get({args[0]})"

    def gen_set(self, args: List[str]) -> str:
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


class WasmMapType(WasmType):
    def __init__(self, con: str, key: WasmType, value: WasmType) -> None:
        super().__init__(f"{con}<{key.name}, {value.name}>")
        self.con = con
        self.key = key
        self.value = value

    def gen_init(self) -> str:
        return f"{self.con}::new()"

    def gen_get(self, args: List[str]) -> str:
        assert len(args) == 1
        return f".get(&{args[0]})"

    def gen_set(self, args: List[str]) -> str:
        assert len(args) == 2
        return f".insert({args[0]}, {args[1]})"


class WasmRpcType(WasmType):
    def __init__(self, name: str, fields: List[(str, WasmType)]):
        super().__init__(name)
        self.fields = fields

    def gen_get(self, args: List[str]) -> str:
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
        init: Optional[str] = None,
    ) -> None:
        self.name = name
        self.type = wasm_type
        self.temp = temp
        self.rpc = rpc
        self.atomic = atomic

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
        "Gen_encrypt",
        [WasmType("&str"), WasmType("&str")],
        WasmBasicType("String"),
        False,
        """pub fn Gen_encrypt(a: &str, b: &str) -> String {
            let mut ret = String::new();
            for (x, y) in a.bytes().zip(b.bytes()) {
                ret.push((x ^ y) as char);
            }
            ret
        }""",
    ),
    "decrypt": WasmFunctionType(
        "Gen_decrypt",
        [WasmType("&str"), WasmType("&str")],
        WasmBasicType("String"),
        False,
        """pub fn Gen_decrypt(a: &str, b: &str) -> String {
            let mut ret = String::new();
            for (x, y) in a.bytes().zip(b.bytes()) {
                ret.push((x ^ y) as char);
            }
            ret
    }""",
    ),
    "update_window": WasmFunctionType(
        "Gen_update_window",
        [WasmBasicType("u64"), WasmBasicType("u64")],
        WasmBasicType("u64"),
        False,
        "pub fn Gen_update_window(a: u64, b: u64) -> u64 { a.max(b) }",
    ),
    "current_time": WasmFunctionType(
        "Gen_current_timestamp",
        [],
        WasmBasicType("f32"),
        True,
        """pub fn Gen_current_timestamp(ctx: & impl Context) -> f32 {
            DateTime::<Utc>::from(ctx.get_current_time()).timestamp() as f32
        }""",
    ),
    "time_diff": WasmFunctionType(
        "Gen_time_difference",
        [WasmBasicType("f32"), WasmBasicType("f32")],
        WasmBasicType("f32"),
        False,
        "pub fn Gen_time_difference(a: f32, b: f32) -> f32 { a - b }",
    ),
    "random_f32": WasmFunctionType(
        "Gen_random_f32",
        [WasmBasicType("f32"), WasmBasicType("f32")],
        WasmBasicType("f32"),
        False,
        "pub fn Gen_random_f32(l: f32, r: f32) -> f32 { rand::random::<f32>() }",
    ),
    "random_u32": WasmFunctionType(
        "Gen_random_u32",
        [WasmBasicType("u32"), WasmBasicType("u32")],
        WasmBasicType("u32"),
        False,
        "pub fn Gen_random_u32(l: u32, r: u32) -> u32 { rand::random::<u32>() }",
    ),
    "min_u64": WasmFunctionType(
        "Gen_min_u64",
        [WasmBasicType("u64"), WasmBasicType("u64")],
        WasmBasicType("u64"),
        False,
        "pub fn Gen_min_u64(a: u64, b: u64) -> u64 { a.min(b) }",
    ),
    "min_f64": WasmFunctionType(
        "Gen_min_f64",
        [WasmBasicType("f64"), WasmBasicType("f64")],
        WasmBasicType("f64"),
        False,
        "pub fn Gen_min_f64(a: f64, b: f64) -> f64 { a.min(b) }",
    ),
    "encrypt": WasmFunctionType(
        "Gen_encrypt",
        [WasmType("&str"), WasmType("&str")],
        WasmBasicType("String"),
        False,
        """pub fn Gen_encrypt(a: &str, b: &str) -> String {
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
