#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) Bernhard Tittelbach, 2016

import ledger
import os, sys
from collections import defaultdict
import glob
import csv
from pathlib import Path
import dominate
from dominate.tags import *
import getopt
from typing import Set, List, Optional

hledger_ledgerpath_ = os.path.split(__file__)[0]+'/../Ledgers/r3.ledger'
#invoice_path_ = os.path.abspath(os.path.split(__file__)[0]+'/../Rechnungen/')
invoice_path_ = os.path.relpath(os.path.split(__file__)[0]+'/../Rechnungen/')
show_only_accounts_with_these_roots_ = ["expense", "revenue"]
inventory_destination_accounts_ = ["assets:current:inventory-edibles", "assets:current:inventory-materials"]
inventory_source_accounts_ = ["revenue:sales", "expenses:shrinkage"]
inventory_expense_accounts_ = ["expenses:sales"]
INVOICE_TAG_NAME_ = "invoice"

def sgn(a):
    if a > 0:
        return 1.0
    elif a < 0:
        return -1.0
    else:
        return 0

columnnumber_ = 0
def nextcolumnnumber():
    global columnnumber_
    yield columnnumber_
    columnnumber_+=1
columns_={}

def find_invoice_files_from_tags(tx: ledger.Transaction) -> list[Path]:
    """
        Search for invoice-files give in transaction tags `invoice` or `invoicesubstr`
        @returns [Path | str] list of found file paths or not-found codes
    """
    if not isinstance(tx, ledger.Transaction):
        return []

    filepaths_list:List[Path] = []
    for iv in tx.getTagList(INVOICE_TAG_NAME_):
        filepaths_list += Path(invoice_path_).glob("**/"+iv.strip())

    ## make relative
    filepaths_list = [fpath.relative_to(Path(invoice_path_)) for fpath in filepaths_list]

    return filepaths_list

def findFileMatchingInvoiceCode(code):
    """
        Search for invoice-files matching the invoice code and return (list of tuples (file,code) that were codes that are files, list of not-file codes)
        @returns ([(filepath,name)],[rest])
    """
    if not isinstance(code, str):
        return ([],[])  #(list of files, list of codes that are not files)
    notfiles_code_list=[]
    filepaths_with_name_list=[]
    fnames=[]
    flist = glob.glob(os.path.join(invoice_path_,"*",code.strip()),recursive=True)
    ## append found files with exact name to list
    filepaths_with_name_list += [(filepath, code) for filepath in flist]

    ## nothing found? maybe extensions was left out? try searching with .???
    if len(filepaths_with_name_list) == 0 and "." not in code[-5:]:
        flist = glob.glob(os.path.join(invoice_path_, "*", code.strip()+os.path.extsep+"???"),recursive=True)
        filepaths_with_name_list += [(filepath, code+os.path.splitext(filepath)[1]) for filepath in flist]

    ## still no match? maybe it's multiple files, separated by ','
    if len(filepaths_with_name_list) == 0 and "," in code:
        for scode in code.split(","):
            sflist = glob.glob(os.path.join(invoice_path_,"*",scode.strip()),recursive=True)
            filepaths_with_name_list += [(filepath, scode) for filepath in sflist]
            if len(sflist) == 0 and "." not in scode[-5:]:
                ## maybe extensions was left out? try searching with .???
                sflist = glob.glob(os.path.join(invoice_path_,"*",scode.strip()+os.path.extsep+"???"),recursive=True)
                filepaths_with_name_list += [(filepath, scode+os.path.splitext(filepath)[1]) for filepath in sflist]
            if len(sflist) == 0:
                notfiles_code_list += [scode]
    ## maybe the code is a code that is part of several files?
    ## e.g. Transaction: 2019/07/18  (Amazon429) Duct Tape Einkauf
    ## would match files "Rechnung_1_(Amazon429).pdf" and "2019-07-18_Amazon_ZweiteRechnung_(Amazon429).pdf"
    if len(filepaths_with_name_list) == 0 and len(code) >= 4:
        flist = glob.glob(os.path.join(invoice_path_,"*","*[(_-]%s[)_-]*" % code),recursive=True)
        if len(flist) <= 10:
            ## only add if machtes are not too generic
            filepaths_with_name_list += [(filepath, os.path.basename(filepath)) for filepath in flist]
    ## finally try wider match for single file
    if len(filepaths_with_name_list) == 0:
        flist = glob.glob(os.path.join(invoice_path_,"*","*%s*" % code),recursive=True)
        filepaths_with_name_list += [(filepath, os.path.basename(filepath)) for filepath in flist]
    ## still no file found? then it's a code that is not a filename
    if len(filepaths_with_name_list) == 0:
        notfiles_code_list = [code]
    return (list(filepaths_with_name_list), notfiles_code_list)


