#!/usr/bin/python3
# -*- coding: utf-8 -*-
from ledger import Transaction, Posting, Amount, FutureAmountFraction, sortTransactionsByDate, NoAmount, queryHledgerForAccountList
import re, os, sys, types

default_currency_ = "EUR"
hledger_mainledgerpath_=os.path.split(__file__)[0]+'/../Ledgers/my_main_ledger_which_includes_others.ledger'
invoice_path_ = os.path.abspath(os.path.split(__file__)[0]+'/../Rechnungen/')

unknown_revenue_default_transaction_ = Transaction("receive money").addPosting(Posting("revenue:---UNKNOWN---", None))
unknown_expense_default_transaction_ = Transaction("pay stuff").addPosting(Posting("expenses:---UNKNOWN---", None))
unknown_equity_default_transaction_ = Transaction("do nothing or assert stuff").addPosting(Posting("equity:---ASSERTION---", None))

## This allows you to add some hledger hints into the extra-text when making bank-transfers
## Thus reducing your workflow to entering correct text when making the bank-transfer
## rather than making a bank-transfer, then importing bank-statements and then adding hledger accounts to the transaction
hledger_aware_booking_re_ = re.compile(r"(^|.*\s)"+default_currency_+r"(?:\d+\.\d\d|REST|ALL)\s")
re_booking_w_hledger_info_ = re.compile(default_currency_+r"(-?\d+(?:[.,]\d\d?)?|ALL|REST)\s+(\S+)")
re_booking_w_hledger_invoice_ = re.compile(r"\(([^)]+)\)")
re_booking_w_hledger_tags_ = re.compile(r"([^,:=/ ]+)/([^,:=/ ]*)(?:\s|^|,)")

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
members_sqlite_db_=os.path.split(__file__)[0]+'/../Ledgers/members.sqlite'
#format bis 2016-02-01, ab 2016-02-25:
mitgliedsbeitrag_re = re.compile(r"Mitgliedsbeitrage|Midgliedsbeitrag", re.I)
receive_membership_transaction_name_ = "receive membership-fee"
receive_membership_toplevel_account_ = "assets:current:membership A/R:"

elba_primary_account_ = "assets:current:checking"
donation_feeoverhead_account_ = "revenue:donations:membership"

