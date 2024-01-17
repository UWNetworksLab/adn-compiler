import unittest
import subprocess
import sys
from pathlib import Path
import random
import colorlog
import os
import logging

sys.path.append(str(Path(__file__).parent.parent.absolute()))

from tests import *

logger = logging.getLogger()
logger.level = logging.DEBUG
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(
    colorlog.ColoredFormatter(
        "%(log_color)s%(levelname)-7s%(reset)s %(purple)s%(name)-7s%(reset)s - %(asctime)s - %(message)s",
    )
)
logger.addHandler(stream_handler)
TEST_LOG = logging.getLogger("COMPILER TEST")

element_pool = [
    "cache",
    "fault",
    "ratelimit",
    "lbsticky",
    "logging",
    "mutation",
    "acl",
    "metrics",
    "admissioncontrol",
    "bandwidthlimit",
    "circuitbreaker",
    # "encryptping-decryptping",
]

apps = {
    "ping": {
        "proto_file": os.path.join(proto_base_dir, "ping.proto"),   
        "method_name": "PingEcho",
    },
    "reservation": {
        "proto_file": os.path.join(proto_base_dir, "reservation.proto"),   
        "method_name": "CheckAvailability",
    },
    "search": {
        "proto_file": os.path.join(proto_base_dir, "search.proto"),   
        "method_name": "Nearby",
    },
    "rate": {
        "proto_file": os.path.join(proto_base_dir, "rate.proto"),   
        "method_name": "GetRates",
    },
    "profile": {
        "proto_file": os.path.join(proto_base_dir, "profile.proto"),   
        "method_name": "GetProfiles",
    },
    # "geo": {
    #     "proto_file": os.path.join(proto_base_dir, "geo.proto"),   
    #     "method_name": "Nearby",
    # },
}

backend = "envoy"


class CompilerTestCase(unittest.TestCase):
    def generate_element_code(self, ename: str, p: str, proto_file: str, method_name: str):
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
    def create_test_method(app, element, proto_file, method_name):
        def test_method(self):
            os.environ['ELEMENT_SPEC_BASE_DIR'] = os.path.join(ROOT_DIR, f"experiments/elements/{app}_elements")
            position_pool = ["client"] if backend == "envoy" else ["client", "server"]
            for position in position_pool:
                TEST_LOG.info(f"Testing {app} element: {element} at position: {position}")
                
                # Generate element code
                result = self.generate_element_code(element, position, proto_file, method_name)
                self.assertEqual(result.returncode, 0)
                self.assertIn('Code Generation took:', result.stderr)
                
                # Compile elements
                result = self.compile_elements()
                self.assertEqual(result.returncode, 0)
                self.assertIn("Finished release [optimized] target(s) in", result.stderr)
        
        return test_method
    

# Dynamically add test methods to CompilerTestCase
for app in apps.keys():
    for element in element_pool:
        test_method_name = f"test_{app}_{element}_element_compilation"
        test_method = CompilerTestCase.create_test_method(app, element, apps[app]["proto_file"], apps[app]["method_name"])
        setattr(CompilerTestCase, test_method_name, test_method)

if __name__ == "__main__":
    unittest.main()


