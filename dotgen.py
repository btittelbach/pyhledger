#!/usr/bin/python3
# -*- coding: utf-8 -*-

import ledger
import cgi
import os, sys

hledger_ledgerpath_=os.path.split(__file__)[0]+'/../Ledgers/r3.ledger'

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
    common_prefix = commonPrefix(n1,n2)
    if len(common_prefix) >= minlen:
        return common_prefix
    return n1+","+n2

class DotGraph(object):
    def __init__(self, html=True):
        self.graph=[]
        self.html = html

    def addNode(self, name, description, weight=1.0):
        if self.html:
            self.graph.append('"%s" [ fixedwith=True width=%f height=%f style = "filled" penwidth = 3 fillcolor = "white" fontname = "Courier New" shape = "Mrecord" label =<<table border="0" cellborder="0" cellpadding="3" bgcolor="white"><tr><td bgcolor="black" align="center" colspan="2"><font color="white">%s</font></td></tr><tr><td align="left">%s</td></tr></table>> ]' % (name.replace("\"","\\\""), weight, weight, cgi.escape(name),cgi.escape(description.replace("\n","<br/>"))))
        else:
            self.graph.append('"%s" [ label = "%s" fixedwith=True width=%f height=%f]' % (name.replace("\"","\\\""),name.replace("\"","\\\"")+" "+description.replace("\"","\\\""), weight, weight))

    def addEdge(self, n1, n2, description, weight=1.0):
        self.graph.append('"%s" -> "%s" [label="%s" weight=%f]' % (n1.replace("\"","\\\""), n2.replace("\"","\\\""), description.replace("\"","\\\""), weight))

    def addLabel(self, label):
        self.graph.append('labelloc="t"')
        if self.html:
            self.graph.append('label=<<u><b>%s</b></u>>' % cgi.escape(label))
        else:
            self.graph.append('label="%s"' % label.replace("\"","\\\""))

    def mkGraph(self, name):
        return "digraph %s {\n" % (name,) + "".join(map(lambda s: "\t%s;\n" % s ,self.graph)) + "}\n"


depth = 3
#depth = None
accounts = ledger.queryHledgerForAccountListWithBalance(hledger_ledgerpath_, depth=depth)
transactions = filter(lambda t: len(t.postings) > 0, ledger.parseJournal(ledger.getHledgerRegister(hledger_ledgerpath_, ["--cost"],depth=None)))
#transactions_all = ledger.parseJournal(ledger.getHledgerRegister(hledger_ledgerpath_, ["--cost"],depth=None))
transactions_dict = {}
for t in transactions:
    if t.name in transactions_dict:
        try:
            transactions_dict[t.name].mergeInPostingsFrom(t)
        except ledger.DifferentCurrency:
            print("Transaction Currencies Differ:", file=sys.stderr)
            print(transactions_dict[t.name], file=sys.stderr)
            print(t, file=sys.stderr)
    else:
        transactions_dict[t.name] = t.reduceDepth(None) # make sure each posting has an unique account

for t in transactions_dict.values():
    t.reduceDepth(depth)

transactions = transactions_dict.values()

graph = DotGraph(html=False)
graph.addLabel("r3 Bookkeeping")

edges = {}
for (acct,amt) in accounts:
    graph.addNode(acct,"",weight=amt.quantity * sgn(amt.quantity))
#for t in transactions.values():
    #pplus = list(filter(lambda p: p.amount.isPositiv(),t.postings))
    #pneg = list(filter(lambda p: not p.amount.isPositiv(),t.postings))
    #if len(pplus) == 1:
        #for a1 in pneg:
            #graph.addEdge(a1.account,pplus[0].account,t.name+" "+str(a1.amount))
    #elif len(pneg) == 1:
        #for a2 in pplus:
            #graph.addEdge(pneg[0].account,a2.account,t.name+" "+str(a2.amount))
    #else:
        #continue
        ###ignore for now

## convert transaction into edges and also
## sum up edges, cause parallel edges are not allowed
for t in transactions: #.values():
    pplus = list(filter(lambda p: p.amount.isPositiv(),t.postings))
    pneg = list(filter(lambda p: not p.amount.isPositiv(),t.postings))
    if len(pplus) == 1:
        for a1 in pneg:
            key = (a1.account,pplus[0].account)
            if key in edges:
                edges[key] = (intelliMergeName(edges[key][0],t.name,5), edges[key][1]+a1.amount)
            else:
                edges[key] = (t.name,a1.amount)
    elif len(pneg) == 1:
        for a2 in pplus:
            key = (pneg[0].account,a2.account)
            if key in edges:
                edges[key] = (intelliMergeName(edges[key][0],t.name,5), edges[key][1]+a2.amount)
            else:
                edges[key] = (t.name,a2.amount)
    else:
        continue
        ##ignore for now

## add edges to graph and make edge weights positiv
for k,v in edges.items():
    graph.addEdge(*(k+(v[0],)),weight=v[1].quantity * sgn(v[1].quantity))

print(graph.mkGraph("hledgerautograph"))
