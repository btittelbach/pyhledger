# pyhledger
Python Library to read, manipulate and generate stats of hledger files.

Scripts to import various bank histories. Use as example to write your own.

Cool visualisation for your account network.

ledger.py
=========

Is a simple python3 library that can parse ledger() and especially hledger ledgers-files (see http://hledger.org).
It was originally written to help parse bank statement csv exports and generate hledger compatible output.

## Usage:
```import ledger.py``` in your script


convert-*.py
===========
scripts to help convert various bank-data export datat to hledger format

## Usage:

    convert-*.py < bank-export.csv > new_ledger.ledger


visjsserver.py
==============
Comprehensive Visualition of Account-network and statistics. Work in Progress

## Usage:

    ./visjsserver.py
