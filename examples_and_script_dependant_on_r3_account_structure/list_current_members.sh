#!/bin/zsh
outfile="${0:h}/../$(date "+%Y-%m-%d_paying_members.csv")"
sqlite3 -csv ${0:h}/../Ledgers/members.sqlite <<< "select * from paying_members_list;" | tee $outfile
echo > /dev/stderr
echo "saved to ${outfile:A}" > /dev/stderr
