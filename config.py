#!/usr/bin/python3
# -*- coding: utf-8 -*-
from ledger import Transaction, Posting, Amount, FutureAmountFraction, sortTransactionsByDate, NoAmount, queryHledgerForAccountList
import re, os

#
#example configuration
#

default_currency_ = "EUR"
hledger_mainledgerpath_=os.path.split(__file__)[0]+'/../Ledgers/my_main_ledger_which_includes_others.ledger'

unknown_revenue_default_transaction_ = Transaction("receive money").addPosting(Posting("revenue:---UNKNOWN---", None))
unknown_expense_default_transaction_ = Transaction("pay stuff").addPosting(Posting("expenses:---UNKNOWN---", None))
unknown_equity_default_transaction_ = Transaction("do nothing or assert stuff").addPosting(Posting("equity:---ASSERTION---", None))

nix = NoAmount()
anyamt = lambda a: True
expenseamt = lambda a: a < 0.00
revenueamt = lambda a: a > 0.00
equityamt = lambda a: a == 0


########### Monefy Config ###################

# in case we want to log cash withdrawls in Monefy
# we don't want to import them twice, if we already have
# transactions for the cash withdrawls from the bank csv exports
monefy_ignore_accounts_ = ["assets:current:checking","assets:current:checking2"]

#Dict to transform Monefy Account names to hledger accounts
# Example: We can buy stuff either with cash or a credit card
monefy_account_shorthands = {
    "VISA":"liability:visa",
    "Cash":"assets:current:cash",
    "Elba":"assets:current:checking",
    "N26":"assets:current:checking2",
    }

#Dict: Categories we spend money on ---> hledger accounts money goes to
# Example
monefy_category_shorthands = {
    "Kino":"expenses:kino",
    "restaurant":"expenses:restaurant",
    "groceries":"expenses:groceries",
}


########### ELBA Config ###################
import sqlite3 as lite
import itertools

elba_primary_account_ = "assets:current:checking"

#Example:
# predefined shorthands for the processHledgerAwareExpense() function below
hledger_aware_booking_account_shorthands = {
    "Camp2015":"expenses:projects:cccamp:2015",
    "supplies-masha":"expenses:projects:supplies-masha",
    }

########## Matchors

###
###  Transaction can be matched and processed in the following way:
###  (regex, amount_guard_function(amt)) : Transaction()
###  (regex, amount_guard_function(amt)) : (lambda amount, description : Transaction())
###

#Example:
# example custom amount guard function. in this case checkig if an incoming amount might be a hackerspace membership fee
def amountMayBeMembershipFee(fee):
    return fee == 30 or fee == 15 or (fee % 25 == 0 and fee <= 300)

hledger_aware_booking_re = re.compile(r"(^|.*\s)"+default_currency_+r"(?:\d+\.\d\d|REST|ALL)\s")

##Examples:
transaction_matchors = {
## Revenue
    (re.comepile(r"^MemberShipFee from"), amountMayBeMembershipFee):lambda *xs: Custom_Function_That_Returns_An_Transaction(*xs),
    (re.compile(r"HABENZINSEN"), revenueamt):Transaction("receive interest").addPosting(Posting("revenue:interest:checking-interest", nix)),
    (re.compile(r"STROM",re.I), revenueamt):Transaction("receive excess utility payment").addPosting(Posting("expenses:room:utilities:electric", nix)),

## Expenses
    (hledger_aware_booking_re, expenseamt): lambda *x: processHledgerAwareExpense(*x),
    (re.compile(r"ENTGELT FUER KONTOFÜHRUNG|KONTOFUEHRUNG|Entgelt Nichtdurchführung"),expenseamt):Transaction("pay bank fees").addPosting(Posting("expenses:bank:checking-fees", nix)),
    (re.compile(r"(ENTGELT FÜR BUCHUNGEN|MANIPULATIONSENTGELT|DIENSTLEISTUNGSENTGELT|PORTO|UMSATZPROVISION)"),expenseamt):Transaction("pay bank fees").addPosting(Posting("expenses:bank:checking-fees", nix)),
    (re.compile(r"SOLLZINSEN",re.I),expenseamt):Transaction("pay interest").addPosting(Posting("expenses:interest:checking-interest-r3", nix)),
    (re.compile(r"KEST",re.I),expenseamt):Transaction("pay tax").addPosting(Posting("expenses:taxes:kest", nix)),
    (re.compile(r"Miete",re.I),expenseamt):Transaction("pay rent").addPosting(Posting("expenses:room:rent", nix)),
    (re.compile(r"Versicherung",re.I),expenseamt):Transaction("pay insurance").addPosting(Posting("expenses:room:insurance", nix)),
    (re.compile(r"STROM|VERBUND|myElectric|EnergieGraz|200086049501\sEINZUG",re.I),expenseamt):Transaction("pay utilities").addPosting(Posting("expenses:room:utilities:electric", nix)),
}

#### Custom Helper Functions And Transaction generators ####