def codeToFileURI(t):
    """
        Search for invoice-files matching the invoice code and text for inclusion in CSV
    """
    fnames, remaining_codes_list = findFileMatchingInvoiceCode(t.code)
    return "\n".join(remaining_codes_list + [ Path(os.path.abspath(fn[0])).as_uri() for fn in fnames] + [ fn.as_uri() for fn in find_invoice_files_from_tags(t)])


def codeToHTMLLinks(t):
    """
        Search for invoice-files matching the invoice code and return html objects
    """
    fnlist, remaining_codes_list = findFileMatchingInvoiceCode(t.code)
    fnlist += [str(f) for f in find_invoice_files_from_tags(t)]
    if len(fnlist) == 0 and len(remaining_codes_list) == 0:
        return ""
    ulist = ul()
    with ulist:
        for filepath,filename in fnlist:
            li(a(filename,href=Path(filepath),target="_blank"))
        for restcode in remaining_codes_list:
            if restcode in ["TODO","Rechnung fehlt","missing","MISSING","no mail received"]:
                li(span(restcode,style="color:red;"))
            else:
                li(restcode)
    return ulist

def printhelp():
    print("%s <option> [hledger filter options]")
    print("\t--help\t\tShow Help")
    print("\t--html\t\tOutput HTML List to StdOut")
    print("\t--csv\t\tOutput CSV List to StdOut")


############## MAIN #####################

try:
    opts, args = getopt.getopt(sys.argv[1:], "chmi", ["help", "csv", "html","inventory"])
except getopt.GetoptError as err:
    # print help information and exit:
    print(err)  # will print something like "option -a not recognized"
    usage()
    sys.exit(2)
output_csv = False
output_html = False
inventory_mode = False
for opt_o, opt_a in opts:
    if opt_o in ("-h", "--help"):
        printhelp()
        sys.exit()
    elif opt_o in ("-c", "--csv"):
        output_csv = True
    elif opt_o in ("-m", "--html"):
        output_html = True
    elif opt_o in ("-i", "--inventory"):
        inventory_mode = True
    else:
        assert False, "unhandled option"

#exactly one of these options must be set
if not (output_csv ^ output_html):
    printhelp()
    sys.exit(1)

depth = 3
#depth = None

#need to convert filter-generator to actual list or we can only read it once
#getting journal from hledger (apply filters) and parsing it into python objects ...
transactions = list(
                filter(
                    lambda t: len(t.postings) > 0, ledger.parseJournal(
                        ledger.getHLedger(hledger_ledgerpath_, ["--cost", "-x"] + args,depth=None)
                        )
                    )
                )

# for t in transactions:
#     print(t, file=sys.stderr)


#depth limiting transactions ...
for t in transactions:
    t.reduceDepth(depth)


in_out_postingslist_ = []
if inventory_mode:
    for t in transactions:
        ## if transaction contains revenue:sales-gewinn:* postings it is a GEWINN transaction
        if any([any([posting.account.startswith(a) for a in inventory_source_accounts_]) for posting in t.postings]):
            ## in that case: only add the postings to cash:register which contains actual cash income
            ## and ignore all the inventory account postings
            for posting in t.postings:
                if any([posting.account.startswith(a) for a in inventory_destination_accounts_ + inventory_source_accounts_]):
                    continue
                columns_[posting.account] = nextcolumnnumber()
                posting.amount.flipSign() # WARNING: don't use transaction for any other purpose now
                in_out_postingslist_.append((t,posting))
        else:
            ## Otherwise: only include cost that goes into accounts assets:current:inventory-*
            ##            which will be acquisition of stuff-to-be-sold
            for posting in t.postings:
                if (posting.account in inventory_destination_accounts_ and posting.amount.quantity > 0.0):
                    columns_[posting.account] = nextcolumnnumber()
                    in_out_postingslist_.append((t,posting))
else:
    for t in transactions:
        for posting in t.postings:
            ## include only expense: and revenue: accounts
            if not any([posting.account.startswith(ra) for ra in show_only_accounts_with_these_roots_]):
                continue
            ## exclude expense/revenue accounts that are reserved for inventory_mode
            if any([posting.account.startswith(a) for a in inventory_source_accounts_ + inventory_destination_accounts_]):
                continue
            columns_[posting.account] = nextcolumnnumber()
            in_out_postingslist_.append((t,posting))

##colwidth[colid]
#columnwidths_ = list([len(colname) for colid, colname in sorted([(v,k) for k,v in columns_.items()])])

if output_csv:
    #CSV Output
    fieldnames = ['Date', "Currency", "Amount", 'Description', "Invoicecode", "Account", "Comment"]
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    for t,posting in in_out_postingslist_:
        writer.writerow({
            'Date': t.getPostingDate(posting).isoformat(),
            'Description': t.name,
            "Invoicecode":codeToFileURI(t),
            "Amount":-1.0*posting.amount.quantity,
            "Currency":posting.amount.currency,
            "Account":posting.account,
            "Comment":" ".join(t.comments)})
elif output_html:
    #HTML Output
    fieldnames = ['Date', "Amount", 'Description', "Invoicecode", "Account", "Comment"]
    doc = html()
    with doc.add(head()):
        title('Einnahmen/Ausgaben Rechnung')
        meta().set_attribute("charset",'utf-8')
        style("""
            tbody td {
                border-bottom: 1px solid black;
            }
            .tname {
                min-width:30ex;
            }
            td li {
                max-width: 40ex;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .transactiontext {
                font-family: monospace;
                font-size:60%;
                white-space: pre-wrap;
            }
            thead td {
                font-weight:bold;
                border-bottom: 2px solid black;
                border-top: 2px solid black;
            }
            .red {
                color:red;
            }
            """)
    sumcurr = defaultdict(float)
    with doc.add(body()):
        with div(id='content'):
            h1("Einnahmen/Ausgaben Rechnung")
            if inventory_mode:
                h3("Inventur/Getränkekassa Modus")
            else:
                h3("gewöhnlicher Modus")
            tbl = table()
            tbl.add(thead()).add(tr()).add([td(f) for f in fieldnames])
            with tbl.add(tbody()):
                for t,posting in in_out_postingslist_:
                    with tr():
                        td(t.getPostingDate(posting).isoformat())
                        amt = -1.0*posting.amount.quantity
                        td("%s%.2f" % (posting.amount.currency,amt)).set_attribute("class","red" if amt < 0.0 else "black")
                        sumcurr[posting.amount.currency] += amt
                        td(t.name).set_attribute("class","tname")
                        with td():
                            codeToHTMLLinks(t)
                        td(posting.account)
                        td(" ".join(t.comments))
                        td(str(t)).set_attribute("class","transactiontext")
            with tbl.add(thead()):
                with tr():
                    td()
                    with td():
                        for cur, thatsum in sumcurr.items():
                            if thatsum == 0:
                                continue
                            p("%s%.2f" % (cur,thatsum)).set_attribute("class","red" if thatsum < 0.0 else "black")
                    td("SUMME")
                    td()
                    td()
                    td()
    print(doc)
else:
    printhelp()
