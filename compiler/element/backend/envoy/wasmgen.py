from typing import Dict, List, Optional

from compiler.element.backend.envoy.wasmtype import *
from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.node import *
from compiler.element.visitor import Visitor

FUNC_INIT = "init"
FUNC_REQ_HEADER = "req_hdr"
FUNC_REQ_BODY = "req_body"
FUNC_RESP_HEADER = "resp_hdr"
FUNC_RESP_BODY = "resp_body"
FUNC_EXTERNAL_RESPONSE = "external_response"


class WasmContext:
    def __init__(self, proto=None, method_name=None) -> None:
        self.internal_states: List[
            WasmVariable
        ] = []  # List of internal state variables
        self.inners: List[
            WasmVariable
        ] = []  # Inners are temp variables used to access state
        self.name2var: Dict[
            str, WasmVariable
        ] = {}  # Mapping from names to Wasm variables
        self.current_procedure: str = "unknown"  # Name of the current procedure (i.e., init/req/resp) being processed
        self.params: List[WasmVariable] = []  # List of parameters for the function
        self.init_code: List[str] = []  # Code for initialization
        self.req_hdr_code: List[str] = []  # Code for request header processing
        self.resp_hdr_code: List[str] = []  # Code for response header processing
        self.req_body_code: List[str] = []  # Code for request body processing
        self.resp_body_code: List[str] = []  # Code for response body processing
        self.external_call_response_code: List[
            str
        ] = []  # Code for handling external call responses (state sync)
        self.decode: bool = True  # Flag to determine whether to decode the RPC
        self.proto: str = proto  # Protobuf used
        self.method_name: str = method_name  # Name of the RPC method

        # Maps to store the state (incl. RPC) operations on request/response headers and bodies
        self.access_ops: Dict[str, Dict[str, MethodType]] = {
            FUNC_INIT: {},
            FUNC_REQ_HEADER: {},
            FUNC_REQ_BODY: {},
            FUNC_RESP_HEADER: {},
            FUNC_RESP_BODY: {},
        }

    def declare(
        self,
        name: str,
        rtype: WasmType,
        temp_var: bool,
        atomic: bool,
        consistency: str = None,
        combiner: str = None,
        persistence: bool = False,
    ) -> None:
        # This method declares a new variable in the Wasm context and add it to the name2var mapping
        if name in self.name2var:
            # Check for duplicate variable names
            raise Exception(f"variable {name} already defined")
        else:
            # Create a new WasmVariable instance and add it to the name2var mapping
            var = WasmVariable(
                name,
                rtype,
                temp_var,
                name == "rpc_request" or name == "rpc_response",
                atomic,
                inner=False,
                consistency=consistency,
                combiner=combiner,
                persistence=persistence,
            )
            if consistency == "strong":
                self.internal_states.append(var)
                self.name2var[name] = var
            elif not temp_var and not var.rpc and atomic:
                # If it's not a temp variable and does not belong to RPC request or response processing.
                var.init = rtype.gen_init()
                self.internal_states.append(var)
                # Create an inner variable for the declared variable
                v_inner = WasmVariable(
                    name + "_inner", rtype, False, False, False, inner=True
                )
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
        # Generate inners based on operations
        for v in self.internal_states:
            if v.consistency != "strong":
                if v.name in self.access_ops[self.current_func]:
                    if self.access_ops[self.current_func][v.name] == MethodType.GET:
                        ret = (
                            ret
                            + f"let mut {v.name}_inner = {v.name}.read().unwrap();\n"
                        )
                    elif self.access_ops[self.current_func][v.name] == MethodType.SET:
                        ret = (
                            ret
                            + f"let mut {v.name}_inner = {v.name}.write().unwrap();\n"
                        )
                    else:
                        raise Exception("unknown method in gen_inners.")
        return ret

    def clear_temps(self) -> None:
        new_dic = {}
        for k, v in self.name2var.items():
            if not v.temp:
                new_dic[k] = v
        self.name2var = new_dic

    def push_code(self, code: str) -> None:
        # This method appends the given code to the appropriate list based on the current function context
        if self.current_procedure == FUNC_INIT:
            self.init_code.append(code)
        elif self.current_procedure == FUNC_REQ_HEADER:
            self.req_hdr_code.append(code)
        elif self.current_procedure == FUNC_REQ_BODY:
            self.req_body_code.append(code)
        elif self.current_procedure == FUNC_RESP_HEADER:
            self.resp_hdr_code.append(code)
        elif self.current_procedure == FUNC_RESP_BODY:
            self.resp_body_code.append(code)
        elif self.current_procedure == FUNC_EXTERNAL_RESPONSE:
            self.external_call_response_code.append(code)
        else:
            raise Exception(
                "unknown function"
            )  # Raise an exception if the current function context is unknown

    def find_var(self, name: str) -> Optional[WasmVariable]:
        if name in self.name2var:
            return self.name2var[name]
        else:
            return None

    def explain(self) -> str:
        return f"Context.Explain:\n\t{self.internal_states}\n\t{self.name2var}\n\t{self.current_procedure}\n\t{self.params}\n\t{self.init_code}\n\t{self.req_code}\n\t{self.resp_code}"

    def gen_global_var_def(self) -> str:
        ret = ""
        for v in self.internal_states:
            if v.consistency == "strong":
                continue
            wrapped = WasmRwLock(v.type)
            ret = (
                ret
                + f"""
                lazy_static! {{
                    static ref {v.name}: {str(wrapped)} = {wrapped.gen_init()};
                }}\n
            """
            )
        return ret

    def gen_meta_get(self, field: str):
        assert field.startswith("meta")
        if field == "meta_status":
            if self.current_procedure == FUNC_REQ_BODY:
                # Meta status is only set in the response
                raise Exception("Should not read meta in request")
            if self.current_procedure == FUNC_RESP_BODY:
                self.resp_hdr_code.append(
                    """
                    if let Some(status_code) = self.get_http_response_header(":status") {
                        if status_code == "200" {
                            self.meta_status = "success".to_string();
                        } else {
                            self.meta_status = "failure".to_string();
                        }
                    } else {
                        panic!("No status code found in response headers");
                    }
                """
                )


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
            if v.init == "" and v.consistency != "strong":
                v.init = v.type.gen_init()
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)

    def visitInternal(self, node: Internal, ctx: WasmContext) -> None:
        # Iterate through all internal state variables and declare them
        for (i, t, cons, comb, per) in node.internal:
            state_name = i.name
            state_wasm_type = t.accept(self, ctx)
            ctx.declare(
                state_name, state_wasm_type, False, True, cons.name, comb.name, per.name
            )

    def visitProcedure(self, node: Procedure, ctx: WasmContext):
        # TODO: Add request and response header processing.
        match node.name:
            case "init":
                ctx.current_procedure = FUNC_INIT
                procedure_type = "init"  # unused, make python happy
            case "req":
                ctx.current_procedure = FUNC_REQ_BODY
                procedure_type = "Request"
            case "resp":
                ctx.current_procedure = FUNC_RESP_BODY
                procedure_type = "Response"
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

        # Boilerplate code for decoding the RPC message
        prefix_decode_rpc = f"""
        if let Some(body) = self.get_http_{name}_body(0, body_size) {{

            match {ctx.proto}::{ctx.method_name}{procedure_type}::decode(&body[5..]) {{
                Ok(mut rpc_{name}) => {{
        """
        suffix_decode_rpc = f"""
                        }}
                Err(e) => log::warn!("decode error: {{}}", e),
            }}
        }}

        """

        # If the procedure does not access the RPC message, then we do not need to decode it
        if ctx.current_func != FUNC_INIT:
            if ctx.current_func == FUNC_REQ_BODY:
                if "rpc_req" in ctx.access_ops[ctx.current_func]:
                    ctx.push_code(prefix_decode_rpc)
            elif ctx.current_func == FUNC_RESP_BODY:
                if "rpc_resp" in ctx.access_ops[ctx.current_func]:
                    ctx.push_code(prefix_decode_rpc)

        for p in node.params:
            name = p.name
            if ctx.find_var(name) == None:
                LOG.error(f"param {name} not found in VisitProcedure")
                raise Exception(f"param {name} not found")
        for s in node.body:
            code = s.accept(self, ctx)
            ctx.push_code(code)

        if ctx.current_func != FUNC_INIT:
            if ctx.current_func == FUNC_REQ_BODY:
                if "rpc_req" in ctx.access_ops[ctx.current_func]:
                    ctx.push_code(suffix_decode_rpc)
            elif ctx.current_func == FUNC_RESP_BODY:
                if "rpc_resp" in ctx.access_ops[ctx.current_func]:
                    ctx.push_code(suffix_decode_rpc)

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
            # TODO: Check type after we have type inference
            template += node.expr.accept(self, ctx) + ".as_str()"
            # var = ctx.find_var(node.expr.name)
            # if var.type.name == "String":
            #     template += node.expr.accept(self, ctx) + ".as_str()"
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

        if ctx.current_procedure == FUNC_INIT:
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
                # If var is none, it's a temparary variable.
                # NOTE: This is a hacky way to handle temp variables. We assume that temp variables are always of type String.
                # TODO(): Assign correct type to temp variable after we have type inference.
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

    def visitPattern(self, node: Pattern, ctx: WasmContext):
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

    def visitIdentifier(self, node: Identifier, ctx: WasmContext):
        var = ctx.find_var(node.name)
        if var == None:
            LOG.error(f"variable name {node.name} not found")
            raise Exception(f"variable {node.name} not found")
        else:
            if var.temp or var.rpc:
                return var.name
            else:
                # Not sure what this does
                # assert var.is_unwrapped()
                if isinstance(var.type, WasmBasicType):
                    return "*" + var.name
                else:
                    return var.name

    def visitType(self, node: Type, ctx: WasmContext):
        def map_basic_type(type_def: str):
            match type_def:
                case "float":
                    return WasmBasicType("f32")
                case "int":
                    return WasmBasicType("i32")
                case "string":
                    return WasmBasicType("String")
                case "Instant":
                    return WasmBasicType("f32")
                case _:
                    LOG.warning(f"unknown type: {type_def}")
                    return WasmType(type_def)

        type_def: str = node.name
        if type_def.startswith("Vec<"):
            vec_type = type_def[4:].split(">")[0].strip()
            # If the vector state requires strong consistency, we need to rely on an external storage
            # Otherwise (local state or eventual consistent state), use a local vector
            if node.consistency and node.consistency == "strong":
                return WasmSyncVecType(map_basic_type(vec_type))
            else:
                return WasmVecType(map_basic_type(vec_type))
        elif type_def.startswith("Map<"):
            temp = type_def[4:].split(">")[0]
            key_type = temp.split(",")[0].strip()
            value_type = temp.split(",")[1].strip()
            # If the map state requires strong consistency, we need to rely on an external storage
            # Otherwise (local state or eventual consistent state), use a local map
            if node.consistency and node.consistency == "strong":
                return WasmSyncMapType(
                    map_basic_type(key_type), map_basic_type(value_type)
                )
            else:
                return WasmMapType(map_basic_type(key_type), map_basic_type(value_type))
        else:
            return map_basic_type(type_def)

    def visitFuncCall(self, node: FuncCall, ctx: WasmContext) -> str:
        def func_mapping(fname: str) -> WasmFunctionType:
            match fname:
                case "randomf":
                    return WasmGlobalFunctions["random_f32"]
                case "randomu":
                    return WasmGlobalFunctions["random_u32"]
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
                args[idx] = f"(({args[idx]}).clone() as {ty.name})"
        ret = fn.gen_call(args)
        return ret

    def visitMethodCall(self, node: MethodCall, ctx: WasmContext) -> str:
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
        if ctx.current_procedure == FUNC_INIT:
            ret = var.name
        elif var.consistency == "strong":
            ret = ""
        else:
            ret = node.obj.accept(self, ctx)

        if var.rpc:
            match node.method:
                case MethodType.GET:
                    ret = proto_gen_get(var.name, args, ctx)
                case MethodType.SET:
                    ret = proto_gen_set(var.name, args, ctx)
                case MethodType.DELETE:
                    raise NotImplementedError
                case MethodType.SIZE:
                    ret = proto_gen_size(args)
                case MethodType.BYTE_SIZE:
                    return proto_gen_bytesize(var.name, args)
                case _:
                    raise Exception("unknown method", node.method)
        else:
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

    def visitSend(self, node: Send, ctx: WasmContext) -> str:
        # TODO: currently do not support doing things after send!
        # TODO: The status code should be configurable
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
            # return "return Action::Continue;"
            return ""

    def visitLiteral(self, node: Literal, ctx):
        return node.value.replace("'", '"')

    def visitError(self, node: Error, ctx) -> str:
        raise NotImplementedError


def proto_gen_get(rpc: str, args: List[str], ctx: WasmContext) -> str:
    assert len(args) == 1
    arg = args[0].strip('"')
    if arg.startswith("meta"):
        ctx.gen_meta_get(arg)
        return f"self.{arg}"
    else:
        return f"{rpc}.{arg}.clone()"


def proto_gen_set(rpc: str, args: List[str], ctx: WasmContext) -> str:
    assert len(args) == 2
    k = args[0].strip('"')
    v = args[1] + ".to_string()"
    if k.startswith("meta"):
        raise NotImplementedError
    #! fix that use name match
    if rpc == "rpc_request":
        return f"self.PingEcho_request_modify_{k}(&mut {rpc}, {v})"
    elif rpc == "rpc_response":
        return f"self.PingEcho_response_modify_{k}(&mut {rpc}, {v})"


def proto_gen_size(rpc: str, args: List[str]) -> str:
    assert len(args) == 0
    return f"{rpc}.size()"


def proto_gen_bytesize(rpc: str, args: List[str]) -> str:
    assert len(args) == 0
    #! fix me, todo should return usize
    return f"mem::size_of_val(&{rpc}) as f32"