### generate shorthands from list of accounts according to regex .*:([^:]+)
def populateShorthandDictWithHledgerAccounts(acctlist, shorthanddict):
    newdict = {}
    assert(isinstance(acctlist,list))
    assert(isinstance(shorthanddict,dict))
    duplicates = []
    for acct in acctlist:
        if len(acct) < 5:
            continue
        lastaname = acct.split(u":")[-1]
        if lastaname in newdict:
            duplicates.append(lastaname)
        else:
            newdict[lastaname] = acct
    for d in set(duplicates):
        try:
            del newdict[d]
        except:
            pass
    ## overwrite newdict values with existing shorthands
    newdict.update(shorthanddict)
    return newdict


### if transaction text is in the following format, we can immediately parse transfer information from Bank-Transfer-Usage-Text
### Format: EUR(\d+.\d\d|REST|ALL) <account1 | account1-shorthand> EUR(\d+.\d\d|REST|ALL) <account2 | account2-shorthand> EUR(\d+.\d\d|REST|ALL) <account3 | account3-shorthand> ..... etc
re_booking_w_hledger_info = re.compile(r"(\d+\.\d\d|ALL|REST)\s+(.+)")
elba_extrainfo_optional_textseparators_ = re.compile(r"^(.*?)\s*(ÜBERWEISUNG|INTERNET-ÜW|Überweisung/Dauerauftrag|DAUERAUFTRAG|EINZUG)\s*(.*)$")
def processHledgerAwareExpense(amountCmp, fulltext):
    global hledger_accounts_, hledger_aware_booking_account_shorthands, hledger_accounts_longest_first
    hledger_accounts_ = queryHledgerForAccountList(hledger_mainledgerpath_) if not "hledger_accounts_" in globals() else hledger_accounts_
    hledger_aware_booking_account_shorthands = populateShorthandDictWithHledgerAccounts(hledger_accounts_,hledger_aware_booking_account_shorthands) if not "hledger_aware_booking_account_shorthands" in globals() else hledger_aware_booking_account_shorthands
    hledger_accounts_longest_first = sorted(hledger_accounts_, key=len,reverse=True) if not "hledger_accounts_longest_first" in globals() is None else hledger_accounts_longest_first

    dm = elba_extrainfo_optional_textseparators_.match(fulltext)
    if not dm is None:
        text, other, sendertext = dm.group(1,2,3)
    else:
        text, other, sendertext = (fulltext,"","")

    tout = Transaction()
    postings = map(lambda x: re_booking_w_hledger_info.match(x).group(1,2),
        filter(re_booking_w_hledger_info.match, text.split(default_currency_)[1:]) #safely drop first list item which is empty text or the sender information
        )
    rest=None
    amntsum = 0.0
    for (amnttxt, accttxt) in postings:
        acct = None
        accttxt = accttxt.strip()
        for shorthand in hledger_aware_booking_account_shorthands.keys():
            if accttxt == shorthand or (accttxt.startswith(shorthand) and accttxt[len(shorthand)] in " \t\n"):
                acct = hledger_aware_booking_account_shorthands[shorthand]
                accttxt = accttxt[len(shorthand):].strip()
                break
        if acct is None:
            for hacct in hledger_accounts_longest_first:
                if accttxt == hacct or (accttxt.startswith(hacct) and len(accttxt) > len(hacct) and accttxt[len(hacct)] in " \t\n"):
                    acct = hacct
                    accttxt = accttxt[len(acct):].strip()
                    break
        if acct is None:
            acct = accttxt.split(" ")[0]
            accttxt = accttxt[len(acct):].strip()
        if len(accttxt)>0:
                tout.setName(" ".join(filter(len,[accttxt,tout.name])))
        if amnttxt == "REST" or amnttxt == "ALL":
            if rest:
                raise Exception("can only have ONE REST or ALL")
            rest = acct
            amnt = None
        else:
            amnt = float(amnttxt)
            amntsum += amnt
            tout.addPosting(Posting(acct, Amount(amnt, default_currency_)))

    if rest:
        amnt = -1 * round(amntsum + amountCmp,4)
        tout.addPosting(Posting(rest, Amount(amnt, default_currency_)))
    else:
        assert(amountCmp == -1 * amntsum)

    if len(tout.name) == 0:
        tout.setName("ELBA parsed expense")
    return tout



########### Number26 Config ###################
n26_primary_account_ = "assets:current:checking2"

########## Matchors

###
###  Transaction can be matched and processed in the following way:
###  ([(key, value_test_function(value))], amount_guard_function(amt)) : Transaction()
###  ... if all keys exist in jsontrsc and all values statisfy the given value_test_function() the matchor matches if amount also matches amount_guard_function()
###

n26_transaction_matchors = [
#    [("",lambda x: True)]:Transaction("receive interest").addPosting(Posting("revenue:interest:checking-interest-raika", nix)),
#    [("",lambda x: x == "power")]::Transaction("receive excess utility payment").addPosting(Posting("expenses:utilities:electric", nix)),
]
########## END Matchors


