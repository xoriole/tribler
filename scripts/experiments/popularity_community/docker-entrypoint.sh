#!/usr/bin/env bash

THIS_SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]:-$0}"; )" &> /dev/null && pwd 2> /dev/null; )";
cd $THIS_SCRIPT_DIR
pip3 install -r ../requirements.txt

cd "../../../"
ROOT_DIR=`pwd`
SCRIPT_DIR="$ROOT_DIR/scripts"
SRC_DIR="$ROOT_DIR/src"

export PYTHONPATH=$SRC_DIR:$ROOT_DIR
python3 $SCRIPT_DIR/experiments/popularity_community/runner.py