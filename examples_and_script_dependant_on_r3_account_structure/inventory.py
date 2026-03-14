#!/usr/bin/python3
# -*- coding: utf-8 -*-

import ledger
import os, sys
from functools import reduce

register_account_ = "assets:current:cash:register"
cash_account_prefix_ = "assets:current:cash"
revenue_accounts_ = ["revenue:sales:edibles", "revenue:sales:materials"]
inventory_accounts_ = ["assets:current:inventory-edibles", "assets:current:inventory-materials" ]
expense_accounts_ = ["expenses:sales:edibles", "expenses:sales:materials"]
schwund_account_ = "revenue:sales:edibles"
donation_account_ = "revenue:sales:edibles"
theoreticalsales_tag = "theoreticalsales"
bargeldverwahrung_tag_ = "bargeldverwahrung"
schwund_tag_ = "schwund"
salessystem_tag_ = "inventorysalesaccounting"
#donation_account_ = "revenue:donations:shrinkage"
default_currency_ = "EUR"

## this is where our ledger file is
hledger_ledgerpath_=os.path.split(__file__)[0]+'/../Ledgers/r3.ledger'

## open and parse and sort the ledger file
ledger_fileobj = open(hledger_ledgerpath_)
journal = ledger.sortTransactionsByDate(
    list(ledger.createTempAccountsForAndConvertFromMultiDatePostings(
        ledger.parseJournal(ledger_fileobj)
        ))
    )
ledger_fileobj.close()

## create a dictionary with sum per acount and currency from ledger
acct_currency_amt_dict, asstresult = ledger.sumUpJournalVerifyAssertions(journal, abort_on_assrtfail=True)
#print(ledger.showSums(acct_currency_amt_dict, [register_account_]+revenue_accounts_+ inventory_accounts_))

if asstresult == True:
    sys.exit(0)
    ##nothing to do

## get the next transaction with asserts that failed (i.e. a Inventory with asserts that has not been processed yet)
asstresult, problematic_transaction, posting_with_failed_assertion = asstresult

## make sure the transaction we found is actually an INVENTUR transaction
assert(asstresult == False)
if problematic_transaction.name != "INVENTUR":
    print("ERROR problematic_transaction.name != INVENTUR",file=sys.stderr)
    print(problematic_transaction)
    sys.exit(1)

## how much money does hledger believe is in the cash:register at time of inventur
register_current_euro = acct_currency_amt_dict[register_account_][default_currency_].quantity

## get index of last and current inventur transaction in journal
last_good_inventur_transaction_index = 0
problematic_transaction_index = 0
for i in range(0, len(journal)):
    if journal[i] == problematic_transaction:
        problematic_transaction_index = i
        break
    if journal[i].name == "INVENTUR" and len([1 for p in journal[i].postings if p.account == register_account_]) > 0:
        last_good_inventur_transaction_index = i

isrevenueacct = lambda a : a in revenue_accounts_
isexpenseacct = lambda a : a in expense_accounts_

#transactions_since_last_inventur = journal[last_good_inventur_transaction_index+1:problematic_transaction_index+1]
#umsatz_zwischen_inventuren_ohne_getränkeerlös = 0.0
#for t in transactions_since_last_inventur:
#        umsatz_zwischen_inventuren_ohne_getränkeerlös += sum([p.amount.quantity for p in t.postings if p.account == register_account_ and p.amount.currency == default_currency_])

#### Variante 1: zwei große Postings, aber "Waren" tauchen in revenue:sales-gewinn:edibles auf, während die revenue erst mit hledger --cost sichtbar wird
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

## Warenwert nach aktueller Inventur:
warenwert_lager_diese_inventur = {}
for iacct in inventory_accounts_:
    warenwert_lager_diese_inventur[iacct] = 0.0
    for key, amt in acct_currency_amt_dict[iacct].items():
        if amt.totalprice and amt.totalprice.currency == default_currency_:
            warenwert_lager_diese_inventur[iacct] += amt.totalprice.quantity

