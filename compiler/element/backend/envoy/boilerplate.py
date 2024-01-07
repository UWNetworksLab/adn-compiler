lib_rs = """
use proxy_wasm::traits::{{Context, HttpContext}};
use proxy_wasm::types::{{Action, LogLevel}};
use proxy_wasm::traits::RootContext;
use lazy_static::lazy_static;
use std::collections::HashMap;
use std::sync::Mutex;
use prost::Message;
use chrono::{{DateTime, Utc}};
use std::mem;

pub mod ping {{
    include!(concat!(env!("OUT_DIR"), "/ping_pb.rs"));
}}

{GlobalVariables}

{GlobalFuncDef}


#[no_mangle]
pub fn _start() {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {{ Box::new({FilterName}Root) }});
    proxy_wasm::set_http_context(|context_id, _| -> Box<dyn HttpContext> {{
        Box::new({FilterName}Body {{ context_id, meta_status: "unknown".to_string() }})
    }});
 }}

struct {FilterName}Root;

impl {FilterName}Body {{
    {ProtoFuncDef}
}}

impl Context for {FilterName}Root {{}}

impl RootContext for {FilterName}Root {{
    fn on_vm_start(&mut self, _: usize) -> bool {{
        log::warn!("executing on_vm_start");
        {Init}
        true
    }}
}}

struct {FilterName}Body {{
    #[allow(unused)]
    context_id: u32,
    meta_status: String,
}}

impl Context for {FilterName}Body {{
    fn on_http_call_response(&mut self, _: u32, _: usize, body_size: usize, _: usize) {{
        if let Some(body) = self.get_http_call_response_body(0, body_size) {{
            if let Ok(body_str) = std::str::from_utf8(&body) {{
                {ExternalCallResponse}
            }} else {{
                log::warn!("Response body: [Non-UTF8 data]");
            }}
            self.resume_http_request();
        }}
    }}
}}

impl HttpContext for {FilterName}Body {{
    fn on_http_request_headers(&mut self, _num_of_headers: usize, _end_of_stream: bool) -> Action {{
        log::warn!("executing on_http_request_headers generated");
        // if !end_of_stream {{
        //     return Action::Continue;
        // }}
        {RequestHeaders}
        Action::Continue
    }}

    fn on_http_request_body(&mut self, body_size: usize, _end_of_stream: bool) -> Action {{
        log::warn!("executing on_http_request_body generated");
        // if !end_of_stream {{
        //    return Action::Pause;
        // }}
        {RequestBody}
        Action::Continue
    }}

    fn on_http_response_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {{
        log::warn!("executing on_http_response_headers generated");
        // if !end_of_stream {{
        //    return Action::Continue;
        // }}
        {ResponseHeaders}
        Action::Continue
    }}

    fn on_http_response_body(&mut self, body_size: usize, _end_of_stream: bool) -> Action {{
        log::warn!("executing on_http_response_body generated");
        // if !end_of_stream {{
        //    return Action::Pause;
        // }}
        {ResponseBody}
        Action::Continue
    }}
}}
"""

cargo_toml = """
[package]
name = "{FilterName}"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]
# See more keys and their definitions at https://doc.rust-lang.org/cargo/reference/manifest.html

[build-dependencies]
prost-build = "0.11.1"

[dependencies]
log = "0.4"
prost = "0.11.0"
proxy-wasm = "0.2.0"
lazy_static = "1.4.0"
rand = "0.7.0"
getrandom = {{ version = "0.2", features = ["js"] }}
chrono = {{ version = "0.4", default-features = false, features = ["clock", "std"] }}
"""

build_sh = """
#!/usr/bin/env bash

WORKDIR=`dirname $(realpath $0)`
cd $WORKDIR

cargo build --target=wasm32-wasi --release
cp target/wasm32-wasi/release/{FilterName}.wasm /tmp

"""
