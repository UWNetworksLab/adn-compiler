import unittest
import subprocess
import sys
from pathlib import Path
import random
import colorlog
import os
import logging

sys.path.append(str(Path(__file__).parent.parent.absolute()))

from tests import TEST_DIR, ROOT_DIR

logger = logging.getLogger()
logger.level = logging.DEBUG
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(
    colorlog.ColoredFormatter(
        "%(log_color)s%(levelname)-7s%(reset)s %(purple)s%(name)-7s%(reset)s - %(message)s"
    )
)
logger.addHandler(stream_handler)
TEST_LOG = logging.getLogger("COMPILER TEST")

# from experiments.utils import *
# from experiments.evaluation import gen_user_spec

element_pool = [
    "cachehackping",
    "fault",
    "ratelimitnormal",
    "lbstickyhackping",
    "loggingping",
    "mutationping",
    "aclping",
    "metricsping",
    "admissioncontrol",
    "encryptping",
    "bandwidthlimit",
    "circuitbreaker",
]

proto_file = "../examples/proto/ping.proto"
method_name = "PingEcho"
backend = "envoy"


class CompilerTestCase(unittest.TestCase):
    def generate_element_code(self, ename: str, p: str):
        command = [
            "python3.10", os.path.join(ROOT_DIR, "compiler/element_compiler_test.py"),
            "--element", ename,
            "--backend", "envoy",
            "--placement", p,
            "--proto", proto_file,
            "--method_name", method_name,
        ]

        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result

    def compile_elements(self):
        command = [
            "bash", os.path.join(ROOT_DIR, "compiler/generated/envoy/build.sh"),
        ]

        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result

    # Dynamically create a test method for each element
    def create_test_method(element):
        def test_method(self):
            position_pool = ["client"] if backend == "envoy" else ["client", "server"]
            for position in position_pool:
                TEST_LOG.info(f"Testing element: {element} at position: {position}")
                
                # Generate element code
                result = self.generate_element_code(element, position)
                self.assertEqual(result.returncode, 0)
                self.assertIn('Code Generation took:', result.stderr)
                
                # Compile elements
                result = self.compile_elements()
                self.assertEqual(result.returncode, 0)
                self.assertIn("Finished release [optimized] target(s) in", result.stderr)
        
        return test_method
    

# Dynamically add test methods to CompilerTestCase
for element in element_pool:
    test_method_name = f"test_{element}_element_compilation"
    test_method = CompilerTestCase.create_test_method(element)
    setattr(CompilerTestCase, test_method_name, test_method)

if __name__ == "__main__":
    unittest.main()


