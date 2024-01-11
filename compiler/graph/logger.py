import logging

import colorlog

ELEMETN_LOG = logging.getLogger("Element Compiler")
GRAPH_LOG = logging.getLogger("Graph Compiler")
GRAPH_BACKEND_LOG = logging.getLogger("Graph Compiler Backend")
EVAL_LOG = logging.getLogger("Evaluation")
TEST_LOG = logging.getLogger("TEST")

loggers = [ELEMETN_LOG, GRAPH_LOG, GRAPH_BACKEND_LOG, EVAL_LOG]


def init_logging(dbg: bool):
    level = logging.DEBUG if dbg else logging.INFO
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s%(levelname)-7s%(reset)s %(purple)s%(name)-7s%(reset)s - %(message)s"
        )
    )
    for logger in loggers:
        logger.setLevel(level)
        logger.addHandler(handler)
