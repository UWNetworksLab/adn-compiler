from typing import Dict, List, Optional

from compiler.element.backend.envoy.wasmtype import *
from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.node import *
from compiler.element.visitor import Visitor

FUNC_REQ_HEADER = "req_hdr"
FUNC_REQ_BODY = "req_body"
FUNC_RESP_HEADER = "resp_hdr"
FUNC_RESP_BODY = "resp_body"
FUNC_INIT = "init"


class WasmContext:
    def __init__(self) -> None:
        self.internal_states: List[WasmVariable] = []
        self.inners: List[WasmVariable] = []
        self.name2var: Dict[str, WasmVariable] = {}
        self.current_func: str = "unknown"
        self.params: List[WasmVariable] = []
        self.init_code: List[str] = []
        self.req_hdr_code: List[str] = []
        self.resp_hdr_code: List[str] = []
        self.req_body_code: List[str] = []
        self.resp_body_code: List[str] = []

    def declare(self, name: str, rtype: WasmType, temp: bool, atomic: bool) -> None:
        if name in self.name2var:
            raise Exception(f"variable {name} already defined")
        else:
            var = WasmVariable(
                name,
                rtype,
                temp,
                name == "rpc_request" or name == "rpc_response",
                atomic,
            )
            if not temp and not var.rpc and atomic:
                var.init = rtype.gen_init()
                self.internal_states.append(var)
                v_inner = WasmVariable(name + "_inner", rtype, False, False, False)
                self.inners.append(v_inner)
                self.name2var[name] = v_inner
            elif name == "rpc_request":
                self.name2var["rpc_req"] = var
            elif name == "rpc_response":
                self.name2var["rpc_resp"] = var
            else:
                self.name2var[name] = var

    def gen_inners(self) -> str:
        ret = ""
        for v in self.internal_states:
            ret = ret + f"let mut {v.name}_inner = {v.name}.lock().unwrap();\n"
        return ret

    def clear_temps(self) -> None:
        new_dic = {}
        for k, v in self.name2var.items():
            if not v.temp:
                new_dic[k] = v
        self.name2var = new_dic

    def push_code(self, code: str) -> None:
        if self.current_func == FUNC_INIT:
            self.init_code.append(code)
        elif self.current_func == FUNC_REQ_HEADER:
            self.req_hdr_code.append(code)
        elif self.current_func == FUNC_REQ_BODY:
            self.req_body_code.append(code)
        elif self.current_func == FUNC_RESP_HEADER:
            self.resp_hdr_code.append(code)
        elif self.current_func == FUNC_RESP_BODY:
            self.resp_body_code.append(code)
        else:
            raise Exception("unknown function")

    def find_var(self, name: str) -> Optional[WasmVariable]:
        if name in self.name2var:
            return self.name2var[name]
        else:
            return None

    def explain(self) -> str:
        return f"Context.Explain:\n\t{self.internal_states}\n\t{self.name2var}\n\t{self.current_func}\n\t{self.params}\n\t{self.init_code}\n\t{self.req_code}\n\t{self.resp_code}"

    def gen_global_var_def(self) -> str:
        ret = ""
        for v in self.internal_states:
            wrapped = WasmMutex(v.type)
            ret = (
                ret
                + f"""
                lazy_static! {{
                    static ref {v.name}: {str(wrapped)} = {wrapped.gen_init()};
                }}\n
            """
            )
        return ret


