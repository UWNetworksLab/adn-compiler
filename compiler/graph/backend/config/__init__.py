service_pos_dict = {
    "hotel": {},
    "rpc_echo_local": {
        "rpc_echo_frontend": "localhost",
        "rpc_echo_server": "localhost",
    },
    "rpc_echo_bench": {
        "rpc_echo_frontend": "h2",
        "rpc_echo_server": "h3",
    },
    "ping_pong_bench": {
        "frontend": "h2",
        "ping": "h3",
    },
}

port_dict = {
    "ping_pong_bench": {
        "ping": "8081",
        "pong": "8082",
    }
}

# TODO: automatically detect sid
sids = {
    "hotel": {
        ("Frontend", "Profile", "client"): "2",
        ("Frontend", "Search", "client"): "3",
        ("Frontend", "Search", "server"): "5",
        ("Search", "Geo", "client"): "3",
        ("Search", "Rate", "client"): "4",
    },
    "rpc_echo_local": {
        ("rpc_echo_frontend", "rpc_echo_server", "client"): "1",
        ("rpc_echo_frontend", "rpc_echo_server", "server"): "1",
    },
    "rpc_echo_bench": {
        ("rpc_echo_frontend", "rpc_echo_server", "client"): "1",
        ("rpc_echo_frontend", "rpc_echo_server", "server"): "1",
    },
}
