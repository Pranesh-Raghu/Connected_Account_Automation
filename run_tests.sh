#!/bin/bash

# exit on errors
set -e

# check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# activate venv
source venv/bin/activate

# install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# run tests
pytest test_tool_proxy.py -v

# deactivate venv
deactivate
