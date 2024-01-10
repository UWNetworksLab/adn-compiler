#!/bin/bash

set -e

# install python dependencies
sudo apt install -y python3-pip
pip install lark pre-commit tomli tomli_w colorlog rich kubernetes pyyaml

echo "Installing Rust"
curl https://sh.rustup.rs -sSf | sh -s -- -y

set +e
