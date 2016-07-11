#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) Bernhard Tittelbach, 2015-2016

import ledger
import os, sys
import json
from collections import defaultdict
from twisted.web import server, resource
from twisted.internet import reactor
import math
import urllib.parse
from itertools import islice
import colorsys
import datetime

hledger_ledgerpath_ = os.path.split(__file__)[0]+'/../Ledgers/master.ledger'
httpserver_root_ = os.path.join(os.path.dirname(os.path.realpath(__file__)),"visjsserver/")

def sgn(a):
    if a > 0:
        return 1.0
    elif a < 0:
        return -1.0
    else:
        return 0

def commonPrefix(a,b):
    rv = ""
    for idx in range(0, min(len(a),len(b))):
        if a[idx] == b[idx]:
            rv += a[idx]
        else:
            break
    return rv

def intelliMergeName(n1,n2,minlen):
    if ","+n2 in n1:
        return n1
    common_prefix = commonPrefix(n1,n2)
    if len(common_prefix) >= minlen:
        return common_prefix
    return n1+","+n2


class VisJsGraph(object):
    def __init__(self):
        self.next_node_id=0
        self.labelids = defaultdict(self.__next_node_id)
        self.nodes=[]
        self.edges=[]
        self.edgescale=0.13
        self.nodeminvalue=099999999.0
        self.nodemaxvalue=0.0
        self.edgeminvalue=999999999.0
        self.edgemaxvalue=0.0

    def __next_node_id(self):
        self.next_node_id+=1
        return self.next_node_id

    def addNode(self, label, **args): # value=None, shape=None, color=None, mass=None, level=None
        nodedict = {"id":self.labelids[label], "label":label}
        nodedict.update(args)
        if "value" in nodedict:
            self.nodemaxvalue=max(self.nodemaxvalue, nodedict["value"])
            self.nodeminvalue=min(self.nodeminvalue, nodedict["value"])
        self.nodes.append(nodedict)

    def addEdge(self, n1, n2, title, value):
        value *= self.edgescale
        edgedict = {"from":self.labelids[n1], "to":self.labelids[n2], "value":value, "title":title}
        self.edgemaxvalue=max(self.edgemaxvalue, value)
        self.edgeminvalue=min(self.edgeminvalue, value)
        self.edges.append(edgedict)

    def mkGraph(self):
        rv = { "nodes": self.nodes, "edges": self.edges,
            "clusterme":["expenses:room","expenses:projects","revenue:sales","revenue","assets:fixed","expenses:taxes"],
            "options": {
    "nodes":
        {"scaling":{"label":{"enabled":True}, "min":self.nodeminvalue, "max":self.nodemaxvalue}},
    "edges":
        {"scaling":{"label":{"enabled":True}, "min":self.edgeminvalue, "max":self.edgemaxvalue}},
    "groups":
        {"equity":{"color":{"background":"DeepPink","border":"black"},"borderWidth":3},
         "balancesheet":{"color":{"background":"LawnGreen","border":"black"},"borderWidth":3},
         "incomestatement":{"color":{"background":"SkyBlue","border":"black"},"borderWidth":3},
        },
        }}
        #rv["options"]["nodes"]["scaling"]["customScalingFunction"]="""function (min,max,total,value) {return value/%f};""" % self.nodemaxvalue
        return rv



############## MAIN #####################

depth = 3
#depth = None
print("running hledger (apply filters), getting balances ...", end="", flush=True)
accounts_ = ledger.queryHledgerForAccountListWithBalance(hledger_ledgerpath_, depth=depth, args=sys.argv[1:])
print("done")

#need to convert filter-generator to actual list or we can only read it once
print("getting journal from hledger (apply filters) and parsing it into python objects ...", end="", flush=True)
transactions = list(filter(lambda t: len(t.postings) > 0, ledger.parseJournal(ledger.getHledgerRegister(hledger_ledgerpath_, ["--cost"] + sys.argv[1:],depth=None))))
print("done")

print("depth limiting transactions ...", end="", flush=True)
for t in transactions:
    t.reduceDepth(depth)
print("done")

## make running sum of journal for the graphs
print("calculating running sum ...", end="", flush=True)
running_sum_ = list(ledger.runningSumOfJournal(transactions))
print("done")
print("calculating cashflow ...", end="")
acct_currency_accts_cashflow_dict_ = ledger.cashflowPerAccount(transactions,addinsubaccounts=True)
print("done")


graph = VisJsGraph()

def logScaleValue(x):
    e=1.3
    return math.log2(e + x) / math.log2(e)

print("grouping and adding Nodes ...", end="", flush=True)
for (acct,amt) in accounts_:
    group="equity"
    if acct.startswith("revenue") or acct.startswith("expense") or acct.startswith("overhead"):
        group="incomestatement"
    elif acct.startswith("asset") or acct.startswith("liabilit"):
        group="balancesheet"
    graph.addNode(acct,value=logScaleValue(amt.quantity * sgn(amt.quantity)), group=group, level=acct.count(":")+1)
