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

dateformat_ = "%Y-%m-%d"
dateformat_hledger_csvexport_ = "%Y/%m/%d"
dateformat_monthonly_ = "%Y-%m"

colorslist_=["r","b","g","y",'c',"m",'w',"burlywood","aquamarine","chartreuse","Coral","Brown","DarkCyan","DarkOrchid","DeepSkyBlue","ForestGreen","Gold","FloralWhite","Indigo","Khaki","GreenYellow","MediumVioletRed","Navy","Tomato","Maroon","Fuchsia","LightGoldenRodYellow"] * 20

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
def getHLedger(hledger_args):
    assert(isinstance(hledger_args,list))
    stdout = subprocess.Popen(['hledger', 'register', '-O', 'csv','-o','-'] + hledger_args, stdout=subprocess.PIPE).communicate()[0]
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
    plotlabel = u"Hledger"
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

def plotRegister(register_dict):
    plotlabel = u"Plotting Hledger Register"
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
    ## if the day of all dates the 1st
    #if all([d.day == 1 for d in map(list.__add__,[list(dd.keys()) for dd in register_dict.values()])]):
    if True:
        plt.gca().xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter(dateformat_monthonly_, tz=None))
    plt.setp(labels, rotation=80)
    plt.legend( legend_barrefs, legend_accts ,loc='upper left')
    plt.subplots_adjust(left=0.05, bottom=0.08, right=0.98, top=0.95)

plt.figure()
plotRegister(getHLedger(sys.argv[1:]))
plt.show()
