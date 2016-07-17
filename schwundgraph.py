#!/usr/bin/python3
# -*- coding: utf-8 -*-

import ledger
import os, sys
from functools import reduce
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.dates import date2num
import datetime

register_account_ = "assets:current:cash:register"
revenue_accounts_ = ["revenue:sales:edibles", "revenue:sales:materials"]
inventory_accounts_ = ["assets:current:inventory-edibles", "assets:current:inventory-materials" ]
schwund_account_ = "expenses:shrinkage"
donation_account_ = "expenses:shrinkage"
#donation_account_ = "revenue:donations:shrinkage"
default_currency_ = "EUR"

hledger_ledgerpath_=os.path.split(__file__)[0]+'/../Ledgers/r3.ledger'

ledger_fileobj = open(hledger_ledgerpath_)
journal = ledger.sortTransactionsByDate(
    list(ledger.createTempAccountsForAndConvertFromMultiDatePostings(
        ledger.parseJournal(ledger_fileobj)
        ))
    )
ledger_fileobj.close()

dates = []
interval = [] # days between taking inventory
d1 = []
d2 = []
d3 = []
d4 = []

# 3 datapoints of umsatz:
# - minimum break even point: summmer der einkaufspreise der getränke/snaks die aus assets:current:inventory-edibles verkauft wurden
# - tatsächlicher umsatz: erwarteter umsatz mit getränken - schwund in euro
# - maximum we should get: erw. umsatz mit getränken
# in inventur.py wären das:
#    d1_minimum_break_even = calculated_worth_of_beverages_sold_euro
#    d2_actual_revenue = calculated_umsatz_durch_verkauf_euro + register_diff_umsatz_plus_getraenke_euro
#    d3_maximum_possible = calculated_umsatz_durch_verkauf_euro

last_inventur = None
d1_minimum_break_even_euro = 0.0
d3_maximum_possible = 0.0
d4_other_expenses = 0.0
for t in journal:
    if t.name == "INVENTUR":
        last_inventur = datetime.datetime.strptime(t.date,ledger.dateformat_hledger_csvexport_).date()
        d4_other_expenses = 0.0
    if t.date < "2015/10/01":
        continue
    if t.name.startswith("GEWINN "):
        # einkaufspreis aus GEWINN Transaction
        d1_minimum_break_even_euro += sum([p.amount.totalprice.quantity for p in t.postings if p.account in inventory_accounts_ and p.amount.totalprice.currency == default_currency_])
        # erwartete Einnahmen durch Anzahl verkaufte Dinge mal Verkaufspreis aus GEWINN Transaction
        d3_maximum_possible += sum([p.amount.quantity for p in t.postings if p.account == register_account_ and p.amount.currency == default_currency_])
    elif schwund_account_ in [p.account for p in t.postings] or donation_account_ in [p.account for p in t.postings]:
        # erwartete Einnahmen +/- der Differenz zu realen Einnahmen
        d2_actual_revenue = d3_maximum_possible + sum([p.amount.quantity for p in t.postings if p.account == register_account_ and p.amount.currency == default_currency_])
        t_date = datetime.datetime.strptime(t.date,ledger.dateformat_hledger_csvexport_).date()
        dates.append(t_date)
        num_days = (t_date - last_inventur).days
        interval.append(num_days)
        d1.append(d1_minimum_break_even_euro/num_days)
        d2.append(d2_actual_revenue/num_days)
        d3.append(d3_maximum_possible/num_days)
        #d4_other_expenses += d1_minimum_break_even_euro # expenses increase break even
        d4.append(d4_other_expenses / num_days)
        d1_minimum_break_even_euro = 0.0
        d3_maximum_possible = 0.0
    elif not any([invacct in [p.account for p in t.postings] for invacct in inventory_accounts_]):
        #expenses that are not related to beverages (includes money taken out by me,m1ch,equinox .. need to acount for that somehow TODO)
        d4_other_expenses -= sum([p.amount.quantity for p in t.postings if p.account == register_account_ and p.amount.currency == default_currency_])


print(dates)
print(d1)
print(d2)
print(d3)
print(d4)

#TODO: make this a bar graph
#TODO: include things bought with cash into d1 to increase break-even to true value
# (right now the graph does not show loss, because the things we need to buy from the beverage revenue is not factored in)

plt.figure()
plt.plot(dates,d3, label="Erwartete Einnahmen/Tag")
plt.plot(dates,d2, label="Tatsächliche Einnahmen/Tag")
plt.plot(dates,d1, label="Break-Even/Tag")
plt.plot(dates,d4, label="Expenses/Tag")
plt.legend(loc='lower left')
plt.title("Break-even vs tatsächlich Einnahmen vs theoretisches Maximum (normiert auf Tage)")
plt.ylabel("EUR")
plt.xlabel("Date")
plt.grid(True)
## draw a line at y=0 (i.e. xaxis line)
plt.axhline(0, color='black')

########## Bar Graph, normalized on Break-Even

dates = date2num(dates)

expected_profit_per_day = [a-b for (a,b) in zip(d3,d1)]
true_profit_per_day = [a-b for (a,b) in zip(d2,d1)]

ax = plt.figure()
plt.bar(dates-1, expected_profit_per_day, color='b',align='center', label="Erwarteter Gewinn/Tag")
plt.bar(dates,true_profit_per_day , color='r',align='center', label="Tatsächlicher Gewinn/Tag")
plt.bar(dates+1, d4, color='g',align='center', label="Expenses/Tag")
plt.legend(loc='upper left')
plt.title("Break-even vs tatsächlich Einnahmen vs theoretisches Maximum (normiert auf Tage und break-even)  (BUGGY)")
plt.ylabel("EUR")
plt.xlabel("Date")
plt.grid(True)
#ax.xaxis_date()
## draw a line at y=0 (i.e. xaxis line)
plt.axhline(0, color='black')


########## CDF of profit versus expenses that do not generate profit

cumulative_expected_profit_per_day = np.cumsum(expected_profit_per_day)
cumulative_true_profit_per_day = np.cumsum(true_profit_per_day)
cumulative_expenses_per_day = np.cumsum(d4)

plt.figure()
plt.plot(dates,cumulative_expected_profit_per_day, label="CDF erwartetes verfügbares Geld")
plt.plot(dates,cumulative_true_profit_per_day, label="CDF tatsächlich verfügbares Geld")
plt.plot(dates,cumulative_expenses_per_day, label="CDF Ausgaben")
plt.legend(loc='upper left')
plt.title("available money and it's use (BUGGY)")
plt.ylabel("EUR")
plt.xlabel("Date")
plt.grid(True)
## draw a line at y=0 (i.e. xaxis line)
plt.axhline(0, color='black')


plt.show()