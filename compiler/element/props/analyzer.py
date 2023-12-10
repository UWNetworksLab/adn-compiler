from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple, TypeVar

from compiler.element.logger import ELEMENT_LOG as LOG
from compiler.element.node import *
from compiler.element.node import Expr, Identifier, Internal, MethodCall, Procedure
from compiler.element.visitor import Visitor


class StateAnalyzer(Visitor):
    def __init__():
        pass

    def visitNode(self, ctx):
        raise Exception("Should be unreachable!")

    def visitInternal(self, node: Internal, ctx) -> int:
        return len(node.internal) > 0


class CopyAnalyzer(Visitor):
    def __init__(self, targets: List[str]):
        self.targets = targets
        self.send_num = 0

    def visitBlock(self, node: List[Statement], ctx) -> int:
        for s in node:
            s.accept(self, ctx)
        return self.send_num

    def visitNode(self, node: Node, ctx):
        if node == START_NODE or node == END_NODE or node == PASS_NODE:
            return
        LOG.error(node.__class__.__name__, "should be visited in copy analyzer")
        raise Exception("Unreachable!")

    def visitProgram(self, node: Program, ctx):
        raise Exception("Unreachable!")

    def visitInternal(self, node: Internal, ctx):
        raise Exception("Unreachable!")

    def visitProcedure(self, node: Procedure, ctx):
        raise Exception("Unreachable!")

    def visitStatement(self, node: Statement, ctx):
        if node.stmt == None:
            return
        else:
            return node.stmt.accept(self, ctx)

    def visitMatch(self, node: Match, ctx):
        for (p, s) in node.actions:
            for st in s:
                st.accept(self, ctx)

    def visitAssign(self, node: Assign, ctx):
        pass

    def visitPattern(self, node: Pattern, ctx):
        pass

    def visitExpr(self, node: Expr, ctx):
        node.lhs.accept(self, ctx)
        node.rhs.accept(self, ctx)

    def visitIdentifier(self, node: Identifier, ctx) -> bool:
        pass

    def visitType(self, node: Type, ctx):
        pass

    def visitFuncCall(self, node: FuncCall, ctx):
        node.name.accept(self, ctx)
        for a in node.args:
            a.accept(self, ctx)

    def visitMethodCall(self, node: MethodCall, ctx):
        pass

    def visitSend(self, node: Send, ctx) -> bool:
        send_target = node.msg.accept(ExprResolver(), ctx)
        if send_target in self.targets:
            self.send_num += 1

    def visitLiteral(self, node: Literal, ctx) -> bool:
        return False

    def visitError(self, node: Error, ctx) -> bool:
        return False


class WriteAnalyzer(Visitor):
    def __init__(self, targets: List[str]):
        self.targets = targets
        self.target_fields: Dict[str, List[Tuple(str, str)]] = {}
        for t in targets:
            self.target_fields[t] = []

    def visitBlock(self, node: List[Statement], ctx) -> bool:
        ret = False
        for s in node:
            ret = s.accept(self, ctx) or ret
        return ret

    def visitNode(self, node: Node, ctx):
        if node == START_NODE or node == END_NODE or node == PASS_NODE:
            return
        LOG.error(node.__class__.__name__, "should be visited in write analyzer")
        raise Exception("Unreachable!")

    def visitProgram(self, node: Program, ctx):
        raise Exception("Unreachable!")

    def visitInternal(self, node: Internal, ctx):
        raise Exception("Unreachable!")

    def visitProcedure(self, node: Procedure, ctx):
        raise Exception("Unreachable!")

    def visitStatement(self, node: Statement, ctx):
        if node.stmt == None:
            return
        else:
            return node.stmt.accept(self, ctx)

    def visitMatch(self, node: Match, ctx) -> bool:
        ret = False
        for (p, s) in node.actions:
            ret = p.accept(self, ctx) or ret
            for st in s:
                ret = st.accept(self, ctx) or ret
        return ret

    def visitAssign(self, node: Assign, ctx) -> bool:
        return node.left.accept(self, ctx) or node.right.accept(self, ctx)

    def visitPattern(self, node: Pattern, ctx) -> bool:
        return node.value.accept(self, ctx)

    def visitExpr(self, node: Expr, ctx) -> bool:
        return node.lhs.accept(self, ctx) or node.rhs.accept(self, ctx)

    def visitIdentifier(self, node: Identifier, ctx) -> bool:
        return False

    def visitType(self, node: Type, ctx) -> bool:
        return False

    def visitFuncCall(self, node: FuncCall, ctx) -> bool:
        ret = node.name.accept(self, ctx)
        for a in node.args:
            ret = a.accept(self, ctx) or ret
        return ret

    def visitMethodCall(self, node: MethodCall, ctx) -> bool:
        assert isinstance(node.obj, Identifier)
        if node.obj.name in self.targets and node.method.name == "SET":
            er = ExprResolver()
            assert len(node.args) == 2
            fields = [i.accept(er, None) for i in node.args]
            self.target_fields[node.obj.name] += [(fields[0], fields[1])]
            return True
        ret = False
        for a in node.args:
            if a != None:
                ret = a.accept(self, ctx) or ret
        return ret

    def visitSend(self, node: Send, ctx) -> bool:
        return node.msg.accept(self, ctx)

    def visitLiteral(self, node: Literal, ctx) -> bool:
        return False

    def visitError(self, node: Error, ctx) -> bool:
        return False


