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

hledger_ledgerpath_ = os.path.split(__file__)[0]+'/../Ledgers/r3.ledger'
invoice_path_ = os.path.abspath(os.path.split(__file__)[0]+'/../Rechnungen/')
show_only_accounts_with_these_roots_ = ["expense", "revenue"]
inventory_destination_accounts_ = ["assets:current:inventory-edibles", "assets:current:inventory-materials"]
inventory_source_accounts_ = ["revenue:sales:edibles","revenue:sales:materials", "expenses:shrinkage"]
inventory_expense_accounts_ = ["expenses:sales:edibles", "expenses:sales:materials"]

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

def codeToFileURI(code):
	"""
		Search for invoice-files matching the invoice code and text for inclusion in CSV
	"""	
	if not isinstance(code, str):
		return code
	flist = glob.glob(os.path.join(invoice_path_,"*",code),recursive=True)
	if len(flist) == 0:
		for scode in code.split(","):
			flist += glob.glob(os.path.join(invoice_path_,"*",scode),recursive=True)
	if len(flist) == 0:
		flist += glob.glob(os.path.join(invoice_path_,"*","*%s*" % code),recursive=True)
	#return "\n".join([code] + [ Path(f).as_uri() for f in flist])
	return "\n".join([code] + [ Path(f).as_uri() for f in flist])

def codeToHTMLLinks(code):
	"""
		Search for invoice-files matching the invoice code and return html objects
	"""
	ulist = ul()
	flist=[]
	if not isinstance(code, str):
		return ""
	with ulist:
		for f in glob.glob(os.path.join(invoice_path_,"*",code),recursive=True):
			flist.append(f)
			li(a(code,href=Path(f).as_uri(),target="_blank"))
		if len(flist) == 0:
			for scode in code.split(","):
				files = glob.glob(os.path.join(invoice_path_,"*",scode),recursive=True)
				if len(files) > 0:
					for f in files:
						flist.append(f)
						li(a(scode,href=Path(f).as_uri(),target="_blank"))
				elif scode != code:
					li(scode)
		if len(flist) == 0:
			for f in glob.glob(os.path.join(invoice_path_,"*","*[(_-]%s[)_-]*" % code),recursive=True):
				flist.append(f)
				li((a(code,href=Path(f).as_uri(),target="_blank")))
		if len(flist) == 0:
			li(code)
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
                        ledger.getHLedger(hledger_ledgerpath_, ["--cost"] + args,depth=None)
                        )
                    )
                )

#depth limiting transactions ...
for t in transactions:
    t.reduceDepth(depth)


in_out_postingslist_ = []
if inventory_mode:
	for t in transactions:
		## if transaction contains revenue:sales-gewinn:* postings it is a GEWINN transaction
		if any([(posting.account in inventory_source_accounts_) for posting in t.postings]):
			## in that case: only add the postings to cash:register which contains actual cash income
        	## and ignore all the inventory account postings
			for posting in t.postings:
				if (posting.account in inventory_destination_accounts_ + inventory_source_accounts_):
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
	        if posting.account in inventory_source_accounts_ + inventory_destination_accounts_:
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
	        'Date': t.getPostingDate(posting), 
	        'Description': t.name, 
	        "Invoicecode":codeToFileURI(t.code), 
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
						td(t.getPostingDate(posting).replace("/","-"))
						amt = -1.0*posting.amount.quantity
						td("%s%.2f" % (posting.amount.currency,amt)).set_attribute("class","red" if amt < 0.0 else "black")
						sumcurr[posting.amount.currency] += amt
						td(t.name)
						with td():
							codeToHTMLLinks(t.code)
						td(posting.account)
						td(" ".join(t.comments))
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
