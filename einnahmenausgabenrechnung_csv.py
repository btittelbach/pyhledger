#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) Bernhard Tittelbach, 2016

import ledger
import os, sys
from collections import defaultdict
from itertools import islice
import csv

hledger_ledgerpath_ = os.path.split(__file__)[0]+'/../Ledgers/r3.ledger'
show_only_accounts_with_these_roots = ["expense", "revenue"]

def sgn(a):
    if a > 0:
        return 1.0
    elif a < 0:
        return -1.0
    else:
        return 0


############## MAIN #####################

depth = 3
#depth = None

#need to convert filter-generator to actual list or we can only read it once
print("getting journal from hledger (apply filters) and parsing it into python objects ...", end="", flush=True)
transactions = list(
                filter(
                    lambda t: len(t.postings) > 0, ledger.parseJournal(
                        ledger.getHLedger(hledger_ledgerpath_, ["--cost"] + sys.argv[1:],depth=None)
                        )
                    )
                )
print("done")

print("depth limiting transactions ...", end="", flush=True)
for t in transactions:
    t.reduceDepth(depth)
print("done")

columnnumber_ = 0
def nextcolumnnumber():
    global columnnumber_
    yield columnnumber_
    columnnumber_+=1
columns_={}

in_out_postingslist_ = []
for t in transactions:
    for p in t.postings:
        if not any([p.account.startswith(ra) for ra in show_only_accounts_with_these_roots]):
            continue
        columns_[p.account] = nextcolumnnumber()
        in_out_postingslist_.append((t,p))

##colwidth[colid]
#columnwidths_ = list([len(colname) for colid, colname in sorted([(v,k) for k,v in columns_.items()])])


#CSV Output
fieldnames = ['tdate', 'tname', "tcode"] + list(columns_.keys())
writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
writer.writeheader()
for t,p in in_out_postingslist_:
    writer.writerow({'tdate': t.getPostingDate(p), 'tname': t.name, "tcode":t.code, p.account:str(p.amount)})