## Warenwert nach letzter Inventur:
warenwert_lager_letzte_inventur = {}
letzte_inventur_acct_currency_amt_dict, letzte_inventur_asstresult = ledger.sumUpJournalVerifyAssertions(journal[:last_good_inventur_transaction_index], abort_on_assrtfail=True)
#print(ledger.showSums(letzte_inventur_acct_currency_amt_dict, [register_account_]+revenue_accounts_+ inventory_accounts_))
for iacct in inventory_accounts_:
    warenwert_lager_letzte_inventur[iacct] = 0.0
    for key, amt in letzte_inventur_acct_currency_amt_dict[iacct].items():
        if amt.totalprice and amt.totalprice.currency == default_currency_:
            warenwert_lager_letzte_inventur[iacct] += amt.totalprice.quantity

## Menge Bargeldverwahrung
## zwei Möglichkeiten diese zu bestimmen:
## 1. tag bargeldverwarung:,
## 2. summe der postings auf ein assets:current:cash Konto welches != assets:current:cash:register ist und in dessen transaction ein posting mit assets:current:cash:register vorkommt
register_diff_cash_bargeldverwahrung = 0.0
for t in journal[last_good_inventur_transaction_index:problematic_transaction_index]:
    if t.getTag(bargeldverwahrung_tag_) != None:
        for p in t.postings:
            if p.account == register_account_ and p.amount.currency == default_currency_:
                register_diff_cash_bargeldverwahrung -= p.amount.quantity  #register_diff_cash_bargeldverwahrung should end up positive

