from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple, TypeVar

from compiler.element.node import *
from compiler.element.node import Expr, Identifier, MethodCall
from compiler.element.props.analyzer import (
    AliasAnalyzer,
    CopyAnalyzer,
    DropAnalyzer,
    ReadAnalyzer,
    StateAnalyzer,
    WriteAnalyzer,
)
from compiler.element.visitor import Visitor


class Property:
    def __init__(self) -> None:
        self.drop: bool = False
        self.block: bool = False
        self.read: List[str] = []
        self.write: List[str] = []
        self.copy: bool = False

    def check(self):
        self.read = list(set(self.read))
        self.write = list(set(self.write))
        self.read = [i.strip("'") for i in self.read]
        self.write = [i.strip("'") for i in self.write]


class Edge:
    def __init__(self, u: int, v: int, w: Tuple[Expr, Expr] = []) -> None:
        self.u = u
        self.v = v
        self.w = w


class Vertex:
    def __init__(self, node: Node, idx: int, annotation: Optional[str] = None) -> None:
        self.node = node
        self.idx = idx
        if annotation is None:
            self.annotation = self.node.__class__.__name__
        else:
            self.annotation = "[" + annotation + "]" + self.node.__class__.__name__


class FlowGraph:
    def __init__(self) -> None:
        self.vertices: List[Vertex] = []
        self.edges: List[Edge] = []
        self.in_deg: Dict[int, int] = {}

    def link(self, u: int, v: int, w: Tuple[Expr, Expr] = []) -> None:
        self.edges.append(Edge(u, v, w))
        if v in self.in_deg:
            self.in_deg[v] += 1
        else:
            self.in_deg[v] = 1

    def handle_block(self, block: List[Statement], prev: int) -> int:
        for s in block:
            assert isinstance(s, Statement)
            v = Vertex(s, len(self.vertices))
            self.vertices.append(v)
            self.link(prev, v.idx)
            prev = v.idx
        return prev

    def handle_match(self, match: Match, prev: int) -> None:
        expr_v = Vertex(Statement(match.expr), len(self.vertices), "match_expr")
        self.vertices.append(expr_v)
        self.link(prev, expr_v.idx)
        prev = expr_v.idx

        end_points = []
        for (p, s) in match.actions:
            match len(s):
                case 0:
                    head = PASS_NODE  # empty statement, do nothing
                    rest = []
                case 1:
                    head = s[0]
                    rest = []
                case _:
                    head = s[0]
                    rest = s[1:]
            head_v = Vertex(head, len(self.vertices), "match_head")
            self.vertices.append(head_v)
            self.link(prev, head_v.idx, (expr_v.node, p))

            if len(rest) == 0:
                end_points.append(head_v.idx)
            else:
                end_points.append(self.handle_block(rest, head_v.idx))

        merge_v = Vertex(PASS_NODE, len(self.vertices), "match_merge")
        self.vertices.append(merge_v)
        for ep in end_points:
            self.link(ep, merge_v.idx)

        return merge_v.idx

    def build_graph(self, proc: Procedure) -> None:
        start_v = Vertex(START_NODE, 0, "start")
        end_v = Vertex(END_NODE, 1, "end")
        self.vertices.append(start_v)
        self.vertices.append(end_v)
        prev = 0
        for body in proc.body:
            # order matters, since match is a subclass of statement
            if isinstance(body, Match):
                prev = self.handle_match(body, prev)
            elif isinstance(body, Statement):
                prev = self.handle_block([body], prev)
            else:
                raise Exception("build graph encountered: ", body.__class__.__name__)

        self.link(prev, end_v.idx)

    def extract_path(self) -> List[List[Vertex]]:
        q = [0]
        ret: Dict[int, List[List[Vertex]]] = {}
        ret[0] = [[self.vertices[0]]]
        while len(q) > 0:
            u = q.pop()
            for e in self.edges:
                if e.u == u:
                    v = self.vertices[e.v]
                    paths = ret[u].copy()
                    paths = [p + [v] for p in paths]
                    if e.v not in ret:
                        ret[e.v] = paths
                    else:
                        ret[e.v] = ret[e.v] + paths
                    self.in_deg[e.v] -= 1
                    if self.in_deg[e.v] == 0:
                        q.append(e.v)
        return ret[1]

    def analyze(self, proc: Procedure, verbose: bool = False) -> Property:
        self.build_graph(proc)
        paths = self.extract_path()
        rpc_name = f"rpc_{proc.name}"

        if proc.name == "req":
            direction = "NET"
        elif proc.name == "resp":
            direction = "APP"

        report = "Total #Path = " + str(len(paths)) + "\n"

        ret = Property()

        for path in paths:
            report += "\nFor path: \n     "
            report += "->".join([v.annotation for v in path if v != self.vertices[-1]])
            report += "\n\n"
            path_nodes = [v.node for v in path]
            aa = AliasAnalyzer(rpc_name)
            targets = aa.visitBlock(path_nodes, None)
            wa = WriteAnalyzer(targets)
            write = wa.visitBlock(path_nodes, None)
            if write:
                write_fields = wa.target_fields
                report += "Write: "
                for (k, v) in write_fields.items():
                    for vv in v:
                        report += f"{vv} "
                        ret.write.append(vv[0])
                report += "\n"

            ra = ReadAnalyzer(targets)
            read = ra.visitBlock(path_nodes, None)

            if read:
                read_fields = ra.target_fields
                report += "Read: "
                for (k, v) in read_fields.items():
                    for vv in v:
                        report += f"({vv}) "
                        ret.read.append(vv)
                report += "\n"

            da = DropAnalyzer(targets, direction)
            no_drop = da.visitBlock(path_nodes, None)
            random_drop = da.random_included and not no_drop

            if random_drop:
                report += "Random Drop(Block)\n"
                ret.block = True
            else:
                report += "No Drop" if no_drop else "Possible Drop"
                ret.drop = ret.drop or (not no_drop)
                report += "\n"

            ca = CopyAnalyzer(targets)
            copy = ca.visitBlock(path_nodes, None)
            ret.copy = ret.copy or (copy > 1)
            report += f"Copy #={copy}" if copy > 1 else "No Copy"
            report += "\n"

        if verbose:
            print(report)
        return ret
