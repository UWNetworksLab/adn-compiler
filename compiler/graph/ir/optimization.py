from copy import deepcopy
from itertools import permutations
from pprint import pprint
from typing import List, Tuple

from compiler.graph.ir.element import AbsElement


def init_dependency(chain: List[AbsElement], path: str):
    for element in chain:
        if element.has_prop(path, "record"):
            element.add_prop(path, "record", ["droptrace", "blocktrace", "copytrace"])
        if element.has_prop(path, "drop"):
            element.add_prop(path, "write", "droptrace")
        if element.has_prop(path, "block"):
            element.add_prop(path, "write", "blocktrace")
        if element.has_prop(path, "copy"):
            element.add_prop(path, "write", "copytrace")


def gen_dependency(chain: List[AbsElement], path: str):
    fields = {"droptrace", "blocktrace", "copytrace"}
    for element in chain:
        for f in (
            element.get_prop(path, "read")
            + element.get_prop(path, "write")
            + element.get_prop(path, "record")
        ):
            fields.add(f)
    writer_table = {f: ["INPUT"] for f in fields}
    dep = {"read": dict(), "record": dict()}
    for element in chain:
        rfields, wfields, rec_fields = (
            element.get_prop(path, "read"),
            element.get_prop(path, "write"),
            element.get_prop(path, "record"),
        )
        assert len(set(rfields)) == len(rfields), "duplicate fields"
        assert len(set(wfields)) == len(wfields), "duplicate fields"
        assert len(set(rec_fields)) == len(rec_fields), "duplicate fields"
        if rfields == "*":
            rfields = list(fields)
        if wfields == "*":
            wfields = list(fields)
        for f in rfields:
            dep["read"][(element.lib_name, f)] = deepcopy(writer_table[f])
        for f in rec_fields:
            dep["record"][(element.lib_name, f)] = deepcopy(writer_table[f])
        for f in wfields:
            if element.partner in writer_table[f]:
                writer_table[f].remove(element.partner)
            else:
                writer_table[f].append(element.lib_name)
    for f in fields:
        dep["read"][("OUTPUT", f)] = deepcopy(writer_table[f])
    return dep


def position_valid(chain: List[AbsElement]) -> bool:
    server_side = False
    for element in chain:
        if element.position == "N":
            server_side = True
        if element.position == "S" and not server_side:
            return False
        if element.position == "C" and server_side:
            return False
    return True


def equivalent(
    chain: List[AbsElement], new_chain: List[AbsElement], path: str, opt_level: str
) -> bool:
    if not position_valid(new_chain):
        return False
    if opt_level == "ignore":
        return True
    dep, new_dep = gen_dependency(chain, path), gen_dependency(new_chain, path)
    if opt_level == "weak":
        return dep["read"] == new_dep["read"]
    elif opt_level == "strong":
        return dep == new_dep
    else:
        raise ValueError(f"Unexpected optimization level {opt_level}")
    # return dep == new_dep


class OptimizedLabel(Exception):
    pass


def reorder(chain: List[AbsElement], path: str, opt_level: str) -> List[AbsElement]:
    # preparation: add some properties for analysis
    init_dependency(chain, path)
    # reorder
    optimized = True
    while optimized:
        optimized = False
        drop_list, non_drop_list, copy_list, non_copy_list = [], [], [], []
        for i, element in enumerate(chain):
            if element.has_prop(path, "drop", "block"):
                drop_list.append(i)
            else:
                non_drop_list.append(i)
            if element.has_prop(path, "copy"):
                copy_list.append(i)
            else:
                non_copy_list.append(i)
        try:
            for i in non_drop_list:
                for j in drop_list[::-1]:
                    if i > j:
                        break
                    # strategy 1: move drop element at the front of non-drop ones
                    new_chain = chain[:i] + [chain[j]] + chain[i:j] + chain[j + 1 :]
                    if equivalent(chain, new_chain, path, opt_level):
                        chain = new_chain
                        optimized = True
                        raise OptimizedLabel()
                    # strategy 2: move non-drop element behind drop ones
                    new_chain = (
                        chain[:i] + chain[i + 1 : j + 1] + [chain[i]] + chain[j + 1 :]
                    )
                    if equivalent(chain, new_chain, path, opt_level):
                        chain = new_chain
                        optimized = True
                        raise OptimizedLabel()
            for i in copy_list:
                for j in non_copy_list[::-1]:
                    if i > j:
                        break
                    # strategy 1: move copy element behind non-copy ones
                    new_chain = (
                        chain[:i] + chain[i + 1 : j + 1] + [chain[i]] + chain[j + 1 :]
                    )
                    if equivalent(chain, new_chain, path, opt_level):
                        chain = new_chain
                        optimized = True
                        raise OptimizedLabel()
                    # strategy 2: move non-copy element at the front of copy ones
                    new_chain = chain[:i] + [chain[j]] + chain[i:j] + chain[j + 1 :]
                    if equivalent(chain, new_chain, path, opt_level):
                        chain = new_chain
                        optimized = True
                        raise OptimizedLabel()
        except OptimizedLabel:
            pass
    return chain


