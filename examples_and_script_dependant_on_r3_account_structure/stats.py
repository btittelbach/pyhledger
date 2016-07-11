#!/usr/bin/python2
# -*- coding: utf-8 -*-

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import sys
import codecs
import os, io
import sqlite3 as lite
import datetime
import dateutil.relativedelta
from collections import defaultdict
import csv
import subprocess

sqlite_db_=os.path.split(__file__)[0]+'/../Ledgers/members.sqlite'
hledger_ledgerpath_=os.path.split(__file__)[0]+'/../Ledgers/r3.ledger'
dateformat_ = "%Y-%m-%d"
dateformat_hledger_csvexport_ = "%Y/%m/%d"
dateformat_monthonly_ = "%Y-%m"

# unaccounted money in fraction of expected beverages revenue
unaccounted_money_fraction = [ (datetime.date(2013,1,22),-.0857),
                                (datetime.date(2013,5,10),-.1002),
                                (datetime.date(2013,8,9),-.3026),
                                (datetime.date(2014,3,6),-.3193),
                                (datetime.date(2014,3,30),-.303),
                                (datetime.date(2014,6,19),.1619),
                                (datetime.date(2014,10,16),-.1558),
                                (datetime.date(2015,2,16),.0296),
                                (datetime.date(2015,6,30),-.157),
                            ]

colorslist_=["r","b","g","y",'c',"m",'w',"burlywood","aquamarine","chartreuse","Coral","Brown","DarkCyan","DarkOrchid","DeepSkyBlue","ForestGreen","Gold","FloralWhite","Indigo","Khaki","GreenYellow","MediumVioletRed","Navy","Tomato","Maroon","Fuchsia","LightGoldenRodYellow"] * 20

def getVeryFirstMonth(con):
    cur = con.cursor()
    cur.execute("SELECT min(m_firstmonth) from membership")
    strdate = cur.fetchone()[0]
    rdate = datetime.datetime.strptime(strdate, dateformat_).date()
    return normalizeDateToFirstInMonth(rdate)

def getNextMonth():
    rdate = datetime.date.today() + dateutil.relativedelta.relativedelta(months=2)
    rdate -= dateutil.relativedelta.relativedelta(days=rdate.day)
    return rdate

def getMembersInMonth(con, month):
    assert(isinstance(month,datetime.date))
    cur = con.cursor()
    cur.execute('SELECT count(*),sum(m_fee) from membership where m_firstmonth <= ? and (m_lastmonth is null or m_lastmonth is "" or m_lastmonth >= ?)', (month.isoformat(),month.isoformat()))
    return cur.fetchone()
    #return [r[0] for r in rows] # unpack singlevalue tuples: [(x,)] => [x]

### returns results from membership table in sqlite db
### @return [(p_id, m_firstmonth :: datetime.date, m_lastmonth :: datetime.date || None, m_fee: float), (...), (...), ...]
def getMemberships(con):
    cur = con.cursor()
    cur.execute('SELECT p_id, m_firstmonth, m_lastmonth, m_fee from membership order by m_firstmonth')
    rows = cur.fetchall()
    return [(r[0],datetime.datetime.strptime(r[1], dateformat_).date(), datetime.datetime.strptime(r[2], dateformat_).date() if not (r[2] is None or len(r[2]) < 1) else None, r[3]) for r in rows]

### Helperclass, basically a variant (float,float) tuple with a __str__ method
### used to count plus/minus members / membershipincome per date
class PlusMinusTuple():
    def __init__(self):
        self.plus=0
        self.minus=0
    def __str__(self):
        s=[]
        if self.plus:
            s+=["+%d" % self.plus]
        if self.minus:
            s+=["%d" % self.minus]
        return "\n".join(s)

### @return datetime.date with the day of given datetime.date set to 1
def normalizeDateToFirstInMonth(rdate):
    if rdate.day != 1:
        rdate += dateutil.relativedelta.relativedelta(days=1-rdate.day)
    return rdate

