# Graph Compiler Usage

<!-- ## Preparations

Clone the multithreaded version of phoenix repository at `$HOME`.

```bash
git clone https://github.com/kristoff-starling/phoenix --recursive -b multi ~/phoenix
``` -->

## Usage

```bash
# Run the graph compiler on demo.yml to generate element code and deployment scripts for mRPC.
export ELEMENT_SPEC_BASE_DIR="$(dirname $(pwd))/examples/element"
python3 ~/adn-compiler/compiler/main.py --spec ~/adn-compiler/examples/graph/dummy.yml --backend envoy -v

usage: main.py [-h] -s SPEC_PATH [-v][--pseudo_property] [--pseudo_impl] -b {mrpc,envoy}
               [--mrpc_dir MRPC_DIR] [--dry_run] [--no_optimize] [--debug]

options:
  -h, --help            show this help message and exit
  -s SPEC_PATH, --spec_path SPEC_PATH
                        Path to user specification file
  -v, --verbose         If added, request graphs (i.e., element chains) on each edge will be printed on
                        the terminal
  --pseudo_property     If added, use hand-coded properties instead of auto-generated ones
  --pseudo_impl         If added, use hand-coded impl instead of auto-generated ones
  -b {mrpc,envoy}, --backend {mrpc,envoy}
                        Backend name
  --mrpc_dir MRPC_DIR   Path to mrpc repo
  --dry_run             If added, the compilation terminates after optimization (i.e., no backend
                        scriptgen)
  --no_optimize         If added, no optimization will be applied to GraphIR
  --debug               Print debug info
```

The compiler will automatically install elements on all the nodes and
* Generate `attach_all.sh` and `detach_all.sh` in `graph/gen` if the backend is mrpc.
* Generate manifest files if the backend is Envoy. Use `kubectl apply -f <manifest-files>` to run the application


## Element Compiler Usage

Follow these steps if you want to interact with the element compiler directly.

The element compiler convert ADN program to an IR. From IR, we can infer the element property (used by graph compiler). The element compiler also generates backend code for each element.

```bash
cd compiler
export PYTHONPATH=$PYTHONPATH:$(pwd):$(dirname $(pwd))
export ELEMENT_SPEC_BASE_DIR="$(dirname $(pwd))/examples/element"
# The code will be in the `./generated/` directory

❯ python element_compiler_test.py --element acl --backend envoy --placement client --proto ping.proto --method_name PingEcho

usage: element_compiler_test.py [-h] -e ELEMENT [-v] [-d DEPLOY] -p PLACEMENT -r
                                PROTO -m METHOD_NAME -b BACKEND

options:
  -h, --help            show this help message and exit
  -e ELEMENT, --element ELEMENT
                        (Element_name',') *
  -v, --verbose         Print Debug info
  -d DEPLOY, --deploy DEPLOY
                        Deploy to the target directory
  -p PLACEMENT, --placement PLACEMENT
                        Placement of the generated code
  -r PROTO, --proto PROTO
                        Filename of the Protobuf definition (e.g., hello.proto)
  -m METHOD_NAME, --method_name METHOD_NAME
                        Method Name (must be defined in proto)
  -b BACKEND, --backend BACKEND
                        Backend Code Target
```

- `-v` for verbose
- `-e` for element_name, refer to ./examples/element for more element names
- `-b` for backend_name, which is either `mrpc` or `envoy`
- `-p` for placement, which is either `c` client or `s` server

Note:
- The grammar is defined (in BNF format) [**here**](./element/frontend/adn.lark).

## Supported Backends

- [**mRPC**](https://github.com/phoenix-dataplane/phoenix)
- [**Envoy**](https://www.envoyproxy.io/) (via [**Proxy WASM**](https://github.com/proxy-wasm/proxy-wasm-rust-sdk))
- [**gRPC**](https://github.com/grpc/grpc-go) (via [**Interceptors**](https://github.com/grpc-ecosystem/go-grpc-middleware))
    - In progress

<!-- ## Deployment

### Mrpc

Fire up phoenixos and hotel applications.

```bash
# in all worker machines
docker pull kristoffstarling/hotel-service:multi

# in $HOME/phoenix/eval/hotel-bench
# By default, the services are deployed at
# Frontend - h2
# Geo      - h3
# Profile  - h4
# Rate     - h5
# Search   - h6
./start_container
./start_phoenix
# in another terminal
./start_service
```

After running the compiler, use `attach_all.sh` and `detach_all.sh` to attach/detach elements.

```bash
# in compiler/graph/gen
chmod +x attach_all.sh
chmod +x detach_all.sh
./attach_all.sh  # attach all engines
./detach_all.sh  # detach all engines
```

## Limitations

* Container name is hard-coded (only support hotel reservation).
* Service deployment information is currently provided by the user in the specification file (should query the controller instead).
* The graph compiler will generate a globally-unique element name for each element instance, but it requires the element's library name to be identical to the element's specification filename. -->
