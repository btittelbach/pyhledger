#!/usr/bin/python3
# -*- coding: utf-8 -*-

import ledger
import os, sys
from functools import reduce

register_account_ = "assets:current:cash:register"
revenue_accounts_ = ["revenue:sales:edibles", "revenue:sales:materials"]
inventory_accounts_ = ["assets:current:inventory-edibles", "assets:current:inventory-materials" ]
schwund_account_ = "expenses:shrinkage"
donation_account_ = "expenses:shrinkage"
#donation_account_ = "revenue:donations:shrinkage"
default_currency_ = "EUR"

hledger_ledgerpath_=os.path.split(__file__)[0]+'/../Ledgers/r3.ledger'

ledger_fileobj = open(hledger_ledgerpath_)
journal = ledger.sortTransactionsByDate(ledger.parseJournal(ledger_fileobj))
ledger_fileobj.close()

acct_currency_amt_dict, asstresult = ledger.sumUpJournalVerifyAssertions(journal, abort_on_assrtfail=True)
#print(ledger.showSums(acct_currency_amt_dict, [register_account_, revenue_account_]+ inventory_accounts_))

if asstresult == True:
    sys.exit(0)
    ##nothing to do

asstresult, problematic_transaction, posting_with_failed_assertion = asstresult

assert(asstresult == False)
if problematic_transaction.name != "INVENTUR":
    print("ERROR problematic_transaction.name != INVENTUR",file=sys.stderr)
    print(problematic_transaction)
    sys.exit(1)

register_current_euro = acct_currency_amt_dict[register_account_][default_currency_].quantity

last_good_inventur_transaction_index = 0
problematic_transaction_index = 0
for i in range(0, len(journal)):
    if journal[i] == problematic_transaction:
        problematic_transaction_index = i
        break
    if journal[i].name == "INVENTUR" and len([1 for p in journal[i].postings if p.account == register_account_]) > 0:
        last_good_inventur_transaction_index = i

isrevenueacct = lambda a : a in revenue_accounts_

#transactions_since_last_inventur = journal[last_good_inventur_transaction_index+1:problematic_transaction_index+1]
#umsatz_zwischen_inventuren_ohne_getränkeerlös = 0.0
#for t in transactions_since_last_inventur:
#        umsatz_zwischen_inventuren_ohne_getränkeerlös += sum([p.amount.quantity for p in t.postings if p.account == register_account_ and p.amount.currency == default_currency_])

#### Variante 1: zwei große Postings, aber "Waren" tauchen in revenue:sales:edibles auf, während die revenue erst mit hledger --cost sichtbar wird
#nt = ledger.Transaction("VERKAUFTE WAREN: EINKAUFSPREIS", problematic_transaction.date)
#for pp in problematic_transaction.postings:
#    if pp.account in inventory_accounts_ and pp.account in acct_currency_amt_dict and not pp.post_posting_assert_amount is None and pp.post_posting_assert_amount.currency in acct_currency_amt_dict[pp.account]:
#        diff = pp.post_posting_assert_amount.quantity - acct_currency_amt_dict[pp.account][pp.post_posting_assert_amount.currency].quantity
#        nt.addPosting(ledger.Posting(pp.account, ledger.Amount(diff,pp.post_posting_assert_amount.currency).addPerUnitPrice(acct_currency_amt_dict[pp.account][pp.post_posting_assert_amount.currency].perunitprice)))
#        nt.addPosting(ledger.Posting(revenue_account_, ledger.Amount(-1*diff,pp.post_posting_assert_amount.currency).addPerUnitPrice(acct_currency_amt_dict[pp.account][pp.post_posting_assert_amount.currency].perunitprice)))
#
#gt = ledger.Transaction("VERKAUFTE WAREN: VERKAUFSERLÖS", problematic_transaction.date).addPosting(ledger.Posting(register_account_, ledger.NoAmount()))
#for pp in problematic_transaction.postings:
#    if pp.account in inventory_accounts_ and pp.account in acct_currency_amt_dict and not pp.post_posting_assert_amount is None and pp.post_posting_assert_amount.currency in acct_currency_amt_dict[pp.account]:
#        diff = pp.post_posting_assert_amount.quantity - acct_currency_amt_dict[pp.account][pp.post_posting_assert_amount.currency].quantity
#        gt.addPosting(ledger.Posting(revenue_account_, ledger.Amount(diff,pp.post_posting_assert_amount.currency).addPerUnitPrice(pp.amount.perunitprice)))
#
#gt.unelideJokerPostings()