### calculates for each month, the number of members who are new and who left
### respectively for each month the amount and decrease in membershipincome
### summing up the two values in a PlusMinusTuple would give the change for that month
### @return tuple (pm_dates,pm_fee_dates) where pm_dates is of type dict{ datetime.date : PlusMinusTuple }
def extractPlusMinusFromMemberships(membership):
    pm_dates = defaultdict(lambda:PlusMinusTuple())
    pm_fee_dates = defaultdict(lambda:PlusMinusTuple())
    for p_id, fmonth, lmonth, m_fee in membership:
        pm_dates[fmonth.strftime(dateformat_monthonly_)].plus += 1
        pm_fee_dates[fmonth.strftime(dateformat_monthonly_)].plus += m_fee
        if lmonth:
            lmonth = normalizeDateToFirstInMonth(lmonth) + dateutil.relativedelta.relativedelta(months=1)
            pm_dates[lmonth.strftime(dateformat_monthonly_)].minus -= 1
            pm_fee_dates[lmonth.strftime(dateformat_monthonly_)].minus -= m_fee
    return (pm_dates, pm_fee_dates)

### @return dict[ p_id :(p_nick,p_name) ] for all members
def getMemberInfos(con):
    cur = con.cursor()
    cur.execute('SELECT p_id, p_nick, p_name from membership left join persons using (p_id) order by p_id')
    rows = cur.fetchall()
    return dict([(a,(b,c)) for a,b,c in rows])

### for each month between start of data and now,
### the function returns the number of members and the theoretical amount of membershipincome from membershipfees
### @return [(datetime.date, (<number of members in month>:int, <membershipincome in month>:float))]
def getMembersTimeData(con):
    cdate = getVeryFirstMonth(con)
    enddate = getNextMonth()
    rv = []
    while cdate < enddate:
        rv.append((cdate, getMembersInMonth(con,cdate)))
        cdate += dateutil.relativedelta.relativedelta(months=1)
    return rv

def graphMembersOverTimeWithPlusMinusText(membertimedata, memberinfos, membership):
    ydates, yvalues = zip(*membertimedata)
    ydates = list(ydates)
    #yvalues = map(lambda x:x[0],yvalues)
    plotlabel = [u"Number of members over time","Membership Income over time"]
    plt.plot(ydates, yvalues, 'o',linewidth=2, markevery=1)
    plt.ylabel("#Members")
    plt.xlabel("Month")
    plt.grid(True)
    plt.legend(plotlabel,loc='upper left')
    plt.twiny()
    plt.ylabel("Euro")
    #plt.title(plotlabel)
    ## label with +x-y members per month
    membersinmonth = dict(membertimedata)
    #print "\n".join([ "%s:%s" % (x[0],str(x[1])) for x in extractPlusMinusFromMemberships(membership).items()])
    pm_dates, pm_fee_dates = extractPlusMinusFromMemberships(membership)
    for astrdate, tpl in pm_dates.items():
        adate = datetime.datetime.strptime(astrdate, dateformat_monthonly_).date()
        assert(adate.day==1)
        if adate in membersinmonth:
            xy = (adate, membersinmonth[adate][0])
            xytext = (xy[0], xy[1]+1)
            plt.annotate(str(tpl), xy=xy, xytext=xytext,arrowprops=dict(facecolor='gray', shrink=0.5))
    for astrdate, tpl in pm_fee_dates.items():
        adate = datetime.datetime.strptime(astrdate, dateformat_monthonly_).date()
        assert(adate.day==1)
        if adate in membersinmonth:
            xy = (adate, membersinmonth[adate][1])
            xytext = (xy[0], xy[1]+30)
            plt.annotate(str(tpl), xy=xy, xytext=xytext,arrowprops=dict(facecolor='gray', shrink=0.5))
    plt.subplots_adjust(left=0.06, bottom=0.05, right=0.99, top=0.95)

