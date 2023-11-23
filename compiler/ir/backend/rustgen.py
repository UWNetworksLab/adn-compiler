from typing import Dict, List, Optional

from compiler.ir.backend.rusttype import *
from compiler.ir.node import *
from compiler.ir.visitor import Visitor

FUNC_REQ = "req"
FUNC_RESP = "resp"
FUNC_INIT = "init"


def map_basic_type(name: str) -> RustType:
    if name == "float":
        return RustBasicType("f64")
    elif name == "int":
        return RustBasicType("i32")
    elif name == "string":
        return RustBasicType("String")
    else:
        print(f"unknown type: {name}")
        return RustType(name)


def proto_gen_get(rpc: str, args: List[str]) -> str:
    assert len(args) == 1
    arg = args[0].strip('"')
    if rpc == "rpc_req":
        return f"hello_HelloRequest_{arg}_readonly(&{rpc})"
    elif rpc == "rpc_resp":
        return f"hello_HelloResponse_{arg}_readonly(&{rpc})"


def proto_gen_set(rpc: str, args: List[str]) -> str:
    assert len(args) == 2
    arg1 = args[0].strip('"')
    if rpc == "rpc_req":
        return f"hello_HelloRequest_{arg1}_modify({rpc}_mut, {args[1]}.as_bytes())"
    elif rpc == "rpc_resp":
        return f"hello_HelloResponse_{arg1}_modify({rpc}_mut, {args[1]}.as_bytes())"


class RustContext:
    def __init__(self) -> None:
        self.internal_states: List[RustVariable] = []
        self.name2var: Dict[str, RustVariable] = {}
        self.current_func: str = "unknown"
        self.params: List[RustVariable] = []
        self.init_code: List[str] = []
        self.req_code: List[str] = []
        self.resp_code: List[str] = []

    def declare(self, name: str, rtype: RustType, temp: bool) -> None:
        if name in self.name2var:
            raise Exception(f"variable {name} already defined")
        else:
            var = RustVariable(
                name, rtype, temp, name == "rpc_req" or name == "rpc_resp"
            )
            self.name2var[name] = var
            if not temp and not var.rpc:
                self.internal_states.append(var)

    def push_code(self, code: str) -> None:
        if self.current_func == FUNC_INIT:
            self.init_code.append(code)
        elif self.current_func == FUNC_REQ:
            self.req_code.append(code)
        elif self.current_func == FUNC_RESP:
            self.resp_code.append(code)
        else:
            raise Exception("unknown function")

    def find_var(self, name: str) -> Optional[RustVariable]:
        if name in self.name2var:
            return self.name2var[name]
        else:
            return None

    def explain(self) -> str:
        return f"Context.Explain:\n\t{self.internal_states}\n\t{self.name2var}\n\t{self.current_func}\n\t{self.params}\n\t{self.init_code}\n\t{self.req_code}\n\t{self.resp_code}"

    def func_mapping(self, fname: str) -> RustFunctionType:
        match fname:
            case "randomf":
                return RustGlobalFunctions["random_f64"]
            case _:
                raise Exception("unknown function")

    def gen_struct_names(self) -> List[str]:
        ret = []
        # todo! check this
        # for i in self.internal_states:
        #     ret.append(i.name)
        return ret

    def gen_init_localvar(self) -> List[str]:
        ret = []
        for (_, v) in self.name2var.items():
            if not v.temp and not v.rpc:
                ret.append(v.gen_init_localvar())
        return ret

    def gen_internal_names(self) -> List[str]:
        ret = []
        for i in self.internal_states:
            ret.append(i.name)
        return ret

    def gen_init_tempvar(self) -> List[str]:
        ret = []
        for (_, v) in self.name2var.items():
            if v.temp and not v.rpc:
                ret.append(v.gen_init_localvar())
        return ret

    def gen_struct_declaration(self) -> List[str]:
        ret = []
        for v in self.internal_states:
            ret.append(v.gen_struct_declaration())
        return ret


