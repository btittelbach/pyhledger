# pyhledger
Python Library to read, manipulate and generate stats of hledger files.

Scripts to import various bank histories. Use as example to write your own.

Cool visualisation for your account network.

ledger.py
=========

Is a simple python3 module that can parse ledger() and especially hledger ledgers-files (see http://hledger.org).
It was originally written to help parse bank statement csv exports and generate hledger compatible output.

## Usage:
```import ledger.py``` in your script


convert-*.py
===========
scripts to help convert various bank-data export datat to hledger format

## Usage:

    convert-*.py < bank-export.(csv|json) > new_ledger.ledger


visjsserver.py
==============
Comprehensive Visualition of Account-network and statistics. Work in Progress. To be published

## Usage:

    ./visjsserver.py

stats.(sh|py)
=============
Displays various graphs and information.
Use as starting point for your own code.
Probably not useable out of the box.

mkmemberfees.hs
===============
Our script that takes sqlite database based on <tt>members.sql</tt> Scheme and generates
monthly transfers between internal accounts for each membershipfee owned.
This should balance out with the actual banktransfers of membershipfees that are imported
from the bank csv 
