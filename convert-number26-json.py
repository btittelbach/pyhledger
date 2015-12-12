#!/usr/bin/python3
# -*- coding: utf-8 -*-

from ledger import *
import os, sys, io
from functools import reduce
import json
import datetime
import time


#################### BEGIN CONFIG ##########################

from config import *
transaction_type_direction_ = {"CT":1,"AA":-1,"PT":-1,"AV":1, "AE":1, "DD":-1, "DT":-1}

#################### CONFIG END ##########################

def addTagsFromDict(t, dct, prepend=""):
    for k,v in dct.items():
        if isinstance(v,dict):
            addTagsFromDict(t, v, k+"_")
        else:
            t.addTag(prepend+k,str(v).strip())


newjournal = []
input_stream = io.TextIOWrapper(sys.stdin.buffer, encoding='utf8',newline='')
json_array_sorted = sorted(json.load(input_stream)["data"], key=lambda x: x["visibleTS"])
for jsontrsc in json_array_sorted:
    date = datetime.date.fromtimestamp(jsontrsc["visibleTS"]/1000.0)
    currency = jsontrsc["currencyCode"]["currencyCode"]
#    if "newAmount" in jsontrsc and "oldAmount" in jsontrsc:
#        amount = jsontrsc["newAmount"] - jsontrsc["oldAmount"] #gives us plus/minus sign which "amount" does not give
#    else:
    assert("type" in jsontrsc and jsontrsc["type"] in transaction_type_direction_)
    amount = jsontrsc["amount"] * transaction_type_direction_[(jsontrsc["type"])]
    jsontrsc["Amount"] = amount
    name = " ".join([ str(jsontrsc[k]).strip() for k in ["bankTransferTypeText","partnerName","merchantName","merchantCity"] if k in jsontrsc ])
    new_transaction = None
    for (guardfunc, possible_transaction) in n26_transaction_matchors.items():
        try:
            if not guardfunc(jsontrsc):
                continue
        except Exception as e:
            continue
        new_transaction = possible_transaction.copy()
        break # first match wins

    if new_transaction is None:
        if amount > 0.0:
            new_transaction = unknown_revenue_default_transaction_.copy()
        elif amount < 0.0:
            new_transaction = unknown_expense_default_transaction_.copy()
        else:
            new_transaction = unknown_equity_default_transaction_.copy()

    new_transaction.setDate(date).addComment(name)
    new_posting = Posting(n26_primary_account_, Amount(amount, currency))
    if amount < 0.0 and "newAmount" in jsontrsc:
        new_posting.addPostPostingAssertAmount(Amount(jsontrsc["newAmount"], currency))
    elif amount > 0.0 and "oldAmount" in jsontrsc:
        new_posting.addPostPostingAssertAmount(Amount(jsontrsc["oldAmount"], currency))
    new_transaction.prependPosting(new_posting)
    addTagsFromDict(new_transaction, jsontrsc)
    newjournal.append(new_transaction)


not_balanced = [t for t in newjournal if not t.isBalanced()]
if len(not_balanced) > 0:
    print("ERROR: the following transactions are not balanced !!\n", file=sys.stderr)
    print("\n\n".join(map(str,(sortTransactionsByDate(not_balanced)))), file=sys.stderr)
    sys.exit(1)
assert(len(not_balanced) == 0)

print("\n\n".join(map(str,(newjournal))))

