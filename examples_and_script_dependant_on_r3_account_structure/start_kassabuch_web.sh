#!/bin/zsh
hledger-web -f ${0:h}/../Ledgers/cash-register/Kassabuch.ledger --cost date:thisyear  "$@"
