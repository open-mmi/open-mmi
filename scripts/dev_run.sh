#!/usr/bin/env bash
set -e

python3 -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install -e .

python3 canbusd/canbusd.py --check
python3 canbusd/canbusd.py
