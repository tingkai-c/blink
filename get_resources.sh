#!/bin/bash
set -euo pipefail

(
    cd Resources/vim
    rm -rf runtime runtime.zip
    curl -L https://github.com/blinksh/vim/releases/download/v9.1.0187/runtime.zip > runtime.zip
    unzip -o runtime.zip
    cp -rf runtime/* ./
    rm -rf runtime runtime.zip
)

echo "done"
