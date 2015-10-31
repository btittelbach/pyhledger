#!/usr/bin/python3
# -*- coding: utf-8 -*-

import re
import sys, os, io
import csv
import sqlite3 as lite
import itertools
import datetime
import codecs
import types
from collections import namedtuple, defaultdict
import subprocess
from functools import reduce
from ledger import Transaction, Posting, Amount, FutureAmountFraction, sortTransactionsByDate, NoAmount, queryHledgerForAccountList



#################### BEGIN CONFIG ##########################
re_hide_line_ = re.compile(".*\(HIDE\)$")
from config import *

#################### CONFIG END ##########################

nix = NoAmount()
nonascii_re = re.compile(r"[^[:ascii:]]")
transfer_regex_ = re.compile(r"^To '([^']+)'$")

def quote(str):
    return '"'+str.replace('"','\"')+'"'

input_stream = io.TextIOWrapper(sys.stdin.buffer, encoding='utf8',newline='')
csvfile = csv.reader(input_stream, delimiter=',', quotechar="\"", quoting=csv.QUOTE_MINIMAL)

transactions = []
for row in csvfile:
    new_transaction = None
    (date,expenseacct,category,amountCmp,currency,csvdescription) = row
    if date == "date" and expenseacct == "account":
        continue
    if not re_hide_line_.match(csvdescription) is None:
        continue
    date = datetime.datetime.strptime(date,"%d/%m/%Y").date()
    amountCmp = float(amountCmp)

    if category.startswith("From '"):
        continue

    assert(expenseacct in monefy_account_shorthands)
    targetacct = monefy_account_shorthands[expenseacct]

    if targetacct in monefy_ignore_accounts_:
        continue

    description, *commentlist = csvdescription.split(";")
    description = description.strip()
    comment = " ".join(commentlist).strip()
    if comment == "":
        comment = None

    new_transaction = Transaction(description, date).addPosting(Posting(targetacct,Amount(amountCmp,currency)))
    if not comment is None and len(comment) > 0:
        new_transaction

    tm = transfer_regex_.search(category)
    if not tm is None:
        sourceacct = tm.group(1)
        assert(sourceacct in monefy_account_shorthands)
        sourceacct = monefy_account_shorthands[sourceacct]
    else:
        if not category in monefy_category_shorthands:
            print("unknown category:",category,file=sys.stderr)
            assert(False)
        sourceacct = monefy_category_shorthands[category]

        new_transaction.addPosting(Posting(sourceacct, nix, comment)).addTag("monefy")

    transactions.append(new_transaction)


not_balanced = [t for t in transactions if not t.isBalanced()]
if len(not_balanced) > 0:
    print("ERROR: the following transactions are not balanced !!\n", file=sys.stderr)
    print("\n\n".join(map(str,(sortTransactionsByDate(not_balanced)))), file=sys.stderr)
    sys.exit(1)
assert(len(not_balanced) == 0)

def mergeIdenticalTransactionsInList(lst, itm):
    t, orig_index = itm
    if len(lst)>0 and t.date == lst[-1][0].date and t.name == lst[-1][0].name:
        #merge transactions, give it largest sorting index, so merged transaction get sorted at position of its youngest subtransaction
        origt = lst[-1][0]
        origt.mergeInPostingsFrom(t)
        lst[-1] = (origt, orig_index)
    else:
        lst.append(itm)
    return lst

def groupTransactionByDate(ddict,t):
    ddict[t.date].append(t)
    return ddict

#grouped_transactions =  reduce(groupTransactionByDate, sortTransactionsByDate(transactions), defaultdict(list))

## merge transactions with same name and date
# sort transactions by date and name for merging, but remember original order
sorted_transactions =  reduce(mergeIdenticalTransactionsInList, sorted(zip(transactions,range(0,len(transactions))), key=lambda tidx: (tidx[0].date,tidx[0].name)), [])
sorted_merged_transactions = [t1 for (t1,idx1) in sorted(sorted_transactions, key=lambda tidx: (tidx[0].date,tidx[1])) ]

print("\n\n".join(map(str,(sorted_merged_transactions))))

