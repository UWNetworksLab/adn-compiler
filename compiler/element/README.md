# ADN Element Compiler

Element compiler convert ADN program to an IR. From IR, we can infer the element property (used by graph compiler). The element compiler also generates backend code for each element.

## Usage

```
cd compiler
export PYTHONPATH=$PYTHONPATH:$(pwd):$(dirname $(pwd))
python ir_main.py -e acl -v True -b envoy -p c
```

`v` for verbose, which is `false` by default
`e` for engine_name, refer to ./examples/element for more engine names
`b` for backend_name, which is either `mrpc` or `envoy`
`p` for placement, which is either `c` client or `s` server

## Supported Backends

- [**mRPC**](https://github.com/phoenix-dataplane/phoenix)
- [**Envoy**](https://www.envoyproxy.io/) (via [**Proxy WASM**](https://github.com/proxy-wasm/proxy-wasm-rust-sdk))
- [**gRPC**](https://github.com/grpc/grpc-go) (via [**Interceptors**](https://github.com/grpc-ecosystem/go-grpc-middleware))
    - In progress
