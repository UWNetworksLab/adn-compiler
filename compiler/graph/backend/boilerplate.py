# Mrpc templates

attach_mrpc = """addon_engine = "{current}Engine"
tx_channels_replacements = [
    ["{tx_prev}Engine", "{current}Engine", 0, 0],
    ["{current}Engine", "{tx_nxt}Engine", 0, 0],
]
rx_channels_replacements = [
    ["{rx_prev}Engine", "{current}Engine", 0, 0],
    ["{current}Engine", "{rx_nxt}Engine", 0, 0],
]
group = {group}
op = "attach"
config_string = '''
{config}
'''
"""

detach_mrpc = """addon_engine = "{current}Engine"
tx_channels_replacements = [["{tx_prev}Engine", "{tx_nxt}Engine", 0, 0]]
rx_channels_replacements = [["{rx_prev}Engine", "{rx_nxt}Engine", 0, 0]]
op = "detach"
"""

addon_loader = """
[[addons]]
name = "{name}"
lib_path = "plugins/libphoenix_{rlib}.rlib"
config_string = \'\'\'
{config}
\'\'\'
"""

# ==============================================================================

# Envoy templates

attach_yml = """apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: {metadata_name}
spec:
  workloadSelector:
    labels:
      app: {service}
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: {bound}
      listener:
        portNumber: {port}
        filterChain:
          filter:
            name: "envoy.filters.network.http_connection_manager"
            subFilter:
              name: "envoy.filters.http.router"
    patch:
      operation: INSERT_BEFORE
      value:
        name: envoy.filters.http.wasm
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm
          config:
            name: {name}
            root_id: {name}
            vm_config:
              vm_id: {vmid}
              runtime: envoy.wasm.runtime.v8
              code:
                local:
                  filename: {filename}
              allow_precompiled: false
"""