#revenue_euro = [p for p in gt.postings if p.account == register_account_ and p.amount.currency == default_currency_][0].amount.quantity
#
#schwund_euro = register_assert_euro - (register_current_euro + revenue_euro)
#
#eurofix = ledger.Transaction(schwund_transactionname, problematic_transaction.date).addPosting(ledger.Posting(register_account_,ledger.Amount(schwund_euro, default_currency_))).addPosting(ledger.Posting(schwund_account_, ledger.NoAmount()))
#
#assert(nt.isBalanced())
#assert(gt.isBalanced())
#assert(eurofix.isBalanced())

#### Variante 2: ein Posting für jede Ware
gewinn_transactions = []
for pp in problematic_transaction.postings:
    if pp.account in inventory_accounts_ and pp.account in acct_currency_amt_dict and not pp.post_posting_assert_amount is None and pp.post_posting_assert_amount.currency in acct_currency_amt_dict[pp.account]:
        gt = ledger.Transaction("GEWINN %s" % pp.post_posting_assert_amount.currency, problematic_transaction.date)
        diff = round(pp.post_posting_assert_amount.quantity - acct_currency_amt_dict[pp.account][pp.post_posting_assert_amount.currency].quantity,4)
        if diff == 0:
            continue
        if diff > 0:
            gt.addDescription("WARNING: commoditiy difference is positive!!!!! WARNING")
            gt.addDescription("WARNING: looks like an inventory count mistake or undocumented commodity donation")
        einkaufspreis = acct_currency_amt_dict[pp.account][pp.post_posting_assert_amount.currency].perunitprice
        verkaufspreis = pp.amount.perunitprice
        gt.addPosting(ledger.Posting(pp.account, ledger.Amount(diff,pp.post_posting_assert_amount.currency).addPerUnitPrice(einkaufspreis)))
        #add comment: % gewinn
        gumsatz = verkaufspreis.quantity * diff
        geinkaufspreis = gt.postings[0].amount.totalprice.quantity
        revenue_acct = revenue_accounts_[inventory_accounts_.index(pp.account)]
        gt.addPosting(ledger.Posting(revenue_acct, None).addComment("(%.2f%% Gewinn)" % (  100*(1.0+(geinkaufspreis/gumsatz))  )))
        gt.addPosting(ledger.Posting(register_account_, ledger.Amount(gumsatz * -1,verkaufspreis.currency)))
        gt.unelideJokerPostings()
        gewinn_transactions.append(gt)

register_assert_euro_postings = [p for p in problematic_transaction.postings if p.account == register_account_ and p.post_posting_assert_amount.currency == default_currency_]
register_previousassert_euro_postings = [p for p in journal[last_good_inventur_transaction_index].postings if p.account == register_account_ and p.post_posting_assert_amount.currency == default_currency_]