class WasmGenerator(Visitor):
    def __init__(self, placement: str) -> None:
        self.placement = placement
        if placement != "client" and placement != "server":
            raise Exception("placement should be sender or receiver")

    def visitNode(self, node: Node, ctx: WasmContext):
        return node.__class__.__name__

    def visitProgram(self, node: Program, ctx: WasmContext) -> None:
        node.definition.accept(self, ctx)
        node.init.accept(self, ctx)
        for v in ctx.internal_states:
            if v.init == "":
                v.init = v.type.gen_init()
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)

    def visitInternal(self, node: Internal, ctx: WasmContext) -> None:
        for i, t in node.internal:
            name = i.name
            wasm_type = t.accept(self, ctx)
            ctx.declare(name, wasm_type, False, True)

    def visitProcedure(self, node: Procedure, ctx: WasmContext):
        #!todo add hdr
        match node.name:
            case "init":
                ctx.current_func = FUNC_INIT
                proto_name = "init"  # unused, make python happy
            case "req":
                ctx.current_func = FUNC_REQ_BODY
                proto_name = "Request"
            case "resp":
                ctx.current_func = FUNC_RESP_BODY
                proto_name = "Response"
            case _:
                raise Exception("unknown function")
        ctx.clear_temps()
        if node.name == "req":
            name = "request"
        elif node.name == "resp":
            name = "response"
        else:
            name = node.name
        if name != "init":
            ctx.declare(f"rpc_{name}", WasmRpcType(f"rpc_{name}", []), True, False)
        inners = ctx.gen_inners()
        ctx.push_code(inners)

        prefix = f"""
        if let Some(body) = self.get_http_{name}_body(0, body_size) {{

            match ping::PingEcho{proto_name}::decode(&body[5..]) {{
                Ok(rpc_{name}) => {{
        """
        suffix = f"""
                        }}
                Err(e) => log::warn!("decode error: {{}}", e),
            }}
        }}

        """

        if ctx.current_func != FUNC_INIT:
            ctx.push_code(prefix)

        for p in node.params:
            name = p.name
            if ctx.find_var(name) == None:
                LOG.error(f"param {name} not found in VisitProcedure")
                raise Exception(f"param {name} not found")
        for s in node.body:
            code = s.accept(self, ctx)
            ctx.push_code(code)

        if ctx.current_func != FUNC_INIT:
            ctx.push_code(suffix)

    def visitStatement(self, node: Statement, ctx: WasmContext) -> str:
        if node.stmt == None:
            return ";//NULL_STMT\n"
        else:
            if isinstance(node.stmt, Expr) or isinstance(node.stmt, Send):
                ret = node.stmt.accept(self, ctx) + ";\n"
                return ret
            else:
                return node.stmt.accept(self, ctx)

    def visitMatch(self, node: Match, ctx: WasmContext) -> str:
        template = "match ("
        if isinstance(node.expr, Identifier):
            var = ctx.find_var(node.expr.name)
            if var.type.name == "String":
                template += node.expr.accept(self, ctx) + ".as_str()"
        else:
            template += node.expr.accept(self, ctx)
        template += ") {"
        for p, s in node.actions:
            leg = f"    {p.accept(self, ctx)} => {{"
            for st in s:
                leg += f"{st.accept(self, ctx)}\n"
            leg += "}"
            template += leg
        template += "}"
        return template

    def visitAssign(self, node: Assign, ctx: WasmContext) -> str:
        value = node.right.accept(self, ctx)
        var = ctx.find_var(node.left.name)

        if ctx.current_func == FUNC_INIT:
            if var == None:
                LOG.error(f"variable not found in assign")
                raise ValueError
            if not var.temp and not var.atomic:
                if isinstance(var.type, WasmBasicType):
                    lhs = "*" + var.name
                else:
                    lhs = var.name
            else:
                lhs = var.name
            if var.type.name == "String":
                rhs = f"{value}.to_string()"
            else:
                rhs = value
            return f"{lhs} = {rhs};"
        else:
            if var == None:
                ctx.declare(node.left.name, WasmType("unknown"), True, False)
                lhs = "let mut " + node.left.name
                return f"{lhs} = {value};\n"
            else:
                if not var.temp and not var.atomic:
                    if isinstance(var.type, WasmBasicType):
                        lhs = "*" + var.name
                    else:
                        lhs = var.name
                else:
                    lhs = var.name
                return f"{lhs} = ({value}) as {var.type.name};\n"

    def visitPattern(self, node: Pattern, ctx):
        if isinstance(node.value, Identifier):
            assert node.some
            name = node.value.name
            if ctx.find_var(name) == None:
                ctx.declare(name, WasmBasicType("String"), True, False)  # declare temp
            else:
                LOG.error("variable already defined should not appear in Some")
                raise Exception(f"variable {name} already defined")
            return f"Some({node.value.accept(self, ctx)})"
        if node.some:
            return f"Some({node.value.accept(self, ctx)})"
        else:
            return node.value.accept(self, ctx)

    def visitExpr(self, node: Expr, ctx):
        return f"({node.lhs.accept(self, ctx)} {node.op.accept(self, ctx)} {node.rhs.accept(self, ctx)})"

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
            LOG.error(f"variable name {node.name} not found")
            raise Exception(f"variable {node.name} not found")
        else:
            if var.temp or var.rpc:
                return var.name
            else:
                assert var.is_unwrapped()
                if isinstance(var.type, WasmBasicType):
                    return "*" + var.name
                else:
                    return var.name

    def visitType(self, node: Type, ctx):
        def map_basic_type(name: str):
            match name:
                case "float":
                    return WasmBasicType("f32")
                case "int":
                    return WasmBasicType("i32")
                case "string":
                    return WasmBasicType("String")
                case "Instant":
                    return WasmBasicType("Instant")
                case _:
                    LOG.warning(f"unknown type: {name}")
                    return WasmType(name)

        name: str = node.name
        if name.startswith("Vec<"):
            last = name[4:].split(">")[0].strip()
            return WasmVecType("Vec", map_basic_type(last))
        elif name.startswith("Map<"):
            middle = name[4:].split(">")[0]
            key = middle.split(",")[0].strip()
            value = middle.split(",")[1].strip()
            return WasmMapType("HashMap", map_basic_type(key), map_basic_type(value))
        else:
            return map_basic_type(name)

    def visitFuncCall(self, node: FuncCall, ctx) -> str:
        def func_mapping(fname: str) -> WasmFunctionType:
            match fname:
                case "randomf":
                    return WasmGlobalFunctions["random_f32"]
                case "update_window":
                    return WasmGlobalFunctions["update_window"]
                case "current_time":
                    return WasmGlobalFunctions["current_time"]
                case "min":
                    return WasmGlobalFunctions["min_f64"]
                case "time_diff":
                    return WasmGlobalFunctions["time_diff"]
                case "time_diff_ref":
                    return WasmGlobalFunctions["time_diff_ref"]
                case "encrypt":
                    return WasmGlobalFunctions["encrypt"]
                case "decrypt":
                    return WasmGlobalFunctions["decrypt"]
                case _:
                    LOG.error(f"unknown global function: {fname} in func_mapping")
                    raise Exception("unknown global function:", fname)

        fn_name = node.name.name
        fn: WasmFunctionType = func_mapping(fn_name)
        types = fn.args
        args = [f"{i.accept(self, ctx)}" for i in node.args if i is not None]
        for idx, ty in enumerate(types):
            if ty.name == "&str":
                args[idx] = f"&{args[idx]}"
            elif ty.name == "Instant":
                args[idx] = f"{args[idx]}.clone()"
            else:
                args[idx] = f"({args[idx]} as {ty.name})"
        ret = fn.gen_call(args)
        return ret

    def visitMethodCall(self, node: MethodCall, ctx) -> str:
        var = ctx.find_var(node.obj.name)
        if var == None:
            LOG.error(f"{node.obj.name} is not declared")
            raise Exception(f"object {node.obj.name} not found")
        t = var.type

        args = [i.accept(self, ctx) for i in node.args]

        if not var.rpc:
            new_arg = []
            for i in args:
                if i.startswith('"'):
                    new_arg.append(i + ".to_string()")
                else:
                    new_arg.append(i)
            args = new_arg

        if ctx.current_func == FUNC_INIT:
            ret = var.name
        else:
            ret = node.obj.accept(self, ctx)
        match node.method:
            case MethodType.GET:
                ret += t.gen_get(args)
            case MethodType.SET:
                ret += t.gen_set(args)
            case MethodType.DELETE:
                ret += t.gen_delete(args)
            case MethodType.SIZE:
                ret += t.gen_size()
            case _:
                raise Exception("unknown method", node.method)
        return ret

    def visitSend(self, node: Send, ctx) -> str:
        #! todo currently do not support doing things after send!
        if isinstance(node.msg, Error):
            return """
                        self.send_http_response(
                            403,
                            vec![
                                ("grpc-status", "1"),
                            ],
                            None,
                        );
                        return Action::Pause;
                    """
        else:
            return "return Action::Continue;"

    def visitLiteral(self, node: Literal, ctx):
        return node.value.replace("'", '"')

    def visitError(self, node: Error, ctx) -> str:
        raise NotImplementedError
