#!/usr/bin/python3
# -*- coding: utf-8 -*-

import re
import sys, os, io
import csv
import itertools
import datetime
import codecs
import types
from collections import namedtuple
import subprocess
from ledger import Transaction, Posting, Amount, FutureAmountFraction, sortTransactionsByDate, NoAmount, queryHledgerForAccountList

#################### BEGIN CONFIG ##########################
#elba_posting_date_ = re.compile(r"([0-3]\d\.[0-1]\d)\s?UM [0-2]\d[:.][0-5]\d|\s([0-3]\d\.[0-1]\d\.\d\d)\sK\d\s[0-2]\d:[0-5]\d|([0-3]\d\.[0-1]\d\.\d\d)\s[0-2]\d:[0-5]\dK\d")
date_ignore_re = re.compile(r"Vorgemerkte Buchung")

from config import *
#################### CONFIG END ##########################



input_stream = io.TextIOWrapper(sys.stdin.buffer, encoding='latin1',newline='')
csvfile = csv.reader(input_stream,delimiter=';', quotechar='"')

#print(regexp_to_member)
transactions = []
for row in csvfile:
    new_transaction = None
    (date,description,date2,amountCmp,currency,*rest) = row
    date = datetime.datetime.strptime(date,"%d.%m.%Y").date()
    date2 = datetime.datetime.strptime(date2,"%d.%m.%Y").date()
    amountCmp = float(amountCmp.replace(",","."))

    ## search for match and convert to Transaction
    matching_matchors = []
    for (p_re, amt_guard), potential_transaction_or_function_returning_transaction in transaction_matchors.items():
        if not amt_guard(amountCmp):
            continue
        m = p_re.search(description)
        if m:
            matching_matchors.append( ( m.end() - m.start() , potential_transaction_or_function_returning_transaction ) )

    ## longest found match wins. Start with first in list reverse-sorted by match-length
    for match_length, potential_transaction_or_function_returning_transaction in sorted(matching_matchors, reverse=True):
        if isinstance(potential_transaction_or_function_returning_transaction, Transaction):
            new_transaction = potential_transaction_or_function_returning_transaction.copy()
            break
        elif type(potential_transaction_or_function_returning_transaction) == types.FunctionType:
            new_transaction = potential_transaction_or_function_returning_transaction(amountCmp, description)
            if isinstance(new_transaction, Transaction):
                break
        else:
            ## Unsupported Value in Matchor, neither a Transaction nor a function yielding a transaction
            print(p_re, description, potential_transaction_or_function_returning_transaction, file=sys.stderr)
            assert(False)

    ## if no match found, tag as default transaction
    if not isinstance(new_transaction, Transaction):
        if amountCmp > 0.0:
            new_transaction = unknown_revenue_default_transaction_.copy()
        elif amountCmp < 0.0:
            new_transaction = unknown_expense_default_transaction_.copy()
        else:
            new_transaction = unknown_equity_default_transaction_.copy()

    ## Convert FutureAmoutFractions to real Amounts
    for p in new_transaction.postings:
        if isinstance(p.amount, FutureAmountFraction):
            p.amount.convertToAmount(Amount(amountCmp,currency))
        if date2 != date:
            p.setDate(date2)
    new_transaction.prependPosting(Posting(elba_primary_account_, Amount(amountCmp,currency))).addComment(description).setDate(date)

    transactions.append(new_transaction)


not_balanced = [t for t in transactions if not t.isBalanced()]
if len(not_balanced) > 0:
    print("ERROR: the following transactions are not balanced !!\n", file=sys.stderr)
    print("\n\n".join(map(str,(sortTransactionsByDate(not_balanced)))), file=sys.stderr)
    sys.exit(1)
assert(len(not_balanced) == 0)

print("\n\n".join(map(str,(sortTransactionsByDate(transactions)))))