class RustGenerator(Visitor):
    def __init__(self) -> None:
        super().__init__()

    def visitNode(self, node: Node, ctx: RustContext):
        return node.__class__.__name__

    def visitProgram(self, node: Program, ctx: RustContext) -> None:
        node.definition.accept(self, ctx)
        node.init.accept(self, ctx)
        for v in ctx.internal_states:
            if v.init == "":
                v.init = v.type.gen_init()
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)

    def visitInternal(self, node: Internal, ctx: RustContext) -> None:
        for (i, t) in node.internal:
            name = i.name
            rust_type = t.accept(self, ctx)
            ctx.declare(name, rust_type, False)

    def visitProcedure(self, node: Procedure, ctx: RustContext):
        match node.name:
            case "init":
                ctx.current_func = FUNC_INIT
            case "req":
                ctx.current_func = FUNC_REQ
            case "resp":
                ctx.current_func = FUNC_RESP
            case _:
                raise Exception("unknown function")
        if node.name != "init":
            ctx.declare(f"rpc_{node.name}", RustRpcType("req", []), False)

        for p in node.params:
            name = p.name
            if ctx.find_var(name) == None:
                raise Exception(f"param {name} not found")

        for s in node.body:
            code = s.accept(self, ctx)
            ctx.push_code(code)

    def visitStatement(self, node: Statement, ctx: RustContext) -> str:
        if node.stmt == None:
            return ";//NULL_STMT\n"
        else:
            if isinstance(node.stmt, Expr):
                return node.stmt.accept(self, ctx) + ";\n"
            else:
                return node.stmt.accept(self, ctx)

    def visitMatch(self, node: Match, ctx: RustContext) -> str:
        template = "match ("
        template += node.expr.accept(self, ctx) + ") {"
        for (p, s) in node.actions:
            leg = f"    {p.accept(self, ctx)} => {{"
            for st in s:
                leg += f"{st.accept(self, ctx)}\n"
            leg += "}"
            template += leg
        template += "}"
        return template

    def visitAssign(self, node: Assign, ctx: RustContext):
        name = node.left.name
        value = node.right.accept(self, ctx)
        if ctx.current_func == FUNC_INIT:
            if ctx.find_var(name) == None:
                raise Exception(f"variable {name} not found")
            var = ctx.find_var(name)
            assert not var.temp and not var.rpc
            var.init = value
            return ""
        elif ctx.current_func == FUNC_REQ or ctx.current_func == FUNC_RESP:
            if ctx.find_var(name) == None:
                ctx.declare(name, RustType("unknown"), True)  # declar temp
                lhs = "let mut " + name
            else:
                var = ctx.find_var(name)
                if var.temp or var.rpc:
                    lhs = name
                else:
                    lhs = "self." + name
            return f"{lhs} = {value};\n"
        else:
            raise Exception("unknown function")

    def visitPattern(self, node: Pattern, ctx):
        return node.value.accept(self, ctx)

    def visitExpr(self, node: Expr, ctx):
        return f"{node.lhs.accept(self, ctx)} {node.op.accept(self, ctx)} {node.rhs.accept(self, ctx)}"

    def visitOperator(self, node: Operator, ctx):
        match node:
            case Operator.ADD:
                return "+"
            case Operator.SUB:
                return "-"
            case Operator.MUL:
                return "*"
            case Operator.DIV:
                return "/"
            case Operator.AND:
                return "&&"
            case Operator.OR:
                return "||"
            case Operator.EQ:
                return "=="
            case Operator.NEQ:
                return "!="
            case Operator.GT:
                return ">"
            case Operator.GE:
                return ">="
            case Operator.LT:
                return "<"
            case Operator.LE:
                return "<="
            case Operator.NOT:
                return "!"
            case _:
                raise Exception("unknown operator")

    def visitIdentifier(self, node: Identifier, ctx):
        var = ctx.find_var(node.name)
        if var == None:
            raise Exception(f"variable {node.name} not found")
        else:
            if var.temp or var.rpc:
                return node.name
            else:
                return "self." + node.name

    def visitType(self, node: Type, ctx):
        name: str = node.name
        if name.startswith("Vec<"):
            last = name[4:].split(">")[0].strip()
            return RustVecType("Vec", map_basic_type(last))
        elif name.startswith("Map<"):
            middle = name[4:].split(">")[0]
            key = middle.split(",")[0].strip()
            value = middle.split(",")[1].strip()
            return RustMapType("HashMap", map_basic_type(key), map_basic_type(value))
        else:
            return map_basic_type(name)

    def visitFuncCall(self, node: FuncCall, ctx) -> str:
        fn_name = node.name.name
        fn: RustFunctionType = ctx.func_mapping(fn_name)

        args = [f"({i.accept(self, ctx)}).into()" for i in node.args if i is not None]
        ret = fn.gen_call(args)

        return ret

    def visitMethodCall(self, node: MethodCall, ctx) -> str:
        var = ctx.find_var(node.obj.name)
        if var == None:
            raise Exception(f"object {node.obj.name} not found")
        else:
            t = var.type
            if isinstance(t, RustRpcType):

                args = [i.accept(ExprResolver(), None) for i in node.args]
                match node.method:
                    case MethodType.GET:
                        ret = proto_gen_get(var.name, args)
                    case MethodType.SET:
                        ret = proto_gen_set(var.name, args)
                    case _:
                        raise Exception("unknown method")
            else:
                args = [i.accept(self, ctx) for i in node.args]
                new_arg = []
                for i in args:
                    if i.startswith('"'):
                        new_arg.append(i + ".to_string()")
                    else:
                        new_arg.append(i)
                args = new_arg
                if ctx.current_func == FUNC_INIT:
                    ret = node.obj.name
                else:
                    ret = node.obj.accept(self, ctx)

                match node.method:
                    case MethodType.GET:
                        ret += t.gen_get(args)
                    case MethodType.SET:
                        ret += t.gen_set(args)
                    case MethodType.SIZE:
                        ret += t.gen_size()
                    case _:
                        raise Exception("unknown method")

        return ret

    def visitSend(self, node: Send, ctx) -> str:
        if ctx.current_func == "unknown" or ctx.current_func == "init":
            raise Exception("send not in function")

        if isinstance(node.msg, Identifier):
            if node.msg.name == "rpc_req":
                inner = """
                    let inner_gen = EngineTxMessage::RpcMessage(RpcMessageTx {
                                meta_buf_ptr: msg.meta_buf_ptr.clone(),
                                addr_backend: msg.addr_backend ,
                            });
                """
            elif node.msg.name == "rpc_resp":
                inner = """
                    let inner_gen = EngineRxMessage::RpcMessage(msg)
                """
            else:
                raise Exception("unknown send target")
        else:
            inner = node.msg.accept(self, ctx)
            inner = f"let inner_gen = {inner};\n"
        if ctx.current_func == FUNC_REQ:
            if node.direction == "NET":
                return f"{inner}self.tx_outputs()[0].send(inner_gen)?"
            elif node.direction == "APP":
                return f"{inner}self.rx_outputs()[0].send(inner_gen)?"
        elif ctx.current_func == FUNC_RESP:
            if node.direction == "NET":
                return f"{inner}self.tx_outputs()[0].send(inner_gen)?"
            elif node.direction == "APP":
                return f"{inner}self.rx_outputs()[0].send(inner_gen)?"
        else:
            raise Exception("unknown function")

    def visitLiteral(self, node: Literal, ctx):
        return node.value.replace("'", '"')

    def visitError(self, node: Error, ctx) -> str:
        return """EngineRxMessage::Ack(
                                RpcId::new(
                                    unsafe { &*msg.meta_buf_ptr.as_meta_ptr() }.conn_id,
                                    unsafe { &*msg.meta_buf_ptr.as_meta_ptr() }.call_id,
                                ),
                                TransportStatus::Error(unsafe { NonZeroU32::new_unchecked(403) }),
                            )"""


class ExprResolver(Visitor):
    def __init__(self) -> None:
        pass

    def visitNode(self, node: Node, ctx) -> str:
        print(node.__class__.__name__)
        raise Exception("Unreachable!")

    def visitLiteral(self, node: Literal, ctx) -> str:
        return node.value.replace("'", '"')

    def visitIdentifier(self, node: Identifier, ctx) -> str:
        return node.name

    def visitExpr(self, node: Expr, ctx) -> str:
        return node.lhs.accept(self, ctx) + str(node.op) + node.rhs.accept(self, ctx)

    def visitError(self, node: Error, ctx) -> str:
        return "ERROR"

    def visitMethodCall(self, node: MethodCall, ctx):
        return (
            node.obj.accept(self, ctx)
            + "."
            + node.method.name
            + "("
            + ",".join([a.accept(self, ctx) for a in node.args])
            + ")"
        )
