#!/usr/bin/python3
# -*- coding: utf-8 -*-

import re
import sys, os, io
import csv
import time
import itertools
import datetime
import codecs
import types
import hashlib
import glob
from pathlib import Path, PurePath
from ledger import Transaction, Posting, Amount, FutureAmountFraction, sortTransactionsByDate, NoAmount, queryHledgerForAccountList, parseAmount, re_amount_str_3captures, TransactionUnbalancedError

#################### BEGIN CONFIG ##########################
#elba_posting_date_ = re.compile(r"([0-3]\d\.[0-1]\d)\s?UM [0-2]\d[:.][0-5]\d|\s([0-3]\d\.[0-1]\d\.\d\d)\sK\d\s[0-2]\d:[0-5]\d|([0-3]\d\.[0-1]\d\.\d\d)\s[0-2]\d:[0-5]\dK\d")
date_ignore_re = re.compile(r"Vorgemerkte Buchung")
max_history_age_to_filter_duplicates_from_days_ = 5*365

from config import *
#################### CONFIG END ##########################

def createUniqueTransactionID(date_dt, description_txt, date2_dt, amount_flt, currency_txt, precise_date):
    exclude_words = [x.lower() for x in ["empfänger:", "verwendungszweck:", "zahlungsreferenz:","auftraggeber:"]]
    description_lst = description_txt.split()
    currency_txt = currency_txt.strip()
    assert(all([i == i.strip() for i in description_lst]))
    assert(all([len(i) > 0 for i in description_lst]))
    description_lst = [i.lower() for i in description_lst]
    description_lst = [i for i in description_lst if i not in exclude_words]
    description_lst.sort()
    final_list = [date_dt.isoformat(),date2_dt.isoformat(),currency_txt,"%.4f"%amount_flt]+description_lst
    unique_str = "|".join(final_list)
    return unique_str

def createHash(mystr):
    myhash = hashlib.sha256()
    myhash.update(mystr.encode("utf-8"))
    return myhash.hexdigest()

def parseCSVrow(row):
    try:
        (date,description,date2,amountCmp,currency,precise_date,*rest) = row
    except:
        raise ValueError("Error parsing CSV file. Not CSV or CSV with less than 6 columns!")
    try:
        date = datetime.datetime.strptime(date,"%d.%m.%Y").date()
    except ValueError:
        date = datetime.datetime.strptime(date,"%d.%m.%y").date()
    try:
        date2 = datetime.datetime.strptime(date2,"%d.%m.%Y").date()
    except ValueError:
        date2 = datetime.datetime.strptime(date2,"%d.%m.%y").date()
    try:
        precise_date = datetime.datetime.strptime(precise_date,"%d.%m.%Y %H:%M:%S:%f")
    except ValueError:
        raise ValueError(f"Error converting precise_date in: {row}")
    amountCmp = float(amountCmp.replace(",","."))
    return date,description,date2,amountCmp,currency,precise_date,rest

def generateDatabaseOfAlreadyImportedTransactionIDs(file_list):
    global txdb
    txdb = {}

    def _buildTXIDDatabase(csvfile):
        global txdb
        for row in csvfile:
            date,description,date2,amountCmp,currency,precise_date,rest = parseCSVrow(row)
            row_uid = createUniqueTransactionID(date,description,date2,amountCmp,currency,precise_date)
            txdb[row_uid]=True

    for argfile in file_list:
        runFunctionOnCSV(_buildTXIDDatabase, argfile)
    return txdb

def guessEncoding(file_path):
    try_encodings=["utf-8-sig","utf-8","latin1"]
    for encoding in try_encodings:
        try:
            with open(file_path,"r",encoding=encoding) as fh:
                fh.read()
                return encoding
        except UnicodeDecodeError:
            pass
    return "utf-8-sig"

def runFunctionOnCSV(fun, file_path):
    if file_path.is_file():
        encoding = guessEncoding(file_path)
        with open(file_path,"r",encoding=encoding,newline='') as csvfh:## we remove the BOM in import-elba-csv-directory
            csvfile = csv.reader((line.replace('\0','') for line in csvfh),delimiter=';', quotechar='"')
            return fun(csvfile)

    else:
        raise IOError("%s is not a file" % file_path)

def parseAssertAmt(string):
    if isinstance(string,str) and len(string) > 0:
        re_amt = re.compile(re_amount_str_3captures)
        final_assert_m = re_amt.match(string.strip())
        if not final_assert_m is None:
            assertamt = parseAmount(*final_assert_m.group(1,2,3))
            return assertamt
    return None

def addAssertToAndSortTransactions(transactions, assertamt):
    transactions = sortTransactionsByDate(transactions)

    if assertamt and len(transactions) > 0:
        transactions[-1].postings[0].addPostPostingAssertAmount(assertamt)

    return transactions

