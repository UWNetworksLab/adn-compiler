import os
import pathlib

from lark import Lark


class ElementParser:
    def __init__(self):
        cwd = pathlib.Path(__file__).parent
        grammar = open(os.path.join(cwd, "element.lark"), "r").read()
        self.lark_parser = Lark(grammar, start="start")

    def parse(self, spec):
        return self.lark_parser.parse(spec)
