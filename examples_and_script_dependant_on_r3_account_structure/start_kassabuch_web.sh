#!/bin/zsh
hledger-web --ignore-assertions -f ${0:h}/../Ledgers/cash-register/Kassabuch.ledger --cost date:thisyear  "$@"
