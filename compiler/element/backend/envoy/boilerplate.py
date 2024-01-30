lib_rs = """
use proxy_wasm::traits::{{Context, HttpContext}};
use proxy_wasm::types::{{Action, LogLevel}};
use proxy_wasm::traits::RootContext;
use lazy_static::lazy_static;
use std::collections::HashMap;
use serde_json::Value;
use std::time::Duration;
use std::sync::RwLock;
use prost::Message;
use chrono::{{DateTime, Utc}};
use std::mem;

pub mod {ProtoName} {{
    include!(concat!(env!("OUT_DIR"), "/{ProtoName}.rs"));
}}

{GlobalVariables}

{GlobalFuncDef}


#[no_mangle]
pub fn _start() {{
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| -> Box<dyn RootContext> {{ Box::new({FilterName}Root) }});
    proxy_wasm::set_http_context(|context_id, _| -> Box<dyn HttpContext> {{
        Box::new({FilterName}Body {{ context_id, meta_status: "unknown".to_string(), meta_response: 1, method: "unknown".to_string() }})
    }});
 }}

struct {FilterName}Root;

impl {FilterName}Body {{
    {ProtoFuncDef}
}}

impl Context for {FilterName}Root {{}}

impl RootContext for {FilterName}Root {{
    fn on_vm_start(&mut self, _: usize) -> bool {{
        // log::warn!("executing on_vm_start");
        {Init}
        true
    }}

    fn on_tick(&mut self) {{
        {OnTick}
    }}
}}

struct {FilterName}Body {{
    #[allow(unused)]
    context_id: u32,
    meta_status: String,
    meta_response: i32,
    method: String,
}}

impl Context for {FilterName}Body {{
    fn on_http_call_response(&mut self, _: u32, _: usize, body_size: usize, _: usize) {{
        // log::warn!("executing on_http_call_response, self.context_id: {{}}", self.context_id);
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
        // log::warn!("executing on_http_request_headers, self.context_id: {{}}", self.context_id);
        // if !end_of_stream {{
        //     return Action::Continue;
        // }}

        match self.get_http_request_header(":path") {{
            Some(path)  => {{
                self.method = path.rsplit('/').next().unwrap_or("").to_string();
            }}
            _ => log::warn!("No path header found!"),
        }}

        {RequestHeaders}
        Action::Continue
    }}

    fn on_http_request_body(&mut self, body_size: usize, _end_of_stream: bool) -> Action {{
        // log::warn!("executing on_http_request_body, self.context_id: {{}}", self.context_id);
        // if !end_of_stream {{
        //    return Action::Pause;
        // }}
        {RequestBody}
        Action::Continue
    }}

    fn on_http_response_headers(&mut self, _num_headers: usize, _end_of_stream: bool) -> Action {{
        // log::warn!("executing on_http_response_headers, self.context_id: {{}}", self.context_id);
        // if !end_of_stream {{
        //    return Action::Continue;
        // }}
        {ResponseHeaders}
        Action::Continue
    }}

    fn on_http_response_body(&mut self, body_size: usize, _end_of_stream: bool) -> Action {{
        // log::warn!("executing on_http_response_body, self.context_id: {{}}", self.context_id);
        // if !end_of_stream {{
        //    return Action::Pause;
        // }}
        {ResponseBody}
        Action::Continue
    }}
}}
"""

on_tick_template = """
    let read_guard_{state_name} = {state_name}.read().unwrap();

    let mut mset_path_{state_name} = String::from("/MSET/");

    for (key, value) in read_guard_{state_name}.iter() {{
        mset_path_{state_name}.push_str(&format!("{{}}_{state_name}/{{}}/", key, value));
    }}
    mset_path_{state_name} = mset_path_{state_name}.trim_end_matches('/').to_string();

    self.dispatch_http_call(
        "webdis-service-{element_name}",
        vec![
            (":method", "GET"),
            (":path", &mset_path_{state_name}),
            (":authority", "webdis-service-{element_name}"),
        ],
        None,
        vec![],
        Duration::from_secs(5),
    );

    let mut mget_path_{state_name} = String::from("/MGET/");

    for (key, _value) in read_guard_{state_name}.iter() {{
        mget_path_{state_name}.push_str(&format!("{{}}_{state_name}/", key));
    }}
    mget_path_{state_name} = mget_path_{state_name}.trim_end_matches('/').to_string();

    self.dispatch_http_call(
        "webdis-service-{element_name}",
        vec![
            (":method", "GET"),
            (":path", &mget_path_{state_name}),
            (":authority", "webdis-service-{element_name}"),
        ],
        None,
        vec![],
        Duration::from_secs(5),
    );
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
serde_json = "1.0"
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
