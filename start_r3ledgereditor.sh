#!/bin/zsh

local VENV=${0:h}/venv_r3py
local PYEXE=${0:h}/r3ledgereditor.py
local PYREQ=(nicegui tortoise-orm aiosqlite)
if [[ $VENV -ot $PYEXE ]]; then
  rm -R "$VENV/"
fi
if ! [[ -d $VENV ]]; then
    python -m venv $VENV
    $VENV/bin/pip install $PYREQ
fi
$VENV/bin/python $PYEXE "$@"