def printTransactionsWithAssert(transactions, assertamt):
    print("\n\n".join(map(str,(addAssertToAndSortTransactions(transactions, assertamt)))), end="\n\n")

def escapeELBAescriptionComma(desc):
    return desc.replace(",","%2C") ## make sure no `,` remain in description, as this will confuse our ledger.py's current tag implementation on re-parsing later

re_iban_dst_ = re.compile(r"\WIBAN (?:Zahlungsempfänger|Empfänger): ([A-Z]{2}[0-9]{2}[0-9A-Z]{16,25})")
re_iban_src_ = re.compile(r"\WIBAN Auftraggeber: ([A-Z]{2}[0-9]{2}[0-9A-Z]{16,25})")
re_bic_dst_ = re.compile(r"\WBIC (?:Zahlungsempfänger|Empfänger): ((?:[a-zA-Z]{6})(?:(?:[2-9a-zA-Z]{1})(?:[0-9a-np-zA-NP-Z]{1}))(?:(?:(?:[0-9a-wy-zA-WY-Z]{1})([0-9a-zA-Z]{2}))|([xX]{3})|))")
re_bic_src_ = re.compile(r"\WBIC Auftraggeber: ((?:[a-zA-Z]{6})(?:(?:[2-9a-zA-Z]{1})(?:[0-9a-np-zA-NP-Z]{1}))(?:(?:(?:[0-9a-wy-zA-WY-Z]{1})([0-9a-zA-Z]{2}))|([xX]{3})|))")
re_kennung_dst_ = re.compile(r"\WEmpfänger-Kennung: ([A-Z0-9]{18})")
## all know elba field names, sorted by longest strings first
elba_field_names_ = sorted(["(?!(?:IBAN|BIC) )Empfänger","(?!(?:IBAN|BIC) )Zahlungsempfänger","(?!(?:IBAN|BIC) )Auftraggeber","IBAN Zahlungsempfänger","IBAN Auftraggeber","BIC Zahlungsempfänger","BIC Auftraggeber", "IBAN Empfänger", "BIC Empfänger","Empfänger-Kennung","Urspr. Empfänger","Urspr. Auftraggeber","Zahlungsreferenz","Mandat","Auftraggeberreferenz","Verwendungszweck"],key=len,reverse=True)
re_generic_elba_tag_ = re.compile(r"(?:\W|^)("+r"|".join(elba_field_names_) +r"):\s((?:.(?!"+r"|".join(elba_field_names_) +"))+)")
re_tagname_not_allowed_chars_ = re.compile(r"(?:\s|:|,)+")
def autoTagFromELBAFieldsReturnShortenedDescription(txn: Transaction, description: str) -> tuple[Transaction, str]:

    m_iban_dst = re_iban_dst_.search(description)
    if not m_iban_dst is None:
        txn.addTag("IBANdst",escapeELBAescriptionComma(fixELBAescriptionExtraWhitespace(m_iban_dst.group(1))))
        txn.addTag("dir","out")
        description = re_iban_dst_.sub("",description, count=1)
    m_iban_src = re_iban_src_.search(description)
    if not m_iban_src is None:
        txn.addTag("IBANsrc",escapeELBAescriptionComma(fixELBAescriptionExtraWhitespace(m_iban_src.group(1))))
        txn.addTag("dir","in")
        description = re_iban_src_.sub("",description, count=1)
    m_bic_dst = re_bic_dst_.search(description)
    if not m_bic_dst is None:
        txn.addTag("BICdst",escapeELBAescriptionComma(fixELBAescriptionExtraWhitespace(m_bic_dst.group(1))))
        description = re_bic_dst_.sub("",description, count=1)
    m_bic_src = re_bic_src_.search(description)
    if not m_bic_src is None:
        txn.addTag("BICsrc",escapeELBAescriptionComma(fixELBAescriptionExtraWhitespace(m_bic_src.group(1))))
        description = re_bic_src_.sub("",description, count=1)
    m_kennung_dst = re_kennung_dst_.search(description)
    if not m_kennung_dst is None:
        txn.addTag("KennungDst",escapeELBAescriptionComma(fixELBAescriptionExtraWhitespace(m_kennung_dst.group(1))))
        description = re_kennung_dst_.sub("",description, count=1)

    ## now parse the rest into tags
    offset_of_removed = 0
    for elba_match in re_generic_elba_tag_.finditer(description):
        ## remove all non allowed characters from tagname 
        tagname = re_tagname_not_allowed_chars_.sub("",elba_match.group(1))
        tagvalue = escapeELBAescriptionComma(fixELBAescriptionExtraWhitespace(elba_match.group(2).strip()))
        prev_value = txn.getTag(tagname)
        if not prev_value is None:
            tagvalue = prev_value+" "+tagvalue
        txn.addTag(tagname, tagvalue)
        ## cut out parsed value
        description = description[:elba_match.start(0)-offset_of_removed]+description[elba_match.end(0)-offset_of_removed:]
        offset_of_removed += elba_match.end(0) - elba_match.start(0)

    return (txn, description)

