from __future__ import annotations

import copy
from enum import Enum
from typing import List, Optional


class RustType:
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


class RustBasicType(RustType):
    def __init__(self, name: str, init_val: Optional[str] = None):
        super().__init__(name)
        self.init_val = init_val

    def is_basic(self) -> bool:
        return True

    def gen_init(self) -> str:
        if self.init_val is None:
            return f"{self.name}::default()"
        else:
            return self.init_val


class RustVecType(RustType):
    def __init__(self, con: str, elem: RustType) -> None:
        super().__init__(f"{con}<{elem.name}>")
        self.con = con
        self.elem = elem

    def gen_init(self) -> str:
        return f"{self.con}::new()"

    def gen_get(self, args: List[str]) -> str:
        assert len(args) == 1
        return f".get({args[0]}).unwrap()"

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


class RustMapType(RustType):
    def __init__(self, con: str, key: RustType, value: RustType) -> None:
        super().__init__(f"{con}<{key.name}, {value.name}>")
        self.con = con
        self.key = key
        self.value = value

    def gen_init(self) -> str:
        return f"{self.con}::new()"

    def gen_get(self, args: List[str]) -> str:
        assert len(args) == 1
        return f".get(&{args[0]}).unwrap()"

    def gen_set(self, args: List[str]) -> str:
        assert len(args) == 2
        return f".insert({args[0]}, {args[1]})"


class RustRpcType(RustType):
    def __init__(self, name: str, fields: List[(str, RustType)]):
        super().__init__(name)
        self.fields = fields

    def gen_get(self, args: List[str]) -> str:
        raise Exception("Rpc get should use proto getter")


class RustFunctionType(RustType):
    def __init__(self, name: str, args: List[RustType], ret: RustType, definition: str):
        super().__init__(name)
        self.args = args
        self.ret = ret
        self.definition = definition

    def __str__(self) -> str:
        return f"{self.name}({', '.join([str(i) for i in self.args])}) -> {self.ret}"

    def gen_def(self) -> str:
        return self.definition

    def gen_call(self, args: Optional[List[str]] = []) -> str:
        return f"{self.name}({', '.join(args)})"


class RustVariable:
    def __init__(
        self,
        name: str,
        rust_type: RustType,
        temp: bool,
        rpc: bool,
        mut: bool = True,
        init: Optional[str] = None,
    ) -> None:
        self.name = name
        self.type = rust_type
        self.temp = temp
        self.rpc = rpc
        self.mut = mut

        if init is None:
            self.init = ""
        else:
            self.init = init

    def __str__(self) -> str:
        return f"{'mut ' if self.mut else ''}{self.name}: {self.type}"

    def gen_init_localvar(self) -> str:
        return f"let mut {self.name} = {self.init};"

    def gen_init_self(self) -> str:
        return f"self.{self.name} = {self.init};"

    def gen_struct_declaration(self) -> str:
        return f"{self.name}: {self.type.name}"


RustGlobalFunctions = {
    "update_window": RustFunctionType(
        "Gen_update_window",
        [RustBasicType("u64"), RustBasicType("u64")],
        RustBasicType("u64"),
        "pub fn Gen_update_window(a: u64, b: u64) -> u64 { a.max(b) }",
    ),
    "current_time": RustFunctionType(
        "Gen_current_timestamp",
        [],
        RustBasicType("Instant"),
        "pub fn Gen_current_timestamp() -> Instant { Instant::now() }",
    ),
    "time_diff": RustFunctionType(
        "Gen_time_difference",
        [RustBasicType("Instant"), RustBasicType("Instant")],
        RustBasicType("f32"),
        "pub fn Gen_time_difference(a: Instant, b: Instant) -> f32 {(a - b).as_secs_f64() as f32}",
    ),
    "random_f32": RustFunctionType(
        "Gen_random_f32",
        [RustBasicType("f32"), RustBasicType("f32")],
        RustBasicType("f32"),
        "pub fn Gen_random_f32(l: f32, r: f32) -> f32 { rand::random::<f32>() }",
    ),
    "min_u64": RustFunctionType(
        "Gen_min_u64",
        [RustBasicType("u64"), RustBasicType("u64")],
        RustBasicType("u64"),
        "pub fn Gen_min_u64(a: u64, b: u64) -> u64 { a.min(b) }",
    ),
    "min_f64": RustFunctionType(
        "Gen_min_f64",
        [RustBasicType("f64"), RustBasicType("f64")],
        RustBasicType("f64"),
        "pub fn Gen_min_f64(a: f64, b: f64) -> f64 { a.min(b) }",
    ),
}


# tx_struct = RustStructType(
#     "RpcMessageTx",
#     [
#         ("meta_buf_ptr", RustStructType("MetaBufferPtr", [])),
#         ("addr_backend", RustBasicType("usize")),
#     ],
# )

# rx_struct = RustStructType("RpcMessageRx", [("meta_buf_ptr", RustStructType("MetaBufferPtr", [])), ("addr_backend", RustBasicType("usize"))])