def graphMembershipIncomeOverTime(membertimedata, memberinfos, membership):
    ydates, yvalues = zip(*membertimedata)
    ydates = list(ydates)
    yvalues = map(lambda x:x[1],yvalues)
    plotlabel = u"Membership Income over time"
    plt.plot(ydates, yvalues, '^g',linewidth=2, markevery=1)
    plt.ylabel("Euro")
    plt.xlabel("Month")
    plt.grid(True)
    plt.title(plotlabel)
    ## label with +x-y members per month
    membersinmonth = dict(membertimedata)
    #print "\n".join([ "%s:%s" % (x[0],str(x[1])) for x in extractPlusMinusFromMemberships(membership).items()])
    pm_dates, pm_fee_dates = extractPlusMinusFromMemberships(membership)
    for astrdate, tpl in pm_fee_dates.items():
        adate = datetime.datetime.strptime(astrdate, dateformat_monthonly_).date()- dateutil.relativedelta.relativedelta(months=1)
        assert(adate.day==1)
        if adate in membersinmonth:
            plt.vlines(adate + dateutil.relativedelta.relativedelta(days=11),tpl.minus+membersinmonth[adate][1],tpl.plus+membersinmonth[adate][1])
            plt.hlines(membersinmonth[adate][1], adate + dateutil.relativedelta.relativedelta(days=10),adate + dateutil.relativedelta.relativedelta(days=12))
    xstart,xend = plt.xlim()
    locs, labels = plt.xticks(np.arange(xstart,xend,61))
    plt.gca().xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter(dateformat_monthonly_, tz=None))
    plt.setp(labels, rotation=80)
    plt.subplots_adjust(left=0.06, bottom=0.08, right=0.99, top=0.95)

def graphMembersOverTime(membertimedata, memberinfos, membership):
    ydates, yvalues = zip(*membertimedata)
    ydates = list(ydates)
    yvalues = map(lambda x:x[0],yvalues)
    plotlabel = u"Number of members over time"
    plt.plot(ydates, yvalues, '^',linewidth=2, markevery=1)
    plt.ylabel("Members")
    plt.ylim(ymin=0)
    plt.xlabel("Month")
    plt.grid(True)
    plt.title(plotlabel)
    ## label with +x-y members per month
    membersinmonth = dict(membertimedata)
    #print "\n".join([ "%s:%s" % (x[0],str(x[1])) for x in extractPlusMinusFromMemberships(membership).items()])
    pm_dates, pm_fee_dates = extractPlusMinusFromMemberships(membership)
    for astrdate, tpl in pm_dates.items():
        adate = datetime.datetime.strptime(astrdate, dateformat_monthonly_).date()- dateutil.relativedelta.relativedelta(months=1)
        assert(adate.day==1)
        if adate in membersinmonth:
            plt.vlines(adate + dateutil.relativedelta.relativedelta(days=11),tpl.minus+membersinmonth[adate][0],tpl.plus+membersinmonth[adate][0])
            plt.hlines(membersinmonth[adate][0], adate + dateutil.relativedelta.relativedelta(days=10),adate + dateutil.relativedelta.relativedelta(days=12))
    plt.subplots_adjust(left=0.06, bottom=0.05, right=0.99, top=0.95)

def graphMembershipdurationsPerPersonOverTime(membership, memberinfos):
    colorslist = list(colorslist_)
    membercolor = defaultdict(lambda: colorslist.pop(0))
    plotlabel = u"Members over Time"
    legendhandles={}
    duration = None
    membernames_inorder = [None]*(max(memberinfos.keys())+1)
    for p_id, fmonth, lmonth, m_fee in membership:
        if fmonth > datetime.date.today():
            continue
        xpos = fmonth
        if lmonth is None:
            duration = getNextMonth() - fmonth
        else:
            duration = lmonth - fmonth
        legendhandles[memberinfos[p_id][0]] = plt.barh([p_id],[duration.days],left=xpos,color=membercolor[p_id])
        membernames_inorder[p_id] = memberinfos[p_id][0]
    plt.ylabel("Member")
    plt.xlabel("Month")
    ## set xaxis maximum to 2 months from today, so we have some space between yaxis and bars
    plt.xlim(xmax=datetime.date.today() + dateutil.relativedelta.relativedelta(months=2))
    ## fill the yaxis description with the membernames
    plt.yticks(memberinfos.keys(),[nick for nick, name in memberinfos.values()])
    ## put yaxis labelin on the right as well as on the left
    plt.tick_params(labelright=True)
    ## show a grid so we can more easily connect bars to membernames
    plt.grid(True)
    plt.title(plotlabel)
    ## show dates on xaxis in 61 day intervals
    xstart,xend = plt.xlim()
    locs, labels = plt.xticks(np.arange(xstart,xend,61))
    ## format dates as %Y-%m
    plt.gca().xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter(dateformat_monthonly_, tz=None))
    ## rotate dates on xaxis for better fit
    plt.setp(labels, rotation=80)
    ## make graph use more space (good if windows is maximized)
    plt.subplots_adjust(left=0.08, bottom=0.08, right=0.92, top=0.95)

