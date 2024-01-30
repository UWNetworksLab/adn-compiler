import os
from pathlib import Path

rpc_name = {
    "geo": "lat",
    "profile": "locale",
    "rate": "out_date",
    "search": "in_date",
    "reservation": "customer_name",
    "ping": "body",
}

elements = [
    "cachestrong",
    "cacheweak" "aclstrong",
    "aclweak",
    "admissioncontrol",
    "logging",
    "mutation",
    "lbstickystrong",
    "lbstickyweak",
    "mutation",
    "ratelimit",
    "circuitbreaker",
    "bandwidthlimit",
    "fault",
]

if __name__ == "__main__":
    element_dir = Path(__file__).parent
    for subdir, dirs, files in os.walk(element_dir):
        for file in files:
            if any(file == e + ".adn" for e in elements):
                file_path = os.path.join(subdir, file)
                adn_content = open(file_path).read()
                if "strong" in file_path:
                    assert "@consistency(strong)" in adn_content, file_path
                elif "weak" in file_path:
                    assert "@consistency(weak)" in adn_content, file_path
                else:
                    assert "@" not in adn_content, file_path
                for sname, fname in rpc_name.items():
                    assert f"'{fname}'" not in adn_content or sname in subdir, file_path