#### Variante 2: ein Posting für jede Ware
gewinn_transactions = []
for pp in problematic_transaction.postings:
    if pp.account in inventory_accounts_ and pp.account in acct_currency_amt_dict and not pp.post_posting_assert_amount is None and pp.post_posting_assert_amount.currency in acct_currency_amt_dict[pp.account]:
        ## build gewinn transactions
        gt = ledger.Transaction("UMSATZ %s" % pp.post_posting_assert_amount.currency, problematic_transaction.getDate().isoformat())
        gt.addTag(salessystem_tag_).addTag(theoreticalsales_tag)

        ## Differenz assertion zu journal pro Ware ausrechnen
        diff = round(pp.post_posting_assert_amount.quantity - acct_currency_amt_dict[pp.account][pp.post_posting_assert_amount.currency].quantity,4)
        if diff == 0:
            continue
        if diff > 0:
            gt.addDescription("WARNING: commoditiy difference is positive!!!!! WARNING")
            gt.addDescription("WARNING: looks like an inventory count mistake or undocumented commodity donation")
        ## Warenwert ausrechnen
        einkaufspreis = acct_currency_amt_dict[pp.account][pp.post_posting_assert_amount.currency].perunitprice
        verkaufspreis = pp.amount.perunitprice
        revenue_acct = revenue_accounts_[inventory_accounts_.index(pp.account)]
        expense_acct = expense_accounts_[inventory_accounts_.index(pp.account)]
        warenmenge_mit_einkaufspreis = ledger.Amount(diff,pp.post_posting_assert_amount.currency).addPerUnitPrice(einkaufspreis)

        ## update warenwert_lager_diese_inventur
        if warenmenge_mit_einkaufspreis.totalprice.currency == default_currency_:
            warenwert_lager_diese_inventur[pp.account] -= warenmenge_mit_einkaufspreis.totalprice.quantity

        ## Posting zur Transaction für diese Ware hinzufügen
        warenmenge_expenseprice=warenmenge_mit_einkaufspreis.totalprice.copy()
        ### in case wares suddenly appeard, we need to still balance transactions
        if warenmenge_mit_einkaufspreis.quantity > 0:
            warenmenge_expenseprice.flipSign()
        gt.addPosting(ledger.Posting(pp.account, warenmenge_mit_einkaufspreis))
        gt.addPosting(ledger.Posting(expense_acct,warenmenge_expenseprice))

        #add comment: % gewinn
        gumsatz = verkaufspreis.quantity * diff
        geinkaufspreis = gt.postings[0].amount.totalprice.quantity

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
        expected_revenue_durch_verkauf_euro = 0
        calculated_expense_fuer_verkauf_euro = 0
    else:
        gewinn_transactions_all_postings = reduce(list.__add__, [t.postings for t in gewinn_transactions])
        expected_revenue_durch_verkauf_euro = sum([p.amount.quantity for p in gewinn_transactions_all_postings if isrevenueacct(p.account) and p.amount.currency == default_currency_])
        calculated_expense_fuer_verkauf_euro = sum([p.amount.quantity for p in gewinn_transactions_all_postings if isexpenseacct(p.account) and p.amount.currency == default_currency_])
    # Differenz zwischen Summe Kassabucheinträgen (current hledger sum) und tatsächlicher Kassazählung (assert) AKA noch unverbuchte Einzahlungen
    # == Diff zwischen Inventuren OHNE erwartete Getränkeeinnahmen
    register_diff_umsatz_euro = register_assert_euro - register_current_euro
    # == Diff zwischen Inventuren MIT erwarteten Getränkeeinnahmen
    # Schwund ist Diff zwischen dem was da sein sollte zu dem was tatsächlich da ist
    # == KassastandInventur(t=0) - KassastandInventur(t=-1) - Verkaufspreis*(GetränkestandInventur(t=0) - GetränkestandInventur(t=-1))
    # == register_diff_umsatz_plus_getraenke_euro = register_assert_euro - (register_current_euro + -1*expected_revenue_durch_verkauf_euro)
    register_diff_umsatz_plus_getraenke_euro = register_diff_umsatz_euro + expected_revenue_durch_verkauf_euro # positiv wenn mehr geld als erwartet da

    schwund_transactionname = "AUSGLEICHSBUCHUNG"
    # Prozent unbezahlter Getränke
    if expected_revenue_durch_verkauf_euro != 0:
        schwund_fraction_of_what_should_have_been_paid = -1 * register_diff_umsatz_plus_getraenke_euro / (expected_revenue_durch_verkauf_euro)
        schwund_transactionname = "AUSGLEICHSBUCHUNG: %.2f%% fehlende Getränkezahlungen" % (100*schwund_fraction_of_what_should_have_been_paid)

    if register_diff_umsatz_plus_getraenke_euro > 0:
        schwund_account_ = donation_account_
        schwund_transactionname = "AUSGLEICHSBUCHUNG"

    eurofix = ledger.Transaction(schwund_transactionname, problematic_transaction.getDate()).addPosting(ledger.Posting(register_account_,ledger.Amount(register_diff_umsatz_plus_getraenke_euro, default_currency_))).addPosting(ledger.Posting(schwund_account_, ledger.NoAmount())).addTag(salessystem_tag_)
    if "schwund_fraction_of_what_should_have_been_paid" in globals():
        eurofix.addTag(schwund_tag_,"%.4f"%schwund_fraction_of_what_should_have_been_paid)
    else:
        eurofix.addTag(schwund_tag_)

    eurofix.addDescription("Warenwert im Lager zur Inventur am %s:" % journal[last_good_inventur_transaction_index].getDate().isoformat())
    for lwacct, lwamt in warenwert_lager_letzte_inventur.items():
        eurofix.addDescription(".   %s  ~ %s" % (lwacct, ledger.Amount(lwamt,default_currency_)))
    eurofix.addDescription("Warenwert im Lager zur heutigen Inventur:")
    for lwacct, lwamt in warenwert_lager_diese_inventur.items():
        lwdiff = lwamt - warenwert_lager_letzte_inventur[lwacct]
        lwsign = "+" if lwdiff >= 0 else ""
        if warenwert_lager_letzte_inventur[lwacct] != 0.0:
            lwpct = "%s%.2f%%" % (lwsign, -100*lwdiff / warenwert_lager_letzte_inventur[lwacct])
        else:
            lwpct = ""
        eurofix.addDescription(".   %s  ~ %s\t(%s%d %s)" % (lwacct, ledger.Amount(lwamt,default_currency_),lwsign,lwdiff,lwpct))
    if len(register_previousassert_euro_postings) == 1:
        eurofix.addDescription("Kassastand zu Inventur vom %s: %s" % (journal[last_good_inventur_transaction_index].getDate().isoformat(), ledger.Amount(register_previousassert_euro, default_currency_)))
    eurofix.addDescription("seit letzter Inventur vom %s:" % journal[last_good_inventur_transaction_index].getDate().isoformat())
    eurofix.addDescription(".   erw. Umsatz durch Verkauf: %s" % ledger.Amount(-1*expected_revenue_durch_verkauf_euro, default_currency_))
    if expected_revenue_durch_verkauf_euro != 0:
        eurofix.addDescription(".   Ausgaben für getrunkene(?) Getränke: %s (%.2f%%)" % (ledger.Amount(calculated_expense_fuer_verkauf_euro, default_currency_), -100*(calculated_expense_fuer_verkauf_euro / expected_revenue_durch_verkauf_euro)))
        erwarteter_gewinn = expected_revenue_durch_verkauf_euro+calculated_expense_fuer_verkauf_euro
        eurofix.addDescription(".   erw. Gewinn durch Verkauf: %s (%.2f%%)" % (ledger.Amount(-1*(erwarteter_gewinn), default_currency_), 100*(erwarteter_gewinn / expected_revenue_durch_verkauf_euro)))
    if len(register_previousassert_euro_postings) == 1:
        eurofix.addDescription(".   Summe Kassabucheinträge: %s" % (ledger.Amount(umsatz_zwischen_inventuren_ohne_getränkeerlös_euro, default_currency_)))
        ##denkfehler????
        ##tatsaechlich_eingenommen = register_assert_euro - (register_previousassert_euro + umsatz_zwischen_inventuren_ohne_getränkeerlös_euro)
        ##eurofix.addDescription("\-- tatsächlicher Umsatz mit Verkauf: %s" % (ledger.Amount(tatsaechlich_eingenommen, default_currency_)))
        ##tatsaechlicher_gewinn = tatsaechlich_eingenommen - calculated_expense_fuer_verkauf_euro
        ##eurofix.addDescription("\-- tatsächlicher Gewinn mit Verkauf: %s" % (ledger.Amount(tatsaechlicher_gewinn, default_currency_)))
    eurofix.addDescription("/ errechneter Kassastand ohne theoretischem Verkaufsumsatz: %s" % ledger.Amount(register_current_euro,default_currency_))
    eurofix.addDescription("| Kassastand heute laut Inventur: %s" % ledger.Amount(register_assert_euro,default_currency_))
    eurofix.addDescription("\\ errechneter Kassastand mit theoretischem Verkaufsumsatz: %s" % ledger.Amount(register_current_euro - expected_revenue_durch_verkauf_euro,default_currency_))
    tatsächlicher_umsatz = register_diff_umsatz_euro - umsatz_zwischen_inventuren_ohne_getränkeerlös_euro
    tatsächliche_bareinnahmen = register_diff_umsatz_euro + register_diff_cash_bargeldverwahrung
    eurofix.addDescription("Umsatz neu, bisher nicht im Kassabuch aufgezeichnet: %s" % (ledger.Amount(register_diff_umsatz_euro, default_currency_)))
    eurofix.addDescription("Umsatz seit letzter Inventur inkl Bargeldverwahrung: %s" % (ledger.Amount(tatsächliche_bareinnahmen, default_currency_)))
    eurofix.addDescription("Umsatz seit letzter Inventur inkl allen Kassabuchbewegungen: %s" % (ledger.Amount(tatsächlicher_umsatz, default_currency_)))
    eurofix.addDescription("Gewinn: %s  (bargeldumsatz - einkauf)" % (ledger.Amount(tatsächliche_bareinnahmen-calculated_expense_fuer_verkauf_euro, default_currency_)))
    ## Ausgaben nützen dem realraum
    ## Spenden finanzieren Ausgaben, reduzieren daher den Nutzen des Getränkeverkaufs
    ## Einkaufskosten reduzieren ebenfalls den nutzen/gewinn
    eurofix.addDescription("Nutzen: %s  (bargeldumsatz + ausgaben - spenden - einkauf)" % (ledger.Amount(tatsächlicher_umsatz-calculated_expense_fuer_verkauf_euro, default_currency_)))
    assert(eurofix.isBalanced())

assert(all([t.isBalanced() for t in gewinn_transactions]))

print("; BEGIN autogenerierte Inventurbuchungen")
for t in gewinn_transactions:
    print("\n%s" % (t))
if "eurofix" in globals():
    print("\n%s" % (eurofix))
print("\n; ENDE autogenerierte Inventurbuchungen\n")
#print("\n%s\n" % (problematic_transaction))