class ReadAnalyzer(Visitor):
    def __init__(self, targets: List[str]):
        self.targets = targets
        self.target_fields: Dict[str, List[str]] = {}
        for t in targets:
            self.target_fields[t] = []

    def visitBlock(self, node: List[Statement], ctx) -> bool:
        ret = False
        for s in node:
            ret = s.accept(self, ctx) or ret
        return ret

    def visitNode(self, node: Node, ctx):
        if node == START_NODE or node == END_NODE or node == PASS_NODE:
            return
        LOG.error(node.__class__.__name__, "should be visited in read analyzer")
        raise Exception("Unreachable!")

    def visitProgram(self, node: Program, ctx):
        raise Exception("Unreachable!")

    def visitInternal(self, node: Internal, ctx):
        raise Exception("Unreachable!")

    def visitProcedure(self, node: Procedure, ctx):
        raise Exception("Unreachable!")

    def visitStatement(self, node: Statement, ctx):
        if node.stmt == None:
            return
        else:
            return node.stmt.accept(self, ctx)

    def visitMatch(self, node: Match, ctx) -> bool:
        ret = False
        for (p, s) in node.actions:
            ret = p.accept(self, ctx) or ret
            for st in s:
                ret = st.accept(self, ctx) or ret
        return ret

    def visitAssign(self, node: Assign, ctx) -> bool:
        return node.left.accept(self, ctx) or node.right.accept(self, ctx)

    def visitPattern(self, node: Pattern, ctx) -> bool:
        return node.value.accept(self, ctx)

    def visitExpr(self, node: Expr, ctx) -> bool:
        return node.lhs.accept(self, ctx) or node.rhs.accept(self, ctx)

    def visitIdentifier(self, node: Identifier, ctx) -> bool:
        return False

    def visitType(self, node: Type, ctx) -> bool:
        return False

    def visitFuncCall(self, node: FuncCall, ctx) -> bool:
        ret = node.name.accept(self, ctx)
        for a in node.args:
            ret = a.accept(self, ctx) or ret
        return ret

    def visitMethodCall(self, node: MethodCall, ctx) -> bool:
        if isinstance(node.obj, Identifier):
            if node.obj.name in self.targets and node.method.name == "GET":
                er = ExprResolver()
                fields = [i.accept(er, None) for i in node.args]
                self.target_fields[node.obj.name] += fields
                return True
        else:
            raise NotADirectoryError
        ret = False
        for a in node.args:
            if a != None:
                ret = a.accept(self, ctx) or ret
        return ret

    def visitSend(self, node: Send, ctx) -> bool:
        return node.msg.accept(self, ctx)

    def visitLiteral(self, node: Literal, ctx) -> bool:
        return False

    def visitError(self, node: Error, ctx) -> bool:
        return False


