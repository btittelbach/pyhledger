#!/bin/zsh
local STARTOFMONTHTIME=$(mktemp)
trap "rm $STARTOFMONTHTIME" EXIT
touch -d "$(date +%Y-%m-01)" $STARTOFMONTHTIME
[[ Ledgers/members.sqlite -nt Ledgers/membership-fees.ledger || $STARTOFMONTHTIME -nt Ledgers/membership-fees.ledger ]] && ${0:h}/mkmemberfees.sh
hledger-web -f ${0:h}/../Ledgers/r3.ledger --server
