#!/bin/bash

set -e

# install python dependencies
sudo apt install -y python3-pip
pip install lark pre-commit tomli tomli_w colorlog rich kubernetes yaml

set +e
