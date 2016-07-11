#!/usr/bin/python3
# -*- coding: utf-8 -*-

import ledger
import sys
with open(sys.argv[1]) as jf:
    j = ledger.sortTransactionsByDate(ledger.parseJournal(jf))
#    j = ledger.parseJournal(jf)

#for t in j:
#    sys.stdout.write("%s\n\n" % (t,))

for t, acctsum, assrt in ledger.runningSumOfJournal(j):
    sys.stdout.write("%s\n-----------\n%s%s\n\n" % (t,ledger.showSums(acctsum,["assets:current:cash:register"]),assrt))