def gather(chain: List[AbsElement]) -> List[AbsElement]:
    last_client, first_server, np = -1, len(chain), 0
    client_strong, cs_strong, server_strong = False, False, False
    for i, element in enumerate(chain):
        if element.position == "C":
            last_client = max(last_client, i)
            if element.prop["state"]["consistency"] == "strong":
                client_strong = True
        elif element.position == "S":
            first_server = min(first_server, i)
            if element.prop["state"]["consistency"] == "strong":
                server_strong = True
        elif element.position == "N":
            np = i
        else:
            if element.prop["state"]["consistency"] == "strong":
                cs_strong = True
    if first_server == len(chain):
        # migrate all elements to the client side
        chain = chain[:np] + chain[np + 1 :] + [chain[np]]
    elif last_client == -1:
        # migrate all elements to the server side
        chain = [chain[np]] + chain[:np] + chain[np + 1 :]
    else:
        if server_strong and not client_strong and cs_strong:
            # migrate all C/S elements to the server side
            chain = (
                chain[: last_client + 1]
                + [chain[np]]
                + chain[last_client + 1 : np]
                + chain[np + 1 :]
            )
        else:
            # migrate all C/S elements to the client side
            chain = (
                chain[:np]
                + chain[np + 1 : first_server]
                + [chain[np]]
                + chain[first_server:]
            )
    return chain


def split_and_consolidate(
    chain: List[AbsElement],
) -> Tuple[List[AbsElement], List[AbsElement]]:
    network_pos = 0
    while network_pos < len(chain) and chain[network_pos].position != "N":
        network_pos += 1
    client_chain, server_chain = chain[:network_pos], chain[network_pos + 1 :]

    for i in range(1, len(client_chain)):
        client_chain[0].fuse(client_chain[i])
    for i in range(1, len(server_chain)):
        server_chain[0].fuse(server_chain[i])
    client_chain, server_chain = client_chain[:1], server_chain[:1]

    return client_chain, server_chain


def chain_optimize(
    chain: List[AbsElement],
    path: str,
    opt_level: str,
) -> Tuple[List[AbsElement], List[AbsElement]]:
    """Optimize an element chain

    Args:
        chain: A list of AbsElement
        path: "request" or "response"
        pseudo_property: if true, use hand-coded properties for analysis

    Returns:
        client chain and server chain
    """
    # Step 1: Reorder + Migration
    chain = reorder(chain, path, opt_level)

    # Step 2: Further migration - more opportunities for state consolidation
    # and turning off sidecars
    chain = gather(chain)

    return split_and_consolidate(chain)


def cost(chain: List[AbsElement], path: str) -> float:
    # Parameters
    # TODO: different parameters for different backends
    e = 1.0
    n = 1.0
    d = 0.1
    s = 5.0
    r = 5.0

    cost = 0

    workload = 1.0
    for element in chain:
        cost += workload * (n if element.position == "N" else e)
        if element.has_prop(path, "drop", "block"):
            workload *= 1 - d

    network_pos = -1
    for i in range(len(chain)):
        if chain[i].position == "N":
            network_pos = i
    assert network_pos != -1, "network element not found"
    client_chain, server_chain = chain[:network_pos], chain[network_pos + 1 :]

    for element in client_chain:
        if (
            element.prop["state"]["consistency"] == "strong"
            and element.prop["state"]["state_dependence"] != "client_replica"
        ):
            cost += s
            break
    for element in server_chain:
        if (
            element.prop["state"]["consistency"] == "strong"
            and element.prop["state"]["state_dependence"] != "server_replica"
        ):
            cost += s
            break

    if len(client_chain) > 0:
        cost += r
    if len(server_chain) > 0:
        cost += r

    return cost


def cost_chain_optimize(chain: List[AbsElement], path: str, opt_level: str):
    min_cost = cost(chain, path)
    init_dependency(chain, path)
    for new_chain in permutations(chain):
        if position_valid(new_chain) and equivalent(chain, new_chain, path, opt_level):
            new_cost = cost(new_chain, path)
            if new_cost < min_cost:
                chain = new_chain
                min_cost = new_cost
    return split_and_consolidate(chain)