def graphMembershipdurationsPerPersonOverTime2(membership, memberinfos):
    plotlabel = u"Members over Time"
    colorslist = list(colorslist_)
    membercolor = defaultdict(lambda: colorslist.pop(0))
    membership2 = defaultdict(list)
    for p_id, fmonth, lmonth in membership:
        duration = None
        if lmonth is None:
            duration = getNextMonth() - fmonth
        else:
            duration = lmonth - fmonth
        membership2[p_id].append((fmonth,))
    for p_id, xrng in membership2.items():
        broken_barh(self, xrng, [(p_id,1)], label=memberinfos[p_id][0],color=membercolor[p_id])
    plt.ylabel("Member")
    plt.xlabel("Month")
    plt.legend(legendhandles.values(),legendhandles.keys(), loc='upper left')
    plt.title(plotlabel)

def graphUnaccountedMoney(ucmoney):
    plotlabel = u"Unaccounted-for money in cash register"
    plus_ucmoney = filter(lambda (x,y): y>=0,ucmoney)
    minus_ucmoney = filter(lambda (x,y): y<0,ucmoney)
    plus_x,plus_y = zip(*plus_ucmoney)
    minus_x,minus_y = zip(*minus_ucmoney)
    #plt.stem(x,y)
    plt.bar(plus_x,plus_y,width=15,color="OliveDrab",edgecolor="k")
    plt.bar(minus_x,minus_y,width=15,color="Crimson",edgecolor="k")
    plt.ylabel("% EUR of expected income")
    plt.xlabel("Date")
    plt.grid(True)
    ## draw a line at y=0 (i.e. xaxis line)
    plt.axhline(0, color='black')
    plt.title(plotlabel)

### cvs reader workaround, see python CSV module documentation
def unicode_csv_reader(unicode_csv_data, dialect=csv.excel, **kwargs):
    # csv.py doesn't do Unicode; encode temporarily as UTF-8:
    csv_reader = csv.reader(utf_8_encoder(unicode_csv_data),
                            dialect=dialect, **kwargs)
    for row in csv_reader:
        # decode UTF-8 back to Unicode, cell by cell:
        yield [unicode(cell, 'utf-8') for cell in row]

### cvs reader workaround, see python CSV module documentation
def utf_8_encoder(unicode_csv_data):
    for line in unicode_csv_data:
        yield line.encode('utf-8')

### query hledger in 'register' mode with given parameters and makes hledger output in csv-format
### the csv output is then being parsed and inserted into
### @return dict[accountname : string][day/week/month/quarter : datetime.time] = amount : float
def getHledgerRegister(hledger_filter):
    assert(isinstance(hledger_filter,list))
    stdout = subprocess.Popen(['/home/bernhard/.cabal/bin/hledger', '-f', hledger_ledgerpath_,"register", '-O', 'csv','-o','-'] + hledger_filter, stdout=subprocess.PIPE).communicate()[0]
    ## python asumes subprocess.PIPE i.e. stdout is ascii encoded
    ## thus a hack is required to make csv.reader process it in utf-8.
    ## first we need to convert it to unicode() type and then
    ## each line has to be converted back to a utf-8 string for cvs.reader()
    csvfile = unicode_csv_reader(codecs.decode(stdout,"utf-8").split(u"\n"),delimiter=',', quotechar='"')
    rv = defaultdict(dict)
    for row in csvfile:
        if len(row) != 5 or row[0] == "date":
            continue
        (date,description,account,amtWcurrency,balance) = row
        date = datetime.datetime.strptime(date,dateformat_hledger_csvexport_).date()
        amtstr, currency = amtWcurrency.split(" ")
        amount = float(amtstr.replace(",",""))
        rv[account][date] = amount
    return rv

def getHBarBottoms(bottom_dict_min, bottom_dict_max, dates, values):
    return map(lambda (dat, val): bottom_dict_max[dat] if val >= 0 else bottom_dict_min[dat], zip(dates,values))

def plotMonthlyExpenses(monthly_register_dict):
    plotlabel = u"Monthly Expenses"
    colorslist = list(colorslist_)
    acctcolor = defaultdict(lambda: colorslist.pop(0))
    legend_barrefs = []
    legend_accts = []
    bottom_dict_max = defaultdict(int)
    bottom_dict_min = defaultdict(int)
    width=20
    for acct, date_amt_dict in monthly_register_dict.items():
        dates, amts = zip(*sorted(date_amt_dict.items()))
        legend_barrefs.append( plt.bar(dates, amts, width, color=acctcolor[acct], bottom=getHBarBottoms(bottom_dict_min, bottom_dict_max, dates, amts)) )
        legend_accts.append(acct)
        for date, amt in date_amt_dict.items():
            bottom_dict_max[date] = max(bottom_dict_max[date], bottom_dict_max[date] + amt)
            bottom_dict_min[date] = min(bottom_dict_min[date], bottom_dict_max[date] + amt)
    plt.ylabel("EUROs")
    plt.xlabel("Date")
    plt.grid(True)
    plt.title(plotlabel)
    ## show dates on xaxis in 61 day intervals
    xstart,xend = plt.xlim()
    locs, labels = plt.xticks(np.arange(xstart,xend,61))
    ## format dates as %Y-%m
    plt.gca().xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter(dateformat_monthonly_, tz=None))
    ## rotate dates on xaxis for better fit
    plt.setp(labels, rotation=80)
    ## display legend in given corner
    plt.legend( legend_barrefs, legend_accts ,loc='upper left')
    ## make graph use more space (good if windows is maximized)
    plt.subplots_adjust(left=0.05, bottom=0.08, right=0.98, top=0.95)

def plotQuaterlyOtherExpenses(register_dict):
    plotlabel = u"Other Quaterly Expenses"
    colorslist = list(colorslist_)
    acctcolor = defaultdict(lambda: colorslist.pop(0))
    legend_barrefs = []
    legend_accts = []
    bottom_dict_max = defaultdict(int)
    bottom_dict_min = defaultdict(int)
    width=20
    for acct, date_amt_dict in register_dict.items():
        dates, amts = zip(*sorted(date_amt_dict.items()))
        legend_barrefs.append( plt.bar(dates, amts, width, color=acctcolor[acct], bottom=getHBarBottoms(bottom_dict_min, bottom_dict_max, dates, amts)) )
        legend_accts.append(acct)
        for date, amt in date_amt_dict.items():
            bottom_dict_max[date] = max(bottom_dict_max[date], bottom_dict_max[date] + amt)
            bottom_dict_min[date] = min(bottom_dict_min[date], bottom_dict_max[date] + amt)
    plt.ylabel("EUROs")
    plt.xlabel("Date")
    plt.grid(True)
    plt.title(plotlabel)
    xstart,xend = plt.xlim()
    locs, labels = plt.xticks(np.arange(xstart,xend,30.5*3))
    plt.gca().xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter(dateformat_monthonly_, tz=None))
    plt.setp(labels, rotation=80)
    plt.legend( legend_barrefs, legend_accts ,loc='lower left')
    plt.subplots_adjust(left=0.05, bottom=0.08, right=0.98, top=0.95)


con = lite.connect(sqlite_db_)
membertimedata = getMembersTimeData(con)
memberships = getMemberships(con)
memberinfos=getMemberInfos(con)
con.close()
graphMembersOverTime(membertimedata,memberinfos,memberships)
plt.figure()
graphMembershipIncomeOverTime(membertimedata,memberinfos,memberships)
plt.figure()
graphMembersOverTimeWithPlusMinusText(membertimedata,memberinfos,memberships)
plt.figure()
graphMembershipdurationsPerPersonOverTime(memberships,memberinfos)
# plt.figure()
# graphMembershipdurationsPerPersonOverTime2(memberships,memberinfos)
plt.figure()
graphUnaccountedMoney(unaccounted_money_fraction)
plt.figure()
plotMonthlyExpenses(getHledgerRegister(["-M","acct:expenses:room","acct:expenses:bank","acct:expenses:internet-domain","acct:expenses:taxes","date:from 2010/01/01"]))
plt.figure()
plotQuaterlyOtherExpenses(getHledgerRegister(["-Q","acct:expenses:---.+---","acct:expenses:projects","acct:expenses:disposal","date:from 2013/03/01"]))
plt.figure()
plotQuaterlyOtherExpenses(getHledgerRegister(["-Q","--depth=1","acct:expenses","acct:revenue","not:acct:expenses:hirepurchase:lasercutter1","date:from 2013/03/01 to "+datetime.date.today().strftime("%Y/%m/19")]))
plt.show()
