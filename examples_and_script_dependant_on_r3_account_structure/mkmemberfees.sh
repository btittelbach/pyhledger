#!/bin/zsh
cd ${0:h}
[[ -x ./mkmemberfees && ./mkmemberfees -nt ./mkmemberfees.hs ]] || ghc --make mkmemberfees.hs || exit 1
./mkmemberfees ../Ledgers/members.sqlite >| ../Ledgers/membership-fees.ledger

