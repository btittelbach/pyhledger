#!/bin/zsh

local VENV=${0:h}/venv_r3py
local PYEXE=${0:h}/r3ledgereditor.py
local PYREQ=${0:h}/r3membermanagement.requirements
if [[ $VENV -ot $PYEXE ]]; then
  rm -R "$VENV/"
fi
if ! [[ -d $VENV ]]; then
  if whereis uv; then
      uv venv "${VENV}"
      uv pip install --prefix "${VENV}" -r $PYREQ
  else
      python -m venv $VENV
      $VENV/bin/pip install -r $PYREQ

  fi
fi
$VENV/bin/python $PYEXE "$@"
