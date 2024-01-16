import re
from typing import Optional, Tuple


def find_type_index(list, target_type) -> int:
    """
    Finds the index of the first occurrence of a specified type in a list.

    Parameters:
    list : list
        The list to search through.
    target_type : type
        The type to find in the list.

    Returns:
    int
        The index of the first occurrence of the specified type in the list.
        Returns -1 if the type is not found in the list.
    """
    for i, item in enumerate(list):
        # Check if the current item is an instance of the target_type
        if isinstance(item, target_type):
            return i  # Return the index of the first occurrence
    return -1  # Return -1 if the type is not found


def extract_proto_message_names(
    proto_file: str, target_method_name: str
) -> Tuple[Optional[str], Optional[str]]:
    with open(proto_file, "r") as file:
        proto_content = file.read()

    # Regular expression to find service definitions
    services = re.findall(r"service\s+\w+\s+{[^}]+}", proto_content)
    assert len(services) == 1, "Only one service definition is supported"

    rpcs = re.findall(r"rpc\s+(\w+)\s*\((\w+)\)\s*returns\s*\((\w+)\)", services[0])
    for rpc in rpcs:
        method_name, request_message_name, response_message_name = rpc
        if method_name == target_method_name:
            return request_message_name, response_message_name

    return None, None
