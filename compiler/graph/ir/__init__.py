from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Union

from rich import box
from rich.panel import Panel

from compiler.graph.ir.element import AbsElement
from compiler.graph.ir.optimization import chain_optimize


def make_service_rich(name: str) -> Panel:
    """Generate rich.panel objects of a service for visualization.

    Args:
        name: Service name.

    Returns:
        A rich.panel object.
    """
    return Panel(
        name,
        box=box.SQUARE,
        border_style="bold",
        style="bold",
        expand=False,
    )


class GraphIR:
    def __init__(self, client: str, server: str, chain: List[Dict], pair: List[Dict]):
        """Initiate an unoptimized graphir according to the specified elements.

        Args:
            client: Client service name.
            server: Server service name.
            chain: A list of dictionaries including user-specified element configs.
            pair: A list of dictionaries including user-specified paired-element configs.
                  Pair elements are deployed on the client and server sides which cancel
                  out each other.
        """
        self.client = client
        self.server = server
        self.elements: Dict[str, List[AbsElement]] = {
            "req_client": [],
            "req_server": [],
            "res_client": [],
            "res_server": [],
        }
        # determine an initial client-server boundary
        # principle:
        # - valid ("C" goes to client, "S" goes to server)
        # - balanced #element on c/s sides
        c_id, s_id = -1, len(chain)
        for i, element in enumerate(chain):
            if "position" in element and element["position"] == "C":
                c_id = max(c_id, i)
            elif "position" in element and element["position"] == "S":
                s_id = min(s_id, i)
        assert c_id <= s_id, "invalid client/server position requirements"
        c_pt, s_pt = 0, len(chain) - 1
        while c_pt <= s_pt:
            if c_pt <= c_id:
                self.elements["req_client"].append(AbsElement(chain[c_pt]))
                c_pt += 1
            elif s_pt >= s_id:
                self.elements["req_server"].insert(0, AbsElement(chain[s_pt]))
                s_pt -= 1
            elif len(self.elements["req_client"]) <= len(self.elements["req_server"]):
                self.elements["req_client"].append(AbsElement(chain[c_pt]))
                c_pt += 1
            else:
                self.elements["req_server"].insert(0, AbsElement(chain[s_pt]))
                s_pt -= 1
        # The initial response graph is identical to the request graph, except for
        # the required positions of element pairs
        self.elements["res_client"] = deepcopy(self.elements["req_client"])
        self.elements["res_server"] = deepcopy(self.elements["req_server"])
        # add element pairs to c/s sides
        for pdict in pair:
            edict1 = {
                "name": pdict["name1"],
                "config": pdict["config1"] if "config1" in pdict else [],
                "position": "C",
                "proto": pdict["proto"],
                "method": pdict["method"],
            }
            edict2 = {
                "name": pdict["name2"],
                "config": pdict["config2"] if "config2" in pdict else [],
                "position": "S",
                "proto": pdict["proto"],
                "method": pdict["method"],
            }
            self.elements["req_client"].append(
                AbsElement(edict1, partner=pdict["name2"])
            )
            self.elements["req_server"].insert(
                0, AbsElement(edict2, partner=pdict["name1"])
            )
            edict1["position"], edict2["position"] = (
                edict2["position"],
                edict1["position"],
            )
            self.elements["res_client"].append(AbsElement(edict2))
            self.elements["res_server"].insert(0, AbsElement(edict1))

    @property
    def name(self) -> str:
        return f"{self.client}->{self.server}"

    def __str__(self):
        s = f"{self.client}->{self.server} request GraphIR: "
        s += " -> ".join(map(str, self.elements["req_client"]))
        s += " (network) "
        s += " -> ".join(map(str, self.elements["req_server"]))
        return s

    def to_rich(self) -> List[Union[Panel, str]]:
        """Generate rich.panel objects for visualization.

        Returns:
            A list of rich.panel objects/strings.
        """
        panel_list = [make_service_rich(self.client), "\n~\n"]
        for i, e in enumerate(self.elements["req_client"]):
            if i != 0:
                panel_list.append("\n→\n")
            panel_list.append(e.to_rich("client"))
        panel_list.append("\n(network)\n")
        for i, e in enumerate(self.elements["req_server"]):
            if i != 0:
                panel_list.append("\n→\n")
            panel_list.append(e.to_rich("server"))
        panel_list.append("\n~\n")
        panel_list.append(make_service_rich(self.server))
        return panel_list

    def optimize(self):
        """Run optimization algorithm on the graphir."""
        self.elements["req_client"], self.elements["req_server"] = chain_optimize(
            self.elements["req_client"]
            + [AbsElement("NETWORK")]
            + self.elements["req_server"],
            "request",
        )
        # TODO: currently, we don't consider optimization for the response chain,
        # so the response chain is copied from request chain.
        self.elements["res_client"] = deepcopy(self.elements["req_client"])
        self.elements["res_server"] = deepcopy(self.elements["res_server"])