print("done")

## convert transaction into edges and also
## sum up edges connecting the same nodes, 'cause parallel edges are not allowed
print("adding Edges ...", end="", flush=True)
edges = {}
for t in transactions: #.values():
    try:
        pplus = list(filter(lambda p: p.amount.isPositiv(),t.postings))
        pneg = list(filter(lambda p: not p.amount.isPositiv(),t.postings))
        if len(pplus) == 1:
            for a1 in pneg:
                key = (a1.account,pplus[0].account)
                if key in edges:
                    edges[key] = (intelliMergeName(edges[key][0],t.name,5), edges[key][1]+a1.amount)
                else:
                    edges[key] = (t.name,a1.amount.copy())
        elif len(pneg) == 1:
            for a2 in pplus:
                key = (pneg[0].account,a2.account)
                if key in edges:
                    edges[key] = (intelliMergeName(edges[key][0],t.name,5), edges[key][1]+a2.amount)
                else:
                    edges[key] = (t.name,a2.amount.copy())
        else:
            continue
            ##ignore for now
    except ledger.DifferentCurrency:
        continue
        ## ignore conversion transactions (transactions with 2 different currencies and no conversion rate)

## add edges to graph and make edge weights positiv
for k,v in edges.items():
    if v[1].quantity == 0:
        continue
    graph.addEdge(*k,title="%s %s" % (v[1], v[0]), value=logScaleValue(v[1].quantity * sgn(v[1].quantity)))
print("done")
assert(all([t.isBalanced() for t in transactions]))


def datesBetweenDates(d1,d2):
    """returns [str] list of all the dates between two dates"""
    d1 = datetime.datetime.strptime(d1,ledger.dateformat_hledger_csvexport_)
    d2 = datetime.datetime.strptime(d2,ledger.dateformat_hledger_csvexport_)
    dd = (d2-d1).days
    return [ (d1+datetime.timedelta(days=d)).strftime(ledger.dateformat_hledger_csvexport_) for d in range(1,dd)]


def itail(gen, n):
    """returns n last elements of generator gen"""
    rlist = []
    for e in gen:
        if n == 0 and len(rlist)>0:
            rlist.pop(0)
            n+=1
        rlist.append(e)
        n-=1
    return rlist


from twisted.web import server, resource
from twisted.internet import reactor