class DropAnalyzer(Visitor):
    def __init__(self, targets: List[str], direction: str):
        self.direction = direction
        self.targets = targets
        self.target_fields: Dict[str, List[str]] = {}
        self.random_included = False
        for t in targets:
            self.target_fields[t] = []

    def visitBlock(self, node: List[Statement], ctx) -> bool:
        ret = False
        for s in node:
            ret = s.accept(self, ctx) or ret
        return ret

    def visitNode(self, node: Node, ctx):
        if node == START_NODE or node == END_NODE or node == PASS_NODE:
            return
        LOG.error("Node", node.__class__.__name__, "should be visited in drop analyzer")
        raise Exception("Unreachable!")

    def visitProgram(self, node: Program, ctx):
        raise Exception("Unreachable!")

    def visitInternal(self, node: Internal, ctx):
        raise Exception("Unreachable!")

    def visitProcedure(self, node: Procedure, ctx):
        raise Exception("Unreachable!")

    def visitStatement(self, node: Statement, ctx):
        if node.stmt == None:
            return
        else:
            return node.stmt.accept(self, ctx)

    def visitMatch(self, node: Match, ctx) -> bool:
        for a in node.actions:
            for st in a[1]:
                if isinstance(st, Send):
                    if isinstance(st.msg, Error):
                        return True
        return False
        # todo! fixme
        raise Exception("Unreachable! Match should not appear in drop analyzer")

    def visitAssign(self, node: Assign, ctx) -> bool:
        return False

    def visitPattern(self, node: Pattern, ctx) -> bool:
        return False

    def visitExpr(self, node: Expr, ctx) -> bool:
        return node.lhs.accept(self, ctx) or node.rhs.accept(self, ctx)

    def visitIdentifier(self, node: Identifier, ctx) -> bool:
        return False

    def visitType(self, node: Type, ctx) -> bool:
        return False

    def visitFuncCall(self, node: FuncCall, ctx) -> bool:
        if node.name.name == "randomf" or node.name.name == "randomi":
            self.random_included = True
        return False

    def visitMethodCall(self, node: MethodCall, ctx) -> bool:
        return False

    def visitSend(self, node: Send, ctx) -> bool:
        if node.direction == self.direction:
            name = node.msg.accept(ExprResolver(), ctx)
            return name in self.targets
        else:
            return False

    def visitLiteral(self, node: Literal, ctx) -> bool:
        return False

    def visitError(self, node: Error, ctx) -> bool:
        return False


class AliasAnalyzer(Visitor):
    def __init__(self, target: str):
        self.targets: List[str] = [target]
        self.target_fields: Dict[str, List[str]] = {}
        for t in self.targets:
            self.target_fields[t] = []

    def visitBlock(self, node: List[Statement], ctx) -> List[str]:
        for s in node:
            s.accept(self, ctx)
        return self.targets

    def visitNode(self, node: Node, ctx):
        if node == START_NODE or node == END_NODE or node == PASS_NODE:
            return
        LOG.error(
            "Node", node.__class__.__name__, "should be visited in alias analyzer"
        )
        raise Exception("Unreachable!")

    def visitProgram(self, node: Program, ctx):
        raise Exception("Unreachable!")

    def visitInternal(self, node: Internal, ctx):
        raise Exception("Unreachable!")

    def visitProcedure(self, node: Procedure, ctx):
        raise Exception("Unreachable!")

    def visitStatement(self, node: Statement, ctx):
        if node.stmt == None:
            return
        else:
            return node.stmt.accept(self, ctx)

    def visitMatch(self, node: Match, ctx):
        for (p, s) in node.actions:
            p.accept(self, ctx)
            for st in s:
                st.accept(self, ctx)

    def visitAssign(self, node: Assign, ctx):
        name = node.left.name
        is_target = node.right.accept(self, ctx)
        if is_target == True:
            self.targets.append(name)
            self.target_fields[name] = []

    def visitPattern(self, node: Pattern, ctx) -> bool:
        return node.value.accept(self, ctx)

    def visitExpr(self, node: Expr, ctx) -> bool:
        if isinstance(node.lhs, Identifier) and node.lhs.name in self.targets:
            return True
        if isinstance(node.rhs, Identifier) and node.rhs.name in self.targets:
            return True
        return node.lhs.accept(self, ctx) or node.rhs.accept(self, ctx)

    def visitIdentifier(self, node: Identifier, ctx) -> str:
        return node.name in self.targets

    def visitType(self, node: Type, ctx) -> bool:
        return False

    def visitFuncCall(self, node: FuncCall, ctx) -> bool:
        ret = node.name.accept(self, ctx)
        for a in node.args:
            ret = a.accept(self, ctx) or ret
        return ret

    def visitMethodCall(self, node: MethodCall, ctx) -> bool:
        assert isinstance(node.obj, Identifier)
        if node.obj.name in self.targets:
            if node.method.name == "GET":
                return True
        return False

    def visitSend(self, node: Send, ctx) -> bool:
        return False

    def visitLiteral(self, node: Literal, ctx) -> bool:
        return False

    def visitError(self, node: Error, ctx) -> bool:
        return False


class ExprResolver(Visitor):
    def __init__(self) -> None:
        pass

    def visitNode(self, node: Node, ctx) -> str:
        LOG.error(node.__class__.__name__, "should be visited in expr resolver ")
        raise Exception("Unreachable!")

    def visitLiteral(self, node: Literal, ctx) -> str:
        return node.value

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
