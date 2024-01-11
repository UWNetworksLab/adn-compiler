from compiler.element.frontend.parser import ElementParser
from compiler.element.frontend.transformer import ElementTransformer
from compiler.element.node import Program


class ElementCompiler:
    def __init__(self):
        self.parser = ElementParser()
        self.transformer = ElementTransformer()

    def parse_and_transform(self, spec: str) -> Program:
        # Step 1: Generate a parse tree based on our grammar
        ast = self.parser.parse(spec)
        # print(ast.pretty())

        # Step 2: Transforme traverses the parse tree and applies transformation to its nodes.
        ir = self.transformer.transform(ast)
        return ir