if len(register_assert_euro_postings) == 1:
    register_assert_euro = register_assert_euro_postings[0].post_posting_assert_amount.quantity
    if len(register_previousassert_euro_postings) == 1:
        register_previousassert_euro = register_previousassert_euro_postings[0].post_posting_assert_amount.quantity
        umsatz_zwischen_inventuren_ohne_getränkeerlös_euro = register_current_euro - register_previousassert_euro
    if len(gewinn_transactions) == 0: ## aka all commodity asserts are already correct
        calculated_umsatz_durch_verkauf_euro = 0
        calculated_gewinn_durch_verkauf_euro = 0
    else:
        gewinn_transactions_all_postings = reduce(list.__add__, [t.postings for t in gewinn_transactions])
        calculated_umsatz_durch_verkauf_euro = sum([p.amount.quantity for p in gewinn_transactions_all_postings if p.account == register_account_ and p.amount.currency == default_currency_])
        calculated_gewinn_durch_verkauf_euro = sum([p.amount.quantity for p in gewinn_transactions_all_postings if isrevenueacct(p.account) and p.amount.currency == default_currency_])
    # Differenz zwischen Summe Kassabucheinträgen (current hledger sum) und tatsächlicher Kassazählung (assert) AKA noch unverbuchte Einzahlungen
    register_diff_umsatz_euro = register_assert_euro - register_current_euro
    # Schwund ist Diff zwischen dem was da sein sollte zu dem was tatsächlich da ist
    register_diff_umsatz_plus_getraenke_euro = register_diff_umsatz_euro - calculated_umsatz_durch_verkauf_euro # positiv wenn mehr geld als erwartet da

    schwund_transactionname = "FEHLBETRAG"
    # Prozent unbezahlter Getränke
    if calculated_umsatz_durch_verkauf_euro != 0:
        schwund_fraction_of_what_should_have_been_paid = register_diff_umsatz_plus_getraenke_euro / (calculated_umsatz_durch_verkauf_euro)
        schwund_transactionname = "FEHLBETRAG: %.2f%% fehlende Getränkezahlungen" % (100*schwund_fraction_of_what_should_have_been_paid)

    if register_diff_umsatz_plus_getraenke_euro > 0:
        schwund_account_ = donation_account_
        schwund_transactionname = "SPENDEN"

    eurofix = ledger.Transaction(schwund_transactionname, problematic_transaction.date).addPosting(ledger.Posting(register_account_,ledger.Amount(register_diff_umsatz_plus_getraenke_euro, default_currency_))).addPosting(ledger.Posting(schwund_account_, ledger.NoAmount()))
    if "schwund_fraction_of_what_should_have_been_paid" in globals():
        eurofix.addTag("schwund","%.4f"%schwund_fraction_of_what_should_have_been_paid)
    if len(register_previousassert_euro_postings) == 1:
        eurofix.addDescription("Kassastand zu Inventur vom %s: %s" % (journal[last_good_inventur_transaction_index].date, ledger.Amount(register_previousassert_euro, default_currency_)))
    eurofix.addDescription("seit letzter Inventur vom %s:" % journal[last_good_inventur_transaction_index].date)
    eurofix.addDescription("\-- erw. Umsatz durch Verkauf: %s" % ledger.Amount(calculated_umsatz_durch_verkauf_euro, default_currency_))
    if calculated_umsatz_durch_verkauf_euro != 0:
        eurofix.addDescription("\-- erw. Gewinn durch Verkauf: %s (%.2f%%)" % (ledger.Amount(-1*calculated_gewinn_durch_verkauf_euro, default_currency_), -100*(calculated_gewinn_durch_verkauf_euro / calculated_umsatz_durch_verkauf_euro)))
    if len(register_previousassert_euro_postings) == 1:
        eurofix.addDescription("\-- eingetragene Umsätze ohne Verkauf: %s" % (ledger.Amount(umsatz_zwischen_inventuren_ohne_getränkeerlös_euro, default_currency_)))
    eurofix.addDescription("errechneter Kassastand vor theoretischem Verkaufsumsatz: %s" % ledger.Amount(register_current_euro,default_currency_))
    eurofix.addDescription("theoretischer Kassastand nach theoretischem Verkaufsumsatz: %s" % ledger.Amount(register_current_euro + calculated_umsatz_durch_verkauf_euro,default_currency_))
    assert(eurofix.isBalanced())

assert(all([t.isBalanced() for t in gewinn_transactions]))

print("\n\n; BEGIN autogenerierte Inventurbuchungen")
for t in gewinn_transactions:
    print("\n%s" % (t))
if "eurofix" in globals():
    print("\n%s" % (eurofix))
print("\n; ENDE autogenerierte Inventurbuchungen\n")
print("\n%s\n" % (problematic_transaction))