def makeLedgerTransactionFromCSVFile(already_imported_db, csvfile):
    #print(regexp_to_member)
    transactions = []
    already_seen_skip_count = 0
    for row in csvfile:
        new_transaction = None
        (date, description, date2, amountCmp, currency, precise_date, rest) = parseCSVrow(row)
        tx_uid = createUniqueTransactionID(date,description,date2,amountCmp,currency,precise_date)
        tx_hash = createHash(tx_uid)

        if tx_uid in already_imported_db:
            already_seen_skip_count += 1
            # print("Skipping previously imported line: %s\n" % row, file=sys.stderr)
            continue

        ## search for match and convert to Transaction
        matching_matchors = []
        for (p_re, amt_guard, potential_transaction_or_function_returning_transaction) in transaction_matchors:
            if not amt_guard(amountCmp):
                continue
            m = p_re.search(description)
            if m:
                matching_matchors.append( ( m.end() - m.start() , potential_transaction_or_function_returning_transaction ) )

        for match_length, potential_transaction_or_function_returning_transaction in matching_matchors:
            if isinstance(potential_transaction_or_function_returning_transaction, Transaction):
                # copy template transaction from config.py
                new_transaction = potential_transaction_or_function_returning_transaction.copy()
                break
            elif type(potential_transaction_or_function_returning_transaction) == types.FunctionType:
                # run function from config.py to generate new txn
                new_transaction = potential_transaction_or_function_returning_transaction(amountCmp, description)
                if isinstance(new_transaction, Transaction):
                    # if function returned valid txn, we are done. If function returns error or None, continue
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

        # extract common elba stuff from description and put into tags
        new_transaction, description = autoTagFromELBAFieldsReturnShortenedDescription(new_transaction, description)
        # add all other infos: amount, description, date
        new_transaction.prependPosting(Posting(elba_primary_account_, Amount(amountCmp,currency))).addComment(description).setDate(date)

        ## add "now-imported" hash
        new_transaction.addTag("csvsha256",tx_hash)

        transactions.append(new_transaction)


    not_balanced = [t for t in transactions if not t.isBalanced()]
    if len(not_balanced) > 0:
        raise TransactionUnbalancedError("ERROR: the following transactions are not balanced !!\n"+"\n\n".join(map(str,(sortTransactionsByDate(not_balanced)))))
    assert(len(not_balanced) == 0)

    return transactions, already_seen_skip_count

def getCSVExportDateFromFilename(filepath):
    try:
        return datetime.datetime.strptime(filepath.name[:16],"%Y-%m-%d_%H:%M") 
    except:
        return datetime.datetime.fromtimestamp(filepath.stat().st_mtime)


##### Main ####
if __name__ in {"__main__", "__mp_main__"}:
    if len(sys.argv) < 3:
        print("Usage: %s <current checking balance> <file1> [.. <fileN>]" % (sys.argv[0],), file=sys.stderr)
        sys.exit(1)

    ## make iterator of *.csv files in imported dir not older than 1,2 years
    now = datetime.datetime.now()
    scriptdir = os.path.split(sys.argv[0])[0]
    elba_previously_imported_dir = "../Umsätze/elba/imported/"
    already_imported_csvfiles = (fp for fp in 
        Path(scriptdir,elba_previously_imported_dir).glob("**/*.csv",case_sensitive=False) 
        if now - getCSVExportDateFromFilename(fp) < datetime.timedelta(days=max_history_age_to_filter_duplicates_from_days_)
        )
    already_imported_txids = generateDatabaseOfAlreadyImportedTransactionIDs(already_imported_csvfiles)

    transactions = []
    num_skipped_already_imported = 0
    assertamt = parseAssertAmt(sys.argv[1])
    for argfile in sys.argv[2:]:
        n_t, n_s = runFunctionOnCSV(lambda csvfile: makeLedgerTransactionFromCSVFile(already_imported_txids,csvfile), Path(argfile))
        transactions += n_t
        num_skipped_already_imported += n_s
        # add just imported txids to already imported set to avoid duplicates within multiple new files
        # the reason we do this here, after the file has been fully processed and not within the makeLedgerTransactionFromCSVFile function
        # is, that if we did it within that function, we would skip duplicates within the same file, which is not desired
        # as duplicates within the same file, can only happen if the bank exports it like this, meaning our duplicate checking method is
        # more likely to be incorrect than the duplicates being an error
        already_imported_txids.update(generateDatabaseOfAlreadyImportedTransactionIDs([Path(argfile)]))
    printTransactionsWithAssert(transactions, assertamt)
    # print(f"# Skipped {num_skipped_already_imported} already imported transactions.", file=sys.stderr)

