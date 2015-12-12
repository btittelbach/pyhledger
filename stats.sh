#!/bin/zsh
local CDATE="$(date +"%B%Y")"
local SQLFILE=${0:h}/../Ledgers/members.sqlite
local HJOURNAL=${0:h}/../Ledgers/r3.ledger
echo -n "Membercount ($CDATE): "
sqlite3 $SQLFILE <<< "select count(*) from paying_members_list;"
echo -n "Theoretical monthly membership income ($CATE): "
sqlite3 $SQLFILE <<< "select sum(m_fee) from paying_members_list;"
echo -n "Actual membership income ($CATE): "
hledger -f $HJOURNAL balance acct:"assets:current:membership A/R" date:'this month' amt:'>0' --depth=3 | head -n1
echo -e "\nOutstanding membership fees:\n\t(positive means member has too much money of\n\trealraum, negative means member prepaid fees)"
hledger -f $HJOURNAL balance acct:"assets:current:membership A/R"
echo -e "\nThis months expenses:"
hledger -f $HJOURNAL balance acct:expenses date:'this month'
