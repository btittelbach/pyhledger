#!/bin/zsh
local STARTOFMONTHTIME=$(mktemp)
trap "rm $STARTOFMONTHTIME" EXIT
touch -d "$(date +%Y-%m-01)" $STARTOFMONTHTIME
[[ ${0:h}/../Ledgers/members.sqlite -nt ${0:h}/../Ledgers/membership-fees.ledger || $STARTOFMONTHTIME -nt ${0:h}/../Ledgers/membership-fees.ledger ]] && ${0:h}/mkmemberfees.sh
hledger-ui -f ${0:h}/../Ledgers/r3.ledger --cost --empty "$@"