class LedgerVisResource(resource.Resource):
    isLeaf = True
    numberRequests = 0

    def __getHTMLColor(self, num, highlight=False):
        v = 0.8
        s = 0.4 if highlight else 1.0
        h = (num % 8)/ 8.0
        if num >= 8:
            h += 1/16.0
        r,g,b = colorsys.hsv_to_rgb(h,s,v)
        return "#%02x%02x%02x" % (int(0xff*r), int(0xff*g), int(0xff*b))

    def __getnextgroupid(self):
        self.groupid_next += 1
        return self.groupid_next


    def __init__(self):
        self.render_handlers=[
            self.__render_json_balance,
            self.__render_json_canvasjs_history,
            self.__render_network_json,
            self.__render_json_cashflow,
            self.__render_json_history,
            self.__render_json_journal,
            self.__render_json_canvasjs_history_days,
            self.__render_file,
            self.__render_default,
            ]
        self.fileext_to_mime={
            ".js":b"text/javascript",
            ".htm":b"text/html",
            ".html":b"text/html",
            ".css":b"text/css"
            }
        self.groupid_next = 0

    def __render_default(self, request, upr):
        request.setHeader(b"content-type", b"text/html")
        try:
            with open(os.path.join(httpserver_root_, "account_network.html"), "rb") as anfh:
                return anfh.read()
        except:
            return """<html><body></body></html>""".encode()

    def __render_file(self, request, upr):
        requestpath = upr.path[1:]
        relpath = os.path.join(httpserver_root_, requestpath.decode("utf-8"))
        if os.path.isfile(relpath):
            ext = os.path.splitext(relpath)[1]
            if not ext in self.fileext_to_mime:
                return False # do not serve just any filetype
            request.setHeader(b"content-type", self.fileext_to_mime[ext])
            with open(relpath, "rb") as anfh:
                return anfh.read()
        return False

    def __render_json_balance(self, request, upr):
        if not upr.path == b'/accountbalance.json':
            return False
        query = urllib.parse.parse_qs(upr.query.decode("utf8"), strict_parsing=False)
        request.setHeader(b"content-type", b"application/json")
        if not "account" in query:
            return b"{}"
        qryaccts = query["account"]
        cur_amtsum = defaultdict(lambda: ledger.Amount(0,""))
        for acct, amt in accounts_:
            if acct.startswith(qryaccts[0]):
                cur_amtsum[amt.currency] += amt
        return json.dumps({"account":qryaccts[0],"balance":list(map(str,cur_amtsum.values()))}).encode("utf-8")

    def __render_json_cashflow(self, request, upr):
        if not upr.path == b'/accountcashflow.json':
            return False
        query = urllib.parse.parse_qs(upr.query.decode("utf8"), strict_parsing=False)
        request.setHeader(b"content-type", b"application/json")
        if not "account" in query:
            return b"{}"
        qryaccts = query["account"]
        if not qryaccts[0] in acct_currency_accts_cashflow_dict_:
            return b"{}"
        pos_data = []
        neg_data = []
        nextpcol = 0
        nextncol = 0
        for currency, acc_amt_float in acct_currency_accts_cashflow_dict_[qryaccts[0]].items():
            for acc, amt_float in acc_amt_float.items():
                piepiece_label = "%s (%s)" % (acc, currency)
                if amt_float > 0:
                    pos_data.append({"value":round(amt_float,1), "label":piepiece_label, "color":self.__getHTMLColor(nextpcol), "highlight":self.__getHTMLColor(nextpcol, highlight=True)})
                    nextpcol += 1
                else:
                    neg_data.append({"value":-1*round(amt_float,1), "label":piepiece_label, "color":self.__getHTMLColor(nextncol), "highlight":self.__getHTMLColor(nextncol, highlight=True)})
                    nextncol += 1
        return json.dumps({"in":pos_data,"out":neg_data}).encode("utf-8")

    def __render_json_history(self, request, upr):
        if not upr.path == b'/accounthistory.json':
            return False
        query = urllib.parse.parse_qs(upr.query.decode("utf8"), strict_parsing=False)
        request.setHeader(b"content-type", b"application/json")
        if not "account" in query:
            return b"[]"
        self.groupid_next = 0
        groupid = defaultdict(self.__getnextgroupid)
        qryaccts = query["account"]
        frs = ledger.registerFromRunningSum(
            ledger.filterRunningSum(running_sum_,
                fromdate=query["fromdate"][0] if "fromdate" in query else None,
                todate=query["todate"][0] if "todate" in query else None,
                account=qryaccts)
            )
        limit = int(query["limit"][0]) if "limit" in query else 60
        returnlist=[]
        for tdate, account_currency_sum in itail(frs, limit):
            for acc, currdict in account_currency_sum.items():
                if not acc in qryaccts:
                    continue
                for currency, amt in currdict.items():
                    returnlist.append({"x":tdate, "y":round(amt.quantity,2), "group": groupid["%s in %s" % (amt.currency,acc)]}) #, "label":{"content":str(amt)}
                    if amt.totalprice and amt.totalprice.currency != amt.currency:
                        returnlist.append({"x":tdate, "y":amt.totalprice.quantity, "group": groupid["%s in %s" % (amt.totalprice.currency,acc)]}) #, "label":str(amt.totalprice)
        grouplist = [{"id":gid, "content":gname} for (gname, gid) in groupid.items()]
        return json.dumps({"dataset":returnlist,"groupset":grouplist}).encode("utf-8")

    def __render_json_journal(self, request, upr):
        """ handle request and return json data formated for visjs graphlibrary
            return all transaction, no running sum
        """
        if not upr.path == b'/accountjournal.json':
            return False
        query = urllib.parse.parse_qs(upr.query.decode("utf8"), strict_parsing=False)
        request.setHeader(b"content-type", b"application/json")
        if not "account" in query:
            return b"[]"
        self.groupid_next = 0
        groupid = defaultdict(self.__getnextgroupid)
        qryaccts = query["account"]
        frs = ledger.filterRunningSum(running_sum_,
                fromdate=query["fromdate"][0] if "fromdate" in query else None,
                todate=query["todate"][0] if "todate" in query else None,
                account=qryaccts)
        limit = int(query["limit"][0]) if "limit" in query else 60
        returnlist=[]
        for t, account_currency_sum, assrt in itail(frs, limit):
            posting_accounts = [p.account for p in t.postings]
            for p in t.postings:
                if not any([p.account.startswith(acc) for acc in qryaccts]):
                    continue
                if p.amount.quantity == 0 or len(p.amount.currency) == 0:
                    continue
                returnlist.append({"x":t.date, "y":round(p.amount.quantity,2), "label": {"content": "<%s] %s" %(p.amount,t.name), "className":"hoverlabel"} , "group": groupid["%s in %s" % (p.amount.currency,p.account)]}) #, "label":{"content":str(amt)}
                if p.amount.totalprice and p.amount.totalprice.currency != p.amount.currency:
                    returnlist.append({"x":t.date, "y":round(p.amount.totalprice.quantity,2), "group": groupid["%s in %s" % (p.amount.totalprice.currency,p.account)]}) #, "label":str(amt.totalprice)
        grouplist = [{"id":gid, "content":gname} for (gname, gid) in groupid.items()]
        return json.dumps({"dataset":returnlist,"groupset":grouplist}).encode("utf-8")


    def __render_json_canvasjs_history(self, request, upr):
        """ handle request and return json data formated for canvasjs graphlibrary
            return all transactions with balance on that day
        """
        if not upr.path == b'/canvasjsaccounthistory.json':
            return False
        query = urllib.parse.parse_qs(upr.query.decode("utf8"), strict_parsing=False)
        request.setHeader(b"content-type", b"application/json")
        if not "account" in query:
            return b"[]"
        qryaccts = query["account"]
        maxlinelength = int(query["maxlinelength"][0]) if "maxlinelength" in query else 60
        frs = ledger.filterRunningSum(running_sum_,
                fromdate=query["fromdate"][0] if "fromdate" in query else None,
                todate=query["todate"][0] if "todate" in query else None,
                account=qryaccts)
        limit = int(query["limit"][0]) if "limit" in query else 1000
        returndict=defaultdict(list)
        for t, account_currency_sum, assrt in itail(frs, limit):
            tdate_ms = int(datetime.datetime.strptime(t.date,ledger.dateformat_hledger_csvexport_).timestamp()*1000)
            for acc, currdict in account_currency_sum.items():
                if not acc in qryaccts:
                    continue
                tstr = "\n".join([line[:maxlinelength] for line in str(t).split("\n")])
                for currency, amt in currdict.items():
                    datasetname = "%s in %s" % (amt.currency,acc)
                    returndict[datasetname].append(
                        {"x":tdate_ms, "y":round(amt.quantity,2), "currency":currency, "transaction":tstr}
                    )
                    if amt.totalprice and amt.totalprice.currency != amt.currency:
                        returndict["%s in %s" % (amt.totalprice.currency,acc)].append(
                            {"x":tdate_ms, "y":round(amt.totalprice.quantity,2), "currency":amt.totalprice.currency, "transaction":tstr}
                        )
        return json.dumps(returndict).encode("utf-8")

    def __render_json_canvasjs_history_days(self, request, upr):
        """ handle request and return json data formated for canvasjs graphlibrary
            show one account balance for each day that has at least one transaction
        """
        if not upr.path == b'/canvasjsaccounthistoryindays.json':
            return False
        query = urllib.parse.parse_qs(upr.query.decode("utf8"), strict_parsing=False)
        request.setHeader(b"content-type", b"application/json")
        if not "account" in query:
            return b"[]"
        qryaccts = query["account"]
        frs = ledger.registerFromRunningSum(
            ledger.filterRunningSum(running_sum_,
                fromdate=query["fromdate"][0] if "fromdate" in query else None,
                todate=query["todate"][0] if "todate" in query else None,
                account=qryaccts)
            )
        limit = int(query["limit"][0]) if "limit" in query else 1000
        returndict=defaultdict(list)
        for tdate, account_currency_sum in itail(frs, limit):
            tdate_ms = int(datetime.datetime.strptime(tdate,ledger.dateformat_hledger_csvexport_).timestamp()*1000)
            for acc, currdict in account_currency_sum.items():
                if not acc in qryaccts:
                    continue
                for currency, amt in currdict.items():
                    datasetname = "%s in %s" % (amt.currency,acc)
                    returndict[datasetname].append(
                        {"x":tdate_ms, "y":round(amt.quantity,2), "currency":currency}
                    )
                    if amt.totalprice and amt.totalprice.currency != amt.currency:
                        returndict["%s in %s" % (amt.totalprice.currency,acc)].append(
                            {"x":tdate_ms, "y":round(amt.totalprice.quantity,2), "currency":amt.totalprice.currency}
                        )
        return json.dumps(returndict).encode("utf-8")

    def __render_network_json(self, request, upr):
        if not upr.path == b"/network.json":
            return False
        #query = urllib.parse.parse_qs(upr.query.decode("utf8"), encoding='utf8', errors="replace")
        request.setHeader(b"content-type", b"application/json")
        return json.dumps(graph.mkGraph()).encode("utf-8")

    def render_GET(self, request):
        print(request.uri, file=sys.stderr)
        upr  = urllib.parse.urlparse(request.uri)
        for hf in self.render_handlers:
            rv = hf(request, upr)
            if rv:
                return rv
        request.setHeader(b"content-type", b"text/html")
        return """<html><body>404 NOT FOUND</body></html>""".encode()

reactor.listenTCP(5001, server.Site(LedgerVisResource()))
print("READY\nplease connect to http://localhost:5001/")
reactor.run()
