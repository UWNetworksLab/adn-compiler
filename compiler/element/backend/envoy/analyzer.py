from compiler.element.backend.envoy.wasmgen import WasmContext
from compiler.element.node import *
from compiler.element.visitor import Visitor

FUNC_INIT = "init"
FUNC_REQ_HEADER = "req_hdr"
FUNC_REQ_BODY = "req_body"
FUNC_RESP_HEADER = "resp_hdr"
FUNC_RESP_BODY = "resp_body"


class AccessAnalyzer(Visitor):
    # AccessAnalyzer is used to analyze the IR and record the access operations.
    # The operations are then used to avoid unnecessary locks and RPC decode when generating the corresponding WASM code.
    def __init__(self, placement: str):
        self.placement = placement
        if placement != "client" and placement != "server":
            raise Exception("placement should be sender or receiver")

    def visitNode(self, node: Node, ctx: WasmContext) -> str:
        pass

    def visitProgram(self, node: Program, ctx: WasmContext) -> str:
        node.init.accept(self, ctx)
        node.req.accept(self, ctx)
        node.resp.accept(self, ctx)

    def visitInternal(self, node: Internal, ctx: WasmContext):
        pass

    def visitProcedure(self, node: Procedure, ctx: WasmContext):
        match node.name:
            case "init":
                ctx.current_procedure = FUNC_INIT
            case "req":
                ctx.current_procedure = FUNC_REQ_BODY
            case "resp":
                ctx.current_procedure = FUNC_RESP_BODY
            case _:
                raise Exception("unknown function")
        for b in node.body:
            b.accept(self, ctx)

    def visitStatement(self, node: Statement, ctx: WasmContext):
        if node.stmt != None:
            node.stmt.accept(self, ctx)

    def visitMatch(self, node: Match, ctx: WasmContext):
        node.expr.accept(self, ctx)
        for p, s in node.actions:
            for st in s:
                st.accept(self, ctx)

    def visitAssign(self, node: Assign, ctx: WasmContext):
        node.right.accept(self, ctx)

    def visitPattern(self, node: Pattern, ctx: WasmContext):
        pass

    def visitExpr(self, node: Expr, ctx: WasmContext):
        pass

    def visitIdentifier(self, node: Identifier, ctx: WasmContext):
        pass

    def visitConsistencyDecorator(self, node: ConsistencyDecorator, ctx: WasmContext):
        pass

    def visitCombinerDecorator(self, node: CombinerDecorator, ctx: WasmContext):
        pass

    def visitPersistenceDecorator(self, node: PersistenceDecorator, ctx: WasmContext):
        pass

    def visitType(self, node: Type, ctx: WasmContext):
        pass

    def visitFuncCall(self, node: FuncCall, ctx: WasmContext):
        pass

    def visitMethodCall(self, node: MethodCall, ctx: WasmContext):
        # Add access operations to the corresponding function.
        # If there are multiple operations on the same object, the set takes priority.
        if (
            node.obj.name not in ctx.access_ops[ctx.current_procedure]
            or ctx.access_ops[ctx.current_procedure][node.obj.name] != MethodType.SET
        ):
            ctx.access_ops[ctx.current_procedure][node.obj.name] = node.method

        # Handle nested method calls
        for arg in node.args:
            arg.accept(self, ctx)

    def visitSend(self, node: Send, ctx: WasmContext) -> str:
        pass

    def visitLiteral(self, node: Literal, ctx: WasmContext):
        pass

    def visitError(self, node: Error, ctx: WasmContext) -> str:
        pass
