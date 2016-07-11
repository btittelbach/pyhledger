#!/bin/zsh
local STARTOFMONTHTIME=$(mktemp)
trap "rm $STARTOFMONTHTIME" EXIT
touch -d "$(date +%Y-%m-01)" $STARTOFMONTHTIME
[[ ${0:h}/../Ledgers/members.sqlite -nt ${0:h}/../Ledgers/membership-fees.ledger || $STARTOFMONTHTIME -nt ${0:h}/../Ledgers/membership-fees.ledger ]] && ${0:h}/mkmemberfees.sh

local CDATE="$(date +"%B%Y")"
local SQLFILE=${0:h}/../Ledgers/members.sqlite
local HJOURNAL=${0:h}/../Ledgers/r3.ledger
echo -n "Membercount ($CDATE): "
sqlite3 $SQLFILE <<< "select count(*) from paying_members_list;"
echo -n "Theoretical monthly membership income ($CATE): "
sqlite3 $SQLFILE <<< "select sum(m_fee) from paying_members_list;"
echo -n "Actual membership income ($CATE): "
hledger -f $HJOURNAL balance acct:"assets:current:membership A/R" date:'this month' amt:'>0' --depth=3 --ignore-assertions | head -n1
echo -e "\nOutstanding membership fees:\n\t(positive means member has too much money of\n\trealraum, negative means member prepaid fees)"
hledger -f $HJOURNAL balance acct:"assets:current:membership A/R" --ignore-assertions
echo -e "\nLast month's expenses:"
hledger -f $HJOURNAL balance acct:expenses date:'last month' --ignore-assertions
echo -e "\nThis month's expenses:"
hledger -f $HJOURNAL balance acct:expenses date:'this month' --ignore-assertions
local ABALANCE="$(hledger -f $HJOURNAL register acct:"assets:current:checking-r3" | tail -n 1)"
echo "\nRaika account balance: ${ABALANCE[(w)-2,-1]} (as of ${ABALANCE[(w)1]})"
echo -e "\n2015 Umsatz:"
hledger -f $HJOURNAL balance acct:assets:current:checking-r3 date:2015 amt:">0" --ignore-assertions | grep  -P "[0-9,.]+\s\w+\s+\w+"
# The "Gewinn" called transaction that arrive in register are actually revenue
hledger -f $HJOURNAL balance acct:assets:current:cash:register date:2015 desc:Gewinn --ignore-assertions | grep  -P "[0-9,.]+\s\w+\s+\w+"
echo -e "\n2016 Umsatz:"
hledger -f $HJOURNAL balance acct:assets:current:checking-r3 date:2016 amt:">0" --ignore-assertions | grep  -P "[0-9,.]+\s\w+\s+\w+"
# The "Gewinn" called transaction that arrive in register are actually revenue
hledger -f $HJOURNAL balance acct:assets:current:cash:register date:2016 desc:Gewinn --ignore-assertions | grep  -P "[0-9,.]+\s\w+\s+\w+"