#Example:
# predefined shorthands for the processHledgerAwareExpense() function below
hledger_aware_booking_account_shorthands = {
    "Camp2015":"expenses:projects:cccamp:2015",
    "supplies-masha":"expenses:projects:supplies-masha",
    ":improveroom":"expenses:projects:improveroom",
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
    return (fee % 30 == 0 and fee <= 15*30)

def getMatchOrDefault(m, gid:int, default:str) -> str:
    if m is None:
        return default
    else:
        return m.group(gid)

## yes, ELBA annoyningly adds a useless space every 70 characters in the description for every tag
def fixELBAescriptionExtraWhitespace(desc):
    max_len_before_elba_inserts_whitespace = 70
    cursor = 0
    while len(desc) >= cursor+max_len_before_elba_inserts_whitespace and desc[cursor+max_len_before_elba_inserts_whitespace] == " ":
        desc = desc[:cursor+max_len_before_elba_inserts_whitespace] + desc[cursor+max_len_before_elba_inserts_whitespace+1:]
        cursor += max_len_before_elba_inserts_whitespace
    return desc

def newestInvoice(fileglob):
    """
    Search for invoice-files matching the fileglob
    @return file-base-name of newest matching file or None
    """
    import glob
    if not isinstance(fileglob, str):
        return None
    fiter = glob.iglob(os.path.join(invoice_path_,"*",fileglob),recursive=True)
    flist = sorted([(os.path.getmtime(f),os.path.basename(f)) for f in fiter])
    return None if len(flist) == 0 else flist.pop()[1]

def lbdAutoTagWithNickname(txntemplate):
    ## return a closure
    return lambda amountCmp, fulltext: autotagTransactionWithNickname(txntemplate(amountCmp, fulltext) if type(txntemplate) == types.FunctionType else txntemplate, fulltext)

transaction_matchors = [
## Revenue
    (mitgliedsbeitrag_re, amountMayBeMembershipFee,
        lambda *xs: membershipFeeIncomeTransactionAndOnlyBookActualFeeDonateRest(*xs)
    ),
    (re.compile(r"HABENZINSEN",re.I), revenueamt,
        Transaction("receive interest").addPosting(Posting("revenue:interest:checking-interest-r3", nix))
    ),
    (re.compile(r"STROM",re.I), revenueamt,
        Transaction("receive excess utility payment").addPosting(Posting("expenses:room:utilities:electric", nix))
    ),
## Expenses
    (hledger_aware_booking_re_, expenseamt,
        lambda a,t: autotagTransactionWithNickname(processHledgerAwareExpense(a,t),t)
    ),
    (re.compile(r"Bar Auszahlung",re.I), expenseamt,
        Transaction("Geld von Konto in Kassa").addPosting(Posting("assets:current:cash:register", nix)).addTag("cash")
    ),
    (re.compile(r"Bargeldeinzahlung am SB-Gerät",re.I), lambda x: x<0 and x>=-4.0,
        lbdAutoTagWithNickname(Transaction("Gebühr Münzzähler").addPosting(Posting("expenses:bank:checking-fees-r3", nix)).addTag("cash"))
    ),
    (re.compile(r"Kontoführung|Entgelt Nichtdurchführung|Pauschale Elba"), expenseamt,
        Transaction("pay bank fees").addPosting(Posting("expenses:bank:checking-fees-r3", nix))
    ),
    (re.compile(r"Buchungsentgelt|Rahmenprovision|Umsatzprovision|MANIPULATIONSENTGELT|DIENSTLEISTUNGSENTGELT|PORTO",re.I), expenseamt,
        Transaction("pay bank fees").addPosting(Posting("expenses:bank:checking-fees-r3", nix))
    ),
    (re.compile(r"SB-Einzahlung",re.I), expenseamt,
        Transaction("Einzahlungsgebühr").addPosting(Posting("expenses:bank:checking-fees-r3", nix))
    ),
    (re.compile(r"SOLLZINSEN",re.I), expenseamt,
        Transaction("pay interest").addPosting(Posting("expenses:interest:checking-interest-r3", nix))
    ),
    (re.compile(r"KEST|Kapitalertragsteuer",re.I), expenseamt,
        Transaction("pay tax").addPosting(Posting("expenses:taxes:kest-r3", nix))
    ),
    (re.compile(r"LPD Steiermark SVA",re.I), expenseamt,
        Transaction("Gebühr Statutenänderung").addPosting(Posting("expenses:taxes:stampduty", nix))
    ),
    (re.compile(r"Miete.*",re.I), expenseamt,
        Transaction("pay rent")
            .addPosting(Posting("expenses:room:rent", nix))
            .setCode(newestInvoice("*hausverwaltung*vorschreibung*pdf"))
    ),
    (re.compile(r"Versicherung",re.I), expenseamt,
        Transaction("pay insurance").addPosting(Posting("expenses:room:insurance", nix))
    ),
    (re.compile(r"STROMNETZ"), expenseamt,
        Transaction("pay utilities (Strom)").addPosting(Posting("expenses:room:utilities:electric", nix))
    ),
]

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
        b = acct.split(":")
        for subacct in [ ":".join(b[x:]) for x in range(0,len(b))]:
            if subacct in newdict:
                duplicates.append(subacct)
            else:
                newdict[subacct] = acct
    for d in set(duplicates):
        try:
            del newdict[d]
        except:
            pass
    ## overwrite newdict values with existing shorthands
    newdict.update(shorthanddict)
    return newdict


elba_field_names_ = sorted(["(?!(?:IBAN|BIC) )Empfänger","(?!(?:IBAN|BIC) )Zahlungsempfänger","(?!(?:IBAN|BIC) )Auftraggeber","IBAN Zahlungsempfänger","IBAN Auftraggeber","BIC Zahlungsempfänger","BIC Auftraggeber", "IBAN Empfänger", "BIC Empfänger","Empfänger-Kennung","Urspr. Empfänger","Urspr. Auftraggeber","Zahlungsreferenz","Mandat","Auftraggeberreferenz","Verwendungszweck"],key=len,reverse=True)
re_generic_elba_tag_ = re.compile(r"(?:\W|^)("+r"|".join(elba_field_names_) +r"):\s((?:.(?!"+r"|".join(elba_field_names_) +"))+)")
elba_extrainfo_neu1_ = re.compile(r"Verwendungszweck:\s((?:.(?!"+r"|".join(elba_field_names_) +"))+)")
elba_extrainfo_neu2_ = re.compile(r"Auftraggeberreferenz:\s((?:.(?!"+r"|".join(elba_field_names_) +"))+)")
def processHledgerAwareExpense(amountCmp, fulltext):
    """
    checks if transaction text is in hledger-aware format
    if so, we can directly parse out the necessary posting accounts and invoice filename
    if transaction text is in the following format, we can immediately parse transfer information from Bank-Transfer-Usage-Text
    Format:
    EUR(\\d+.\\d\\d|REST|ALL) <account1 | account1-shorthand> EUR(\\d+.\\d\\d|REST|ALL) <account2 | account2-shorthand> EUR(\\d+.\\d\\d|REST|ALL) <account3 | account3-shorthand> ..... etc (inovicefile-substring.pdf)
    """
    global hledger_accounts_, hledger_aware_booking_account_shorthands_ext, hledger_accounts_longest_first
    hledger_accounts_ = queryHledgerForAccountList(hledger_mainledgerpath_) if not "hledger_accounts_" in globals() else hledger_accounts_
    hledger_aware_booking_account_shorthands_ext = populateShorthandDictWithHledgerAccounts(hledger_accounts_, hledger_aware_booking_account_shorthands) if not "hledger_aware_booking_account_shorthands_ext" in globals() else hledger_aware_booking_account_shorthands_ext
    hledger_accounts_longest_first = sorted(hledger_accounts_, key=len,reverse=True) if not "hledger_accounts_longest_first" in globals() is None else hledger_accounts_longest_first
    dm1 = elba_extrainfo_neu1_.search(fulltext)
    dm2 = elba_extrainfo_neu2_.search(fulltext)
    # check if elba text has `Verwendungszweck:` sub-field.
    if not dm1 is None:
        # if so: use only text from that field
        text = fixELBAescriptionExtraWhitespace(dm1.group(1))
        if not dm2 is None:
            # if so: use only text from that field
            text += fixELBAescriptionExtraWhitespace(dm2.group(1))
    else:
        # otherwise use full csv field string
        text = fulltext

    ## new blank Transaction
    tout = Transaction()

    ## extract all matches of re_booking_w_hledger_info_ in text into postings and remove those strings from text
    postings = []
    cutout_offset=0
    for m in re_booking_w_hledger_info_.finditer(text):
        postings += [m.group(1,2)]
        text = text[:m.start(0)-cutout_offset] + text[m.end(0)-cutout_offset:]
        cutout_offset += m.end(0) - m.start(0)

    ## parse postings
    rest=None
    amntsum = 0.0
    for (amnttxt, accttxt) in postings:
        acct = None
        accttxt = accttxt.strip()
        # see if accttxt is a pre-defined shorthand for a longer account name
        for shorthand in hledger_aware_booking_account_shorthands_ext.keys():
            if accttxt == shorthand or (accttxt.startswith(shorthand) and accttxt[len(shorthand)] in " \t\n"):
                acct = hledger_aware_booking_account_shorthands_ext[shorthand]
                accttxt = accttxt[len(shorthand):].strip()
                break
        # otherwise: check if account is a known account name
        if acct is None:
            for hacct in hledger_accounts_longest_first:
                if accttxt == hacct or (accttxt.startswith(hacct) and len(accttxt) > len(hacct) and accttxt[len(hacct)] in " \t\n"):
                    acct = hacct
                    accttxt = accttxt[len(acct):].strip()
                    break
        # otherwise, finally: use the given account verbatim. May be a new account name or is to be edited later.
        # Preserve the rest of the string for later
        if acct is None:
            acct = accttxt.split(" ")[0]
            accttxt = accttxt[len(acct):].strip()
        # if len(accttxt)>0:
        #         tout.setName(" ".join(filter(len,[accttxt,tout.name])))
        if amnttxt == "REST" or amnttxt == "ALL":
            if rest:
                # raise Exception("can only have ONE REST or ALL")
                raise Exception("can only have ONE REST or ALL: " + fulltext)
            rest = acct
            amnt = None
        else:
            amnt = float(amnttxt.replace(",","."))
            amntsum += amnt
            tout.addPosting(Posting(acct, Amount(amnt, default_currency_)))

    if rest:
        amnt = -1 * round(amntsum + amountCmp,4)
        tout.addPosting(Posting(rest, Amount(amnt, default_currency_)))
    else:
        if not (amountCmp == -1 * amntsum):
            raise Exception(f"Error: {amountCmp} =! {-1*amntsum} in line: {fulltext}") 

    # now add invoice-code and tags
    # if it was a hledger aware posting
    if postings:
        invf_strs = []
        cutout_offset=0
        # find all occurances of `(invoice)`
        for invg in re_booking_w_hledger_invoice_.finditer(text):
            invf_str = newestInvoice("*" + invg.group(1).strip().replace(" ", "*").replace("-","*") + "*")
            if invf_str is not None:
                invf_strs.append(invf_str)
                ## cut out found invoice from name to process
                text = text[:invg.start(0)-cutout_offset]+text[invg.end(0)-cutout_offset:]
                cutout_offset = invg.end(0) - invg.start(0)

        if invf_strs:
            tout.setCode(",".join(invf_strs))

        ## add tags to Transaction if present in form: `,a/b or ,c/ or d/e,f/,g/h`
        cutout_offset=0
        for tagm in re_booking_w_hledger_tags_.finditer(text):
            tout.addTag(tagm.group(1).strip(), tagm.group(2).strip())
            text = text[:tagm.start(0)-cutout_offset]+text[tagm.end(0)-cutout_offset:]
            cutout_offset = tagm.end(0) - tagm.start(0)

    # set transaction description from rest of text
    tout.setName(text.strip())
    if len(tout.name) == 0:
        tout.setName("hledger-aware parsed expense")

    return tout

nonascii_re = re.compile(r"[^[:ascii:]]")
def buildRegExpFromName(name):
    name = nonascii_re.sub(".",name.lower())
    names_list = name.split(" ")
    na = itertools.permutations(names_list)
    if len(names_list) > 2:
        ## also match with removed middle names, as they might not be on bank account name
        na = list(na) + list(itertools.permutations([names_list[0],names_list[-1]]))
    return r"(?:"+r"|".join([r"(?:\s*|\W+|..+)".join(p) for p in na])+r")"

def buildRegExToMemberDict(): # -> [ [regex, str, str, Optional(float)] ] # (list in order of priority)
    try:
        con = lite.connect(members_sqlite_db_)
        cur = con.cursor()
        cur.execute('select p_name, p_nick, m_fee as m_most_recent_fee, w_searchregex, max(m_firstmonth), (select c_contact from contact where ct_id=6 and contact.p_id=persons.p_id) as "iban" from persons left join membership using (p_id) left join "wiretransferregex" using (p_id) group by p_id')
        list_custom_regex = [] # will get highest prio. we assume it's highly specific
        list_iban_regex = []
        list_name_regex = []
        list_nick_regex = [] # will get lowest prio. Has shortest string, low specificity

        rows = cur.fetchall()
        for row in rows:
            (p_name, p_nick, m_most_recent_fee, w_searchregex, m_firstmonth, iban) = row
            if p_name is not None:
                list_name_regex.append( (re.compile(buildRegExpFromName(p_name),re.I), p_name, p_nick, m_most_recent_fee) )
                if w_searchregex is not None:
                    list_custom_regex.append( (re.compile(w_searchregex,re.I), p_name, p_nick, m_most_recent_fee) )
                if iban is not None and len(iban) > 0:
                    list_iban_regex.append( (re.compile(r"(?:^|\W|\s)IBAN\sAuftraggeber:\s+"+iban.upper()+r"(?:$|\W|\s)"), p_name, p_nick, m_most_recent_fee) )
                if p_nick is not None:
                    list_nick_regex.append( (re.compile(r"(?:^|\W|\s)"+nonascii_re.sub(".",p_nick.lower())+r"(?:$|\W|\s)",re.I), p_name, p_nick, m_most_recent_fee) )

        return list_custom_regex + list_iban_regex + list_name_regex + list_nick_regex

    except (lite.Error) as e:
        print("Error %s:" % e.args[0])
        sys.exit(1)

def membershipFeeIncomeTransactionAndOnlyBookActualFeeDonateRest(amountCmp, fulltext):
    ## go through list in order of regex-specificty
    for regex, fullname, nickname, most_recent_fee in regexp_to_member_priority_list_:
        if regex.search(fulltext):
            ## match found
            if most_recent_fee is not None and most_recent_fee > 0 and amountCmp % most_recent_fee > 0 and amountCmp > most_recent_fee and amountCmp < most_recent_fee*2:
                ## assume the extra money is a donation (because extra space is being used, etc)
                ## book only the expected membership fee and the extra as donation
                return Transaction(receive_membership_transaction_name_).addPosting(Posting(receive_membership_toplevel_account_ + fullname, Amount(-1*most_recent_fee, default_currency_))).addPosting(Posting(donation_feeoverhead_account_, nix))
            else:
                ## book full amount as membership fee
                return Transaction(receive_membership_transaction_name_).addPosting(Posting(receive_membership_toplevel_account_ + fullname, nix))
    return None ## no membership fee after all


def autotagTransactionWithNickname(txn_template: Transaction, fulltext: str) -> Transaction | None:
    ## go through list in order of regex-specificty
    if txn_template is None:
        return None
    if type(txn_template) == types.FunctionType:
        assert(False) ## not supported
    if isinstance(txn_template, Transaction):
        for regex, fullname, nickname, most_recent_fee in regexp_to_member_priority_list_:
            if regex.search(fulltext):
                ## match found
                return txn_template.copy().addTag("person", nickname) ## the copy is very important!! otherwise we update the Template
    return txn_template.copy()


regexp_to_member_priority_list_ = buildRegExToMemberDict()



########### Number26 Config ###################
# n26_primary_account_ = "assets:current:checking-n26"

########## Matchors

###
###  Transaction can be matched and processed in the following way:
###  lambda t: t[key].startswith("test") and expenseamt(t["Amount"]) : Transaction(),
###

# n26_transaction_matchors = [
#    lambda t: "key" in t and revenueamt(t["Amount"]):Transaction("receive interest").addPosting(Posting("revenue:interest:checking-interest-raika", nix)),
#    lambda t: "merchantName".startsWith("power") and revenueamt(t["Amount"]):Transaction("receive excess utility payment").addPosting(Posting("expenses:utilities:electric", nix)),
# ]
########## END Matchors


