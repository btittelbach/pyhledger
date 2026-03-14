#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) Bernhard Tittelbach, 2015-2026, AGPLv3

from collections import defaultdict
import datetime
import calendar
import subprocess
import os, sys
import codecs
import re
import copy
from itertools import *
import uuid
from pathlib import Path
from typing import Set, List, Optional


dateformat_hledger_csvexport_ = "%Y/%m/%d"
dateformat_hledger_iso_ = "%Y-%m-%d"
dateformat_hledger_dot_ = "%Y.%m.%d"
account_separator_ = ":"

class FileSlice(object):
    def __init__(self, filename, startline, endline):
        self.filepath=Path(filename) if filename is not None and len(filename)>0 else None
        self.startline=startline
        self.endline=endline

    def __str__(self):
        return f"{self.filepath.name}:{self.startline}-{self.endline}"

    def replaceWithStr(self, newblock: str) -> int:
        """
        Replace lines from startline to endline (inclusive) with newblock.

        Args:
            newblock: New content to insert

        Returns:
            Signed integer representing the change in line count (new - original)
        """
        # Read all lines and count original line count
        original_block_count = 0
        start_pos = 0
        end_pos = -1
        line_num = 0
        post_end_line_content = None
        with open(self.filepath, 'r') as f:
            while line:= f.readline():
                if line_num + 1 == self.startline: #if this never is true, because startline == 0, then start_pos = 0 which is the default
                    start_pos = f.tell() # start of next line is after end of this line
                if line_num == self.endline:
                    end_pos = f.tell()
                    post_end_line_content = f.read()
                line_num += 1

        if -1 == end_pos:
            # endline was probably the last line in the file
            end_pos = f.tell()
            post_end_line_content = f.read()

        if post_end_line_content is None:
            raise ValueError("End line exceeds file length")

        # Ensure newblock ends with newline if it doesn't already
        if newblock and not newblock.endswith('\n'):
            newblock += '\n'

        # Write modified content
        with open(self.filepath, 'r+') as f:
            f.seek(start_pos)
            f.truncate()
            f.write(newblock)
            f.write(post_end_line_content)

        old_linecount = (self.endline-self.startline) + 1
        new_linecount = newblock.count('\n')
        self.endline = self.startline + new_linecount - 1

        # Return difference between line count
        return new_linecount - old_linecount

class DifferentCurrency(Exception):
    pass

class TransactionUnbalancedError(Exception):
    pass

class Amount(object):
    def __init__(self, quantity, currency):
        self.quantity=float(quantity)
        self.currency=currency.strip()
        self.totalprice=None
        self.perunitprice=None

    def addTotalPrice(self,amount):
        if amount is None:
            return self
        self.totalprice = copy.copy(amount).makePositive()
        self.perunitprice = Amount(amount.quantity / self.quantity, amount.currency).makePositive()
        return self

    def addPerUnitPrice(self,amount):
        if amount is None:
            return self
        self.totalprice = Amount(amount.quantity * self.quantity, amount.currency).makePositive()
        self.perunitprice = copy.copy(amount).makePositive()
        return self

    def sameUnit(self, amount):
        return self.currency == amount.currency

    def add(self,amount):
        if self.quantity == 0:
            self.quantity = amount.quantity
            self.currency = amount.currency if len(amount.currency)>0 else self.currency
            self.totalprice = amount.totalprice
            self.perunitprice = amount.perunitprice
            return self
        elif amount.quantity == 0:
            return self
        if self.currency != amount.currency:
            raise DifferentCurrency
        if not self.totalprice is None or not amount.totalprice is None:
            if self.totalprice is None:
                if amount.perunitprice is None:
                    self.perunitprice = Amount(amount.totalprice.quantity / amount.quantity, amount.totalprice.currency)
                else:
                    self.perunitprice = copy.copy(amount.perunitprice)
                self.totalprice = Amount(self.perunitprice.quantity * (self.quantity+amount.quantity), amount.totalprice.currency)
            elif amount.totalprice is None:
                self.totalprice.quantity = self.perunitprice.quantity * (self.quantity+amount.quantity)
            else:
                if self.totalprice.currency != amount.totalprice.currency:
                    raise DifferentCurrency
                self.totalprice.quantity += amount.sgn() * amount.totalprice.quantity
                try:
                    self.perunitprice.quantity = self.totalprice.quantity / (self.quantity+amount.quantity)
                except ZeroDivisionError:
                    self.perunitprice.quantity = (self.perunitprice.quantity + amount.perunitprice.quantity) / 2
        self.quantity += amount.quantity
        return self

    def __add__(self,amount):
        return self.add(amount)

    def isPositiv(self):
        return self.quantity >= 0

    def sgn(self):
        if self.quantity == 0:
            return 0
        if self.isPositiv():
            return 1
        else:
            return -1

    def flipSign(self):
        self.quantity *= -1
        return self

    def makePositive(self):
        if not self.isPositiv():
            self.flipSign()
        return self

    def copy(self):
        return copy.deepcopy(self)

    def __str__(self):
        "Format unit/currency quantity as a string."
        a = "%.4f" % (self.quantity)
        a = "%s %s" % (a.rstrip("0").rstrip(".,"), self.currency)  #unfortunately %g does not do the correct thing so we need to use rstrip
        # a = "%s %s" % (str_rstrip_max(a,"0",2).rstrip(".,"), self.currency)  #unfortunately %g does not do the correct thing so we need to use rstrip
        if not self.totalprice is None:
            if not self.perunitprice is None and self.quantity == 0:
                a += " @ " + str(self.perunitprice)
            else:
                a += " @@ " + str(self.totalprice)
        return a.strip()

class NoAmount(Amount):
    def __init__(self):
        self.quantity=0
        self.currency=""
        self.totalprice=None
        self.perunitprice=None

    def __str__(self):
        return ""

class FutureAmountFraction(Amount):
    def __init__(self, fraction):
        self.fraction=float(fraction)
        self.currency=""
        self.totalprice=None
        self.perunitprice=None

    def convertToAmount(self, amount):
        self.quantity = amount.quantity
        self.currency = amount.currency
        self.totalprice = amount.totalprice
        self.quantity *= self.fraction

class Posting(object):
    def __init__(self, account, amount, commenttags = [], assertamount = None, virtual = False):
        self.account = account.strip()
        self.amount = amount if not amount is None else NoAmount()
        assert(isinstance(self.amount,Amount))
        self.tags=defaultdict(list)
        self.commenttags = []
        self.virtual = virtual
        self.elided = True if isinstance(amount, NoAmount) else False # if True: don't print Amount of this posting
        self.post_posting_assert_amount = None if isinstance(assertamount,NoAmount) else assertamount
        if isinstance(commenttags,str):
            self.commenttags.append(commenttags.strip())
        self.__updateTags()

    def __updateTags(self):
        def addTagMatch(tagname, tagvalue):
            self.tags[tagname.replace(",","").replace(":","")] += [tagvalue]

        ## clear tags
        self.tags=defaultdict(list)
        parseTagMatchesFromComments(self.commenttags, addTagMatch)

    def addComment(self, comment):
        if isinstance(comment,str):
            comment = comment.strip()
            if len(comment) > 0:
                self.commenttags.append(comment)
                self.__updateTags()
        return self


    def addTag(self,tag,taginfo=""):
        if taginfo is None:
            taginfo=""
        if not isinstance(taginfo,str):
            taginfo=str(taginfo)
        taginfo = taginfo.strip(" ,\t\n:").replace(",","%2C").replace(":","%3A")
        tag = tag.strip(" ,\t\n:").replace(",","%2C").replace(":","%3A").replace(" ","%20")
        assert(tag.find(" ") < 0)
        assert(tag.find(",") < 0)
        assert(taginfo.find(",") < 0)
        if 0 == len(self.commenttags):
            self.commenttags.append("")
        if len(self.commenttags[0]) > 0:
            self.commenttags[0] += " "
        self.commenttags[0] += f"{tag}:{taginfo},"
        self.__updateTags()
        return self

    def getTag(self, tag) -> Optional[str]:
        rl = self.getTagList(tag)
        if len(rl) == 0:
            return None
        return rl[0]

    def getTagList(self, tag) -> List[str]:
        return [m.group(2) for m in self.tags[tag]]

    def changeTag(self, tag, taginfo="", tagindex=0):
        if not tag in self.tags:
            return
        if tagindex > len(self.tags[tag]):
            return
        taginfo = taginfo.strip(" ,\t\n:").replace(",","%2C").replace(":","%3A")
        m = self.tags[tag][tagindex]
        cmt_index = self.commenttags.index(m.string)
        assert(cmt_index >= 0)
        ## replace that part in the comment
        self.commenttags[cmt_index] = self.commenttags[cmt_index][:m.start(2)] + taginfo + "," + self.commenttags[cmt_index][m.end(0):]
        self.__updateTags()

    def rmTag(self, tag, tagindex=0):
        if not tag in self.tags:
            return
        if tagindex > len(self.tags[tag]) or tagindex < 0:
            return
        m = self.tags[tag][tagindex]
        cmt_index = self.commenttags.index(m.string)
        assert(cmt_index >= 0)
        ## replace that part in the comment
        self.commenttags[cmt_index] = self.commenttags[cmt_index][:m.start(0)] + self.commenttags[cmt_index][m.end(0):]
        self.__updateTags()

    def setDate(self, date):
        date = automagicallyConvertDate(date)
        if date is None:
            return self
        return self.addTag("date", date.isoformat())

    def getDate(self) -> Optional[datetime.date]:
        dtag = self.getTag("date")
        if not dtag:
            return None
        ## an invalid datestring in a tag date ist not allowed and will raise an exception
        return parseDateString(dtag)

    def addPostPostingAssertAmount(self, amt):
        self.post_posting_assert_amount = amt
        return self

    # @arg currency_amt_dict a dictionary of dictionaries of type string:string:Amount which for each account sums up amounts for individual currencies up to a certain point in a ledger
    def validatePostPostingAssertion(self, account_currency_amt_dict):
        if self.post_posting_assert_amount is None:
            return True
        if not self.account in account_currency_amt_dict:
            return True
        if not self.post_posting_assert_amount.currency in account_currency_amt_dict[self.account]:
            return True
        return round(account_currency_amt_dict[self.account][self.post_posting_assert_amount.currency].quantity,4) == round(self.post_posting_assert_amount.quantity,4)

    def strAligned(self, maxacctlen, maxamountlen):
        amtstr = self.__formatAmount()
        if len(amtstr) == 0:
            return "    %s%s" % (self.account,self.__formatComment())
        else:
            return "{:{fill}<4}{:{fill}<{maxacctlen}}{:{fill}<5}{:{fill}>{maxamountlen}}{commentstr}".format("",self.__formatAccount(),"",amtstr, fill=" ", maxacctlen=maxacctlen, maxamountlen=maxamountlen, commentstr=self.__formatComment())

    def __formatAccount(self):
        return "(%s)" % self.account if self.virtual else self.account

    def __formatComment(self):
        commenttags = self.commenttags
        if len(commenttags) == 0:
            return ""
        return ( "\n" if self.amount is None or isinstance(self.amount, NoAmount) else "") + "\n".join(map(lambda l: "{:{fill}<4}; {}".format("",l, fill=" "), commenttags))

    def __formatAmount(self):
        rv = "" if self.amount is None or isinstance(self.amount, NoAmount) or self.elided else str(self.amount)
        if not self.post_posting_assert_amount is None:
            rv += " = " + str(self.post_posting_assert_amount)
        return rv

    def __str__(self):
        return self.strAligned(0,0)


class Transaction(object):
    def __init__(self, name="", date=None, fileposition=None):
        self.setDate(date)
        self.desc=[]  # the lines before the transaction
        self.name=name.strip() # what hledger calls "desc". FIXME
        self.code=None
        self.comments=[] # comments after name
        self.postings=[]
        self.tags=defaultdict(list) # only informative, dict of string to list of matches in comment-strings, only informative
        self.fileposition=fileposition
        self.__updateTags()
        pass

    def copy(self):
        return copy.deepcopy(self)

    def __lt__(self, o):
        return self.date+str(self.code)+str(self.name) < o.date+str(o.code)+str(self.name)

    def __updateTags(self):
        def addTagMatch(tagname, tagvalue):
            self.tags[tagname.replace(",","").replace(":","")] += [tagvalue]

        ## clear tags
        self.tags=defaultdict(list)
        parseTagMatchesFromComments(self.comments, addTagMatch)

    ## description are journal comments before an transaction (not very aptly named... TODO)
    def addDescription(self, desc):
        self.desc += [desc.strip()]
        return self

    def setCode(self, code):
        self.code=code.strip() if isinstance(code, str) else None
        return self

    ## comment is next to transaction name or after transaction name
    def addComment(self, comment):
        if isinstance(comment, str):
            comment = comment.strip()
            if len(comment) > 0:
                self.comments.append(comment)
                self.__updateTags()
        return self

    def addTag(self,tag,taginfo=""):
        if taginfo is None:
            taginfo=""
        if not isinstance(taginfo,str):
            taginfo=str(taginfo)
        taginfo = taginfo.strip(" ,\t\n:").replace(",","%2C").replace(":","%3A")
        tag = tag.strip(" ,\t\n:").replace(",","%2C").replace(":","%3A").replace(" ","%20")
        assert(tag.find(" ") < 0)
        assert(tag.find(",") < 0)
        assert(taginfo.find(",") < 0)
        if 0 == len(self.comments):
            self.comments.append("")
        if len(self.comments[0]) > 0:
            self.comments[0] += " "
        self.comments[0] += f"{tag}:{taginfo},"
        self.__updateTags()
        return self

    def getTag(self, tag) -> Optional[str]:
        rl = self.getTagList(tag)
        if len(rl) == 0:
            return None
        return rl[0]

    def getTagList(self, tag) -> List[str]:
        return [m.group(2) for m in self.tags[tag]]

    def changeTag(self, tag, taginfo="", tagindex=0):
        if not tag in self.tags:
            return
        if tagindex > len(self.tags[tag]):
            return
        taginfo = taginfo.strip(" ,\t\n:").replace(",","%2C").replace(":","%3A")
        m = self.tags[tag][tagindex]
        cmt_index = self.comments.index(m.string)
        assert(cmt_index >= 0)
        ## replace that part in the comment
        self.comments[cmt_index] = self.comments[cmt_index][:m.start(2)] + taginfo + "," + self.comments[cmt_index][m.end(0):]
        self.__updateTags()

    def rmTag(self, tag, tagindex=0, tagvalue=None):
        if not tag in self.tags:
            return
        if isinstance(tagvalue,str) and 0 == tagindex:
            tagindex = self.getTagList(tag).index(tagvalue)
        if tagindex > len(self.tags[tag]) or tagindex < 0:
            return
        m = self.tags[tag][tagindex]
        cmt_index = self.comments.index(m.string)
        assert(cmt_index >= 0)
        ## replace that part in the comment
        self.comments[cmt_index] = self.comments[cmt_index][:m.start(0)] + self.comments[cmt_index][m.end(0):]
        self.__updateTags()

    def setDate(self, date):
        self.date = automagicallyConvertDate(date)
        if self.date is None:
            self.date = datetime.date.today()
        return self

    def getDate(self) -> datetime.date:
        return self.date

    def setName(self, name):
        self.name=name.strip()
        return self

    def initTransaction(self, date, name, code=None, commenttags=""):
        self.name=name.strip()
        self.code=code.strip() if isinstance(code,str) else code
        self.addComment(commenttags)
        self.setDate(date)
        return self

    def prependPosting(self, posting):
        assert(isinstance(posting,Posting))
        self.postings.insert(0,posting)
        return self

    def addPosting(self, posting):
        assert(isinstance(posting,Posting))
        self.postings.append(posting)
        return self

    def getPostingDate(self, posting):
        if isinstance(posting,int):
            if posting >= len(self.postings):
                raise KeyError
            posting = self.postings[posting]
        elif isinstance(posting,Posting):
            if not posting in self.postings:
                raise LookupError
        else:
            raise TypeError

        return automagicallyConvertDate(posting.getTag("date")) if not posting.getTag("date") is None else self.date

    def unelideJokerPostings(self, clear_elided_flag=False):
        jokerpostings = list([p for p in self.postings if p.amount is None or isinstance(p.amount,NoAmount)])
        if len(jokerpostings) == 0:
            return self # nothing to do
        if len(jokerpostings) >= 2:
            print(self, "\n------\n", list(map(str,jokerpostings)), file=sys.stderr)
        assert(len(jokerpostings) < 2)
        ## now find postings of currency that do not balance and fill in Amount into joker posting
        unitamounts = defaultdict(list)
        for p in self.postings:
            if clear_elided_flag:
                p.elided = False
            if p.amount.totalprice is None:
                ## add normal price
                unitamounts[p.amount.currency].append(p.amount)
            else:
                ## is a conversion, so we add the totalprice
                unitamounts[p.amount.totalprice.currency].append(Amount(p.amount.sgn() * p.amount.totalprice.quantity, p.amount.totalprice.currency))
        for currency, alist in unitamounts.items():
            cur_sum = round(sum([a.quantity for a in alist]),4)
            ## if multiple currencies, skip all that sum to 0, except the last, because if there is only one, we want a `0 CUR` here
            if 0 == cur_sum and len(unitamounts.keys()) > 1:
                continue
            jokerpostings[0].amount = Amount(-1*cur_sum, currency)
            break
        ## check if uneliding worked, or if all sums where == 0
        if jokerpostings[0].amount is None or isinstance(jokerpostings[0].amount,NoAmount):
            ## then just add 0 with a random currency
            jokerpostings[0].amount = Amount(0, list(unitamounts.keys())[0])
        return self

    def isBalanced(self):
        """ group all amounts of all postings by currency
            and check that each group's sum equals 0
            if there is a jokerposting, transaction automatically balances
        """
        num_jokerpostings = len(list([1 for p in self.postings if p.amount is None or isinstance(p.amount,NoAmount)]))
        if num_jokerpostings == 1:
            return True
        assert(num_jokerpostings < 2)
        unitamounts = defaultdict(float)
        conversions = defaultdict(set)
        for p in self.postings:
            if "currency" in p.amount.__dict__ and len(p.amount.currency) > 0:
                unitamounts[p.amount.currency] += p.amount.quantity
                if not p.amount.totalprice is None and len(p.amount.totalprice.currency) > 0:
                    unitamounts[p.amount.totalprice.currency] += p.amount.totalprice.quantity * p.amount.sgn()
                    conversions[p.amount.totalprice.currency].add(p.amount.currency)
        currency_balances = {}
        for currency, sum in unitamounts.items():
            currency_balances[currency] = round(sum,4) == 0
        if all(currency_balances.values()):
            return True
        ## balanced currency, means that converted currencies does not need to be balanced
        for balanced_currency in [c for (c,doesbalance) in currency_balances.items() if doesbalance]:
            if balanced_currency in conversions:
                for cc in conversions[balanced_currency]:
                    currency_balances[cc] = True
        return all(currency_balances.values())

    def findPostingWithAccount(self, account):
        return [x for x in self.postings if x.account == account]

    def findPostingWithAccountCurrency(self, account, currency):
        return [x for x in self.postings if x.account == account and x.amount.currency == currency]

    def isEmpty(self):
        return self.name == "" and len(self.postings) == 0

    def mergeInPostingsFrom(self,transaction):
        """ for each posting in transaction, add the amount to an existing posting with the same account or add it to the posting of no posting with the same account exists

            Note: does not necessarily mean that account names are uniqe within the postings, since self.postings could still contain multiple postings with the same account
                  use self.reduceDepth(None) beforehand to make sure account names are uniq
        """
        self.unelideJokerPostings(clear_elided_flag=True)
        transaction.unelideJokerPostings(clear_elided_flag=True)
        for p in transaction.postings:
            corresponding_postings = self.findPostingWithAccountCurrency(p.account, p.amount.currency)
            if len(corresponding_postings) == 1:
                corresponding_postings[0].amount.add(p.amount)
            else:
                self.addPosting(p)
        return self

    def reduceDepth(self, depth):
        """ reduces depth (number of elements separated by account_separator_) of accounts and merges posting with same account
            Called with depth=None, just merges postings with same account within the transaction
        """
        for pidx in range(0,len(self.postings)):
            if pidx >= len(self.postings):
                break
            p = self.postings[pidx]
            p.account = depthLimitAccountName(p.account, depth)
            others = [x for x in self.postings[pidx+1:] if x != p and x.amount.currency == p.amount.currency and depthLimitAccountName(x.account,depth) == p.account]
            for x in others:
                p.amount.add(x.amount)
                del self.postings[self.postings.index(x)]
        return self

    def willStringifySanely(self):
        """ check that there is at most one elided posting and it is not different from a potential Jokerposting
        """
        num_elided_posting = len(list([1 for p in self.postings if p.elided]))
        num_non_elided_jokerpostings = len(list([1 for p in self.postings if p.elided == False and (p.amount is None or isinstance(p.amount,NoAmount))]))

        return num_elided_posting + num_non_elided_jokerpostings <= 1

    def __str__(self):
        lines = []
        commenttags = []
        ## put first comment line right next to transaction and tags after that
        if len(self.comments) > 0:
            commenttags.append(self.comments[0])
        if len(commenttags) > 0:
            commenttags.insert(0," ;")
        lines += map(lambda s: "; %s" % s, self.desc)
        lines.append(" ".join(filter(len,[self.date.strftime(dateformat_hledger_iso_),"(%s)" % self.code if not self.code is None and len(self.code) > 0 else "", self.name]+commenttags)))
        if len(self.comments) > 1:  #are there even more comments?
            lines += map(lambda s: "    ; %s" % s, self.comments[1:])
        if len(self.postings) > 0:
            maxacctlen = max([len(p.account) for p in self.postings])
            maxamountlen = max([len(str(p.amount)) for p in self.postings])
            lines += [ p.strAligned(maxacctlen, maxamountlen) for p in self.postings ]
        return "\n".join(lines)

    def writeUpdateIntoSourceFile(self) -> int:
        """ updates the transaction in the file it was read from
            @return signed integer representing the change in line count (new - original)
        """
        if self.fileposition is None:
            raise ValueError("Transaction has no fileposition set, cannot update in file")
        if not self.willStringifySanely():
            raise ValueError("Transaction has NoAmount and elided-flag set on different postings. Won't write!")
        newblock = str(self)
        linecount_diff = self.fileposition.replaceWithStr(newblock)
        self.fileposition.endline += linecount_diff  # update file position info
        return linecount_diff


def createTempAccountsForAndConvertFromMultiDatePostings(journal):
    """ splits multi-date transactions into multiple transactions that use a temporary account between them
        @arg journal a list of transactions
        @return journal list of transactions without multi-date transactions but additional transaction that use an additional account
    """
    rj = []
    for t in journal:
        tpn = t.copy()
        tpn.unelideJokerPostings()
        mydates=defaultdict(list)
        for p in tpn.postings:
            mydates[tpn.getPostingDate(p)].append(p)
        if 1 == len(mydates):
            yield(t)
        else:
            transferaccount="temp:"+str(uuid.uuid1())
            for date, postinglist in mydates.items():
                tpns = copy.copy(tpn) # don't copy postings
                tpns.setDate(date)
                tpns.postings = postinglist
                tpns.addPosting(Posting(transferaccount,NoAmount()))
                yield(tpns)


# WARNING this will return a modified journal with unelided JokerPostings
# Which should be ok, since originally elided postings are marked as elided and will still be printed as elided
def runningSumOfJournal(journal):
    """ conmputes a running per account balance after each transaction
        @arg journal a list of transactions
        @returns [(t:Transaction, runsum:{acct:{currency:amt}}, assertionsok:bool)]

        postings within one transaction can have individual and differing dates, so you have two options:
            - run createTempAccountsForAndConvertFromMultiDatePostings() beforehand
            - do nothing but be aware that balances/sums may be incorrect and asserts may fail (TODO / FIXME / silently remember those t and change balances but what about posting-dates in the relative past?)
    """
    acct_currency_amt_dict = defaultdict(lambda: defaultdict(lambda: Amount(0,"")))
    assrt = True
    for t_orig in journal:
        t = t_orig.copy().unelideJokerPostings()
        for p in t.postings:
            if isinstance(p.amount,Amount) and len(p.amount.currency)>0 and p.amount.quantity != 0:
                acct_currency_amt_dict[p.account][p.amount.currency] += p.amount
            assrt = assrt and p.validatePostPostingAssertion(acct_currency_amt_dict)
        yield(t, copy.deepcopy(acct_currency_amt_dict), assrt)

def sumUpJournalVerifyAssertions(journal, abort_on_assrtfail=False):
    acct_currency_amt_dict = defaultdict(lambda: defaultdict(lambda: Amount(0,"")))
    assrt = True
    for t_orig in journal:
        t = t_orig.copy().unelideJokerPostings()
        for p in t.postings:
            if isinstance(p.amount,Amount) and len(p.amount.currency)>0 and p.amount.quantity != 0:
                try:
                    acct_currency_amt_dict[p.account][p.amount.currency] += p.amount
                except Exception as e:
                    print(str(t))
                    raise(e)
            assrt = assrt and p.validatePostPostingAssertion(acct_currency_amt_dict)
            if abort_on_assrtfail and assrt == False:
                return (acct_currency_amt_dict, (assrt, t_orig, p))
    return (acct_currency_amt_dict, assrt)

def showSums(acct_currency_amt_dict, acct_filter=[]):
    rv=""
    maxacctlen = max([len(a) for a in acct_currency_amt_dict.keys()])
    for acct, currency_dict in acct_currency_amt_dict.items():
        if acct_filter and not acct in acct_filter:
            continue
        if len(currency_dict) == 1:
            rv+="{:{fill}<{maxacctlen}}{:{fill}<4}{:}\n".format(acct,"",str(list(currency_dict.values())[0]), fill=" ", maxacctlen=maxacctlen)
        else:
            rv+="%s\n" % (acct,)
            for currency, amt in currency_dict.items():
                rv+="    %s\n" % (amt,)
    return rv

# runningSumOfJournal -> runningSumOfJournal
def filterRunningSum(running_sum_journal, fromdate=None, todate=None, account=None, onlybalanced=False, all_given_accounts_must_occur_in_txn=False, match_full_account_name=True):
    if isinstance(account, str):
        account = [account]
    if isinstance(account, list):
        account = set(account)
    assert(account is None or isinstance(account, set))
    fromdate=automagicallyConvertDate(fromdate)
    todate=automagicallyConvertDate(todate)
    for (t, acct_currency_amt_dict, assrt) in running_sum_journal:
        if onlybalanced and assrt == False:
            continue
        if isinstance(fromdate, datetime.date) and t.date < fromdate:
            continue
        if isinstance(todate, datetime.date) and t.date > todate:
            continue
        if isinstance(account, set):
            txn_accounts = [p.account for p in t.postings]
            if not match_full_account_name:
                txn_accounts_partlist = [a.split(':') for a in txn_accounts]
                txn_accounts_and_parents = [ ":".join(parts[0:a_range+1]) for parts in txn_accounts_partlist for a_range in range(0,len(parts))]
                txn_accounts = set(txn_accounts_and_parents) # make it unique
            if all_given_accounts_must_occur_in_txn:
                if len(account.intersection(txn_accounts)) != len(account):
                    continue
            else:
                ## at least one given account must appear in a transaction to be included in the filter
                if len(account.intersection(txn_accounts)) == 0:
                    continue
        yield (t, acct_currency_amt_dict, assrt)

# runningSumOfJournal -> Register: [t.date, acct_currency_amt_dict] with t.date being uniqe
def registerFromRunningSum(running_sum_journal):
    last_date = None
    last_acct_currency_amt_dict = None
    for (t, acct_currency_amt_dict, assrt) in running_sum_journal:
        #skip all entries expect the latest of each day
        if last_date is None:
            last_date = t.date
        if t.date != last_date:
            yield(last_date, last_acct_currency_amt_dict)
        last_date = t.date
        last_acct_currency_amt_dict = acct_currency_amt_dict
    yield(last_date, last_acct_currency_amt_dict)

def cashflowPerAccount(journal, fromdate=None, todate=None, addinsubaccounts=False):
    acct_currency_accts_cashflow_dict = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    assrt = True
    fromdate = automagicallyConvertDate(fromdate)
    todate = automagicallyConvertDate(todate)
    for t in journal:
        if isinstance(fromdate, datetime.date) and t.date < fromdate:
            continue
        if isinstance(todate, datetime.date) and t.date > todate:
            continue
        t = t.copy().unelideJokerPostings()
        neg_postings = []
        neg_sum = 0.0
        pos_postings = []
        pos_sum = 0.0
        for p in t.postings:
            if isinstance(p.amount,Amount) and len(p.amount.currency)>0 and p.amount.quantity != 0:
                if p.amount.quantity < 0:
                    neg_postings.append(p)
                    neg_sum += p.amount.quantity
                else:
                    pos_postings.append(p)
                    pos_sum += p.amount.quantity
        if round(pos_sum + neg_sum,4) != 0.0:
            # CONVERSION involved !!!
            # SKIP FOR NOW
            print("NOT HANDLING CONVERSION YET")
            print(str(t))
            continue
        neg_pos_fracts = [p.amount.quantity / neg_sum for p in neg_postings]
        pos_pos_fracts = [p.amount.quantity / pos_sum for p in pos_postings]
        for np, nfrac in zip(neg_postings, neg_pos_fracts):
            currency = np.amount.currency
            for pp, pfrac in zip(pos_postings, pos_pos_fracts):
                dest_quantity = round(np.amount.quantity * pfrac, 4) # np amount geht zu pfrac in den paccount
                src_quantity = round(pp.amount.quantity * nfrac, 4)  #pp amount geht zu nfrac in den naccount
                acct_currency_accts_cashflow_dict[np.account][currency][pp.account] += dest_quantity
                acct_currency_accts_cashflow_dict[pp.account][currency][np.account] += src_quantity
                if addinsubaccounts:
                    for parent_account in generateListOfParentAccountsFromChildAccount(np.account):
                        acct_currency_accts_cashflow_dict[parent_account][currency][pp.account] += dest_quantity
                    for parent_account in generateListOfParentAccountsFromChildAccount(pp.account):
                        acct_currency_accts_cashflow_dict[parent_account][currency][np.account] += src_quantity
    return acct_currency_accts_cashflow_dict

def histogramOfJournal(journal, max_name_compare_len=None, common_name_threshold=2):
    name_counts = defaultdict(int)
    acct_counts = defaultdict(int)
    name_sum = 0
    acct_sum = 0
    for t in journal:
        name_counts[t.name[:max_name_compare_len]] += 1
        name_sum += 1
        for p in t.postings:
            acct_counts[p.account] += 1
            acct_sum += 1
    sorted_name_counts = sorted(name_counts.items(), key=lambda x:x[1], reverse=True)
    name_histogram_normalized = [ (n, float(v) / name_sum) for (n,v) in sorted_name_counts ]
    commonnamelist = list(map(lambda x: x[0], takewhile(lambda tpl: tpl[1] >= common_name_threshold, sorted_name_counts)))
    uncommonnamelist = list(map(lambda x: x[0], sorted_name_counts[len(commonnamelist):]))
    sorted_acct_counts = sorted(acct_counts.items(), key=lambda x:x[1], reverse=True)
    acct_histogram_normalized = [ (n, float(v) / acct_sum) for (n,v) in sorted_acct_counts ]
    return {"name":{"histogram":name_histogram_normalized, "counts":name_counts, "sum":name_sum, "common":commonnamelist, "uncommon":uncommonnamelist},
            "accounts":{"histogram":acct_histogram_normalized, "counts":acct_counts, "sum":acct_sum}}

def _get_last_day_of_month(dt):
    """Return the last day of the month for a given date."""
    _, last_day = calendar.monthrange(dt.year, dt.month)
    return datetime.date(dt.year, dt.month, last_day)

def _get_last_day_of_quarter(dt):
    """Return the last day of the quarter for a given date."""
    quarter = (dt.month - 1) // 3
    last_month = (quarter + 1) * 3
    _, last_day = calendar.monthrange(dt.year, last_month)
    return datetime.date(dt.year, last_month, last_day)

def _get_last_day_of_year(dt):
    """Return the last day of the year for a given date."""
    return datetime.date(dt.year, 12, 31)

def mergeByMonthQuarterYear(journal, mergeBy="month"):
    """Merge transactions by month, quarter, or year.
    
    The merged transaction will have the date set to the last day of the period:
    - month: last day of the month (e.g., 2015-08-31)
    - quarter: last day of the quarter (e.g., 2015-09-30 for Q3)
    - year: last day of the year (e.g., 2015-12-31)
    
    Args:
        journal: List of transactions
        mergeBy: "month", "year", "quarter", or a custom function that takes a date
                and returns a comparable value for grouping
    
    Yields:
        Merged transactions with dates set to the last day of the period
    """
    if callable(mergeBy):
        date_reformat_fun = mergeBy
    elif mergeBy == "month":
        date_reformat_fun = _get_last_day_of_month
    elif mergeBy == "year":
        date_reformat_fun = _get_last_day_of_year
    elif mergeBy == "quarter":
        date_reformat_fun = _get_last_day_of_quarter
    else:
        raise ValueError(f"Invalid mergeBy value: {mergeBy}. Expected 'month', 'year', 'quarter', or a callable.")

    if len(journal) == 0:
        return []
    
    sortedjournal = sortTransactionsByDate(journal)
    ## depthLimitAccountName(None) makes sure mergeInPostingsFrom works correctly, 
    ## as it first makes sure that accounts are unique within a transaction's postings
    lastt = sortedjournal[0].copy().reduceDepth(None)
    lastt.date = date_reformat_fun(lastt.date)
    
    for t in sortedjournal[1:]:
        nextdate = date_reformat_fun(t.date)
        if lastt.date == nextdate:
            lastt.mergeInPostingsFrom(t)
        else:
            yield(lastt)
            lastt = t.copy().reduceDepth(None)
            lastt.date = date_reformat_fun(lastt.date)
    yield(lastt)



re_amount_str_3captures = r"([€$]|[a-zA-Z]+)?\s*((?:-\s?)?[0-9.,]+)\s*([€$]|[a-zA-Z]+)?"
re_account_str = r"(?:[^ \t\n\r\f\v;]| [^ \t\n\r\f\v;])+"
re_journalcommentline = re.compile(r"^;(.+)$")
re_commentline = re.compile(r"^\s\s+;(.+)$")
re_transaction = re.compile(r"^([0-9][-.0-9/]+)(?:=[-.0-9/]+)?\s+(?:\(([^);]+)\)\s+)?([^;]*)(?:\s*;(.*))?$")
re_posting = re.compile(r"^\s\s+("+re_account_str+r")(?:\s\s+"+re_amount_str_3captures+r"(?:\s*(@@?)\s*"+re_amount_str_3captures+r")?(?:\s*=\s*"+re_amount_str_3captures+r")?)?(?:\s+;(.+))?")
re_include = re.compile(r"^include\s+(.+)\s*$")
re_commentblock_begin = re.compile(r"^comment\s*$")
re_commentblock_end = re.compile(r"^end comment\s*$")
##re_tags_ = re.compile("(?:\s|^)(\S+):(\S*)") ## old non-hledger-format-conform tag parser. Once could use this and print.py to fix files with broken tags
# re_tags_ = re.compile(r"(?:\s|^)(\S+):([^,]+)?(?!\S+:)(?:,|$)")
re_tags_ = re.compile(r"(?:\s|^)(\S+):((?:[^,:](?!\S+:))+)?(?:,?)") ## match even whitespace in tag value, unless a new tag: is started

def automagicallyConvertDate(somedate) -> Optional[datetime.date]:
    if somedate is None:
        return None
    elif isinstance(somedate, str):
        if 0 == len(somedate):
            return None
        return parseDateString(somedate)
    elif isinstance(somedate, datetime.datetime):
        return somedate.date()
    elif isinstance(somedate, datetime.date):
        return somedate
    raise ValueError("Could not convert into date: "+str(somedate))

def parseDateString(dstr):
    for df in [dateformat_hledger_iso_, dateformat_hledger_csvexport_, dateformat_hledger_dot_]:
        try:
            return datetime.datetime.strptime(dstr, df).date()
        except:
            pass
    raise Exception("Could not parse datestring: "+dstr)

def parseAmount(c1,quantity,c2):
    if c1 is None and quantity is None and c2 is None:
        return NoAmount()
    currency = c2 if c1 is None else c1
    if currency is None:
        currency = ""
    cp = quantity.find(",")
    dp = quantity.find(".")
    if cp >= 0 and dp >= 0:
        if dp > cp:
            quantity = quantity.replace(",","")
        else:
            quantity = quantity.replace(".","")
    quantity = quantity.replace(",",".")
    return Amount(quantity, currency)

def separateAndAddCommentAndTags(commenttagstr, f_addcomment, f_addtag):
    if not isinstance(commenttagstr, str):
        return
    commenttagstr = commenttagstr.strip()
    if len(commenttagstr) == 0:
        return
    for t,a in re_tags_.findall(commenttagstr):
        f_addtag(t,a)
    cmt = re_tags_.sub("",commenttagstr).strip()
    if len(cmt)>0:
        f_addcomment(cmt)

def parseTagMatchesFromComments(commentlist: List[str], f_addtag):
    for commenttagstr in commentlist:
        if not isinstance(commenttagstr, str):
            continue
        if len(commenttagstr) == 0:
            continue
        for m in re_tags_.finditer(commenttagstr):
            f_addtag(m.group(1), m)

def parseJournal(jreader):
    current_filepath = ""
    current_lineno = -1
    try:
        current_filepath = jreader.name
    except AttributeError:
        pass
    journal = []
    within_commentblock = False
    for line in jreader:
        current_lineno += 1
        line = line.strip("\n\r")
        if not re_commentblock_end.match(line) is None:
            within_commentblock = False
            continue
        if within_commentblock:
            continue
        if not re_commentblock_begin.match(line) is None:
            within_commentblock = True
            continue
        m = re_journalcommentline.match(line)
        if not m is None:
            if len(journal) == 0 or not journal[-1].isEmpty():
                journal.append(Transaction(fileposition=FileSlice(current_filepath, current_lineno, current_lineno)))
            journal[-1].addDescription(m.group(1))
            continue
        m = re_commentline.match(line)
        if not m is None:
            if len(journal) == 0:
                journal.append(Transaction(fileposition=FileSlice(current_filepath, current_lineno, current_lineno)))
            if len(journal[-1].postings) == 0:
                # separateAndAddCommentAndTags(m.group(1), journal[-1].addComment, journal[-1].addTag)
                journal[-1].addComment(m.group(1))
            else:
                # separateAndAddCommentAndTags(m.group(1), journal[-1].postings[-1].addComment, journal[-1].postings[-1].addTag)
                journal[-1].postings[-1].addComment(m.group(1))
            journal[-1].fileposition.endline=current_lineno
            continue
        m = re_transaction.match(line)
        if not m is None:
            if len(journal) == 0 or not journal[-1].isEmpty():
                journal.append(Transaction(fileposition=FileSlice(current_filepath, current_lineno, current_lineno)))
            journal[-1].initTransaction(*m.group(1,3,2,4))
            continue
        m = re_posting.match(line)
        if not m is None:
            amt = parseAmount(*m.group(2,3,4))
            if m.group(5) == "@":
                amt.addPerUnitPrice(parseAmount(*m.group(6,7,8)))
            elif m.group(5) == "@@":
                amt.addTotalPrice(parseAmount(*m.group(6,7,8)))
            post_posting_assert_amount = parseAmount(*m.group(9,10,11))
            journal[-1].addPosting(Posting(m.group(1), amt, assertamount=post_posting_assert_amount))
            # separateAndAddCommentAndTags(m.group(12), journal[-1].postings[-1].addComment, journal[-1].postings[-1].addTag)
            journal[-1].postings[-1].addComment(m.group(12))
            journal[-1].fileposition.endline=current_lineno
            continue
        m = re_include.match(line)
        if not m is None:
            try:
                includepath = os.path.join(os.path.split(jreader.name)[0],m.group(1))
            except:
                includepath = m.group(1)
            if os.path.isfile(includepath):
                with open(includepath) as includefh:
                    journal += parseJournal(includefh)
            else:
                print("ERROR: Could not find include file: %s" % includepath, file=sys.stderr)
            continue
    return journal

### query hledger for accounts
def queryHledgerForAccountList(ledgerpath, depth=None, args=[]):
    stdout = subprocess.Popen(['hledger'] + ([] if ledgerpath is None or not os.path.exists(ledgerpath) else ['-f', ledgerpath])  + ["accounts","--ignore-assertions"] + ([] if depth is None or not isinstance(depth,int) else ["--depth",str(depth)] + args),stdout=subprocess.PIPE).communicate()[0]
    ## python asumes subprocess.PIPE i.e. stdout is ascii encoded
    return list(filter(len,codecs.decode(stdout,"utf-8").split(u"\n")))

### query hledger for accounts and their balance
re_account_balance = re.compile(r"\s+"+ re_amount_str_3captures + r"\s+("+re_account_str+r")$")
def queryHledgerForAccountListWithBalance(ledgerpath, depth=None, args=[]):
    stdout = subprocess.Popen(['hledger'] + ([] if ledgerpath is None or not os.path.exists(ledgerpath) else ['-f', ledgerpath])  + ["balance","--cost", "--flat", "--no-elide", "--empty"] + ([] if depth is None or not isinstance(depth,int) else ["--depth",str(depth)]+args),stdout=subprocess.PIPE).communicate()[0]
    ## python asumes subprocess.PIPE i.e. stdout is ascii encoded
    rv = []
    for l in codecs.decode(stdout,"utf-8").split(u"\n")[:-2]:
        m = re_account_balance.match(l)
        if not m is None:
            rv.append((m.group(4),parseAmount(*m.group(1,2,3))))
    return rv


### query hledger in 'print' mode with given parameters
def getHLedger(ledgerpath, hledger_filter=[], depth=None):
    assert(isinstance(hledger_filter,list))
    stdout = subprocess.Popen(['hledger'] + ([] if ledgerpath is None or not os.path.exists(ledgerpath) else ['-f', ledgerpath]) + ["print"] + ([] if depth is None or not isinstance(depth,int) else ["--depth",str(depth)]) + hledger_filter, stdout=subprocess.PIPE).communicate()[0]
    return codecs.decode(stdout,"utf-8").split(u"\n")

def depthLimitAccountName(acct, depth=None):
    if depth is None:
        return acct
    return account_separator_.join(acct.split(account_separator_)[:depth])

## e.g.: "assets:current:cash:register" -> ["assets", "assets:current", "assets:current:cash"]
def generateListOfParentAccountsFromChildAccount(acct):
    sa = acct.split(account_separator_)
    ids = [range(0,x) for x in range(1,len(sa))]
    return [account_separator_.join(map(sa.__getitem__, aids)) for aids in ids]

## e.g.: assets:current -> ["assets:current:cash:register", "assets:current:checking-raika", "assets:current:cash:personX", ...]
def getListOfChildAccounts(fullacctlist, parentaccount):
    return [a for a in fullacctlist if a.startswith(parentaccount+account_separator_)]

### sorts Journal by date but also keeps original order for postings with the same date
def sortTransactionsByDate(transactions):
    return [ t for a,b,t in sorted([(t.date,num,t) for t,num in zip(transactions,range(0,len(transactions)))])]

def getDateOfPosting(transaction, account) -> datetime.date:
    pl = transaction.findPostingWithAccount(account)
    if len(pl) > 0 and pl[0].getDate():
        return pl[0].getDate()
    else:
        return transaction.date

def sortTransactionsByPostingDateInAccount(transactions, account):
    return [ t for a,b,t in sorted([(getDateOfPosting(t,account),num,t) for t,num in zip(transactions,range(0,len(transactions)))])]

def str_rstrip_max(s, chars, remove_max_chars):
    slen = len(s)
    removed = 0
    while removed < slen and removed < remove_max_chars and s[slen-removed-1] in chars:
        removed += 1
    return s[0:slen-removed]


if __name__ == '__main__':
    import unittest
    import io
    from pprint import pprint

    test_journal1 = io.StringIO("""; journal created 2015-09-23 by hledger
; some journal comment
; next line of journal comment
2013-08-19 DealExtreme  ; paypal:XYXYXYXYXYABC,
    liability:visa              -60.3 EUR = -60.3 EUR
    assets:gadgets:hackmake      30.3 EUR
    expenses:geocaching          30.3 EUR

2013-08-29 DealExtreme  ; Eine Nette:Transaktion, paypal:ZZZZ-XXX-XXX,
    liability:visa            -31 EUR
    assets:gadgets           2.09 EUR    ; Mask
    assets:apparel          13.41 EUR    ; Sonnenbrille
    expenses:geocaching     14.96 EUR    ; Akku
    expenses:bicycle

2013-10-28 Bitcoin ASIC Miner  ; IT Solutions ; paypal:3V33333VVVVVV,
    liability:visa     -139 EUR
    assets:gadgets      139 EUR    ; gadget:,
    ; first comment about that gadget
    ; second comment about that gadget

2014-01-22 DealExtreme  ; paypal:4H44H4H4H,
    liability:visa              -49.83 EUR
    assets:gadgets:hackmake       5.47 EUR
    assets:gadgets               19.62 EUR    ; Starry Green Laserpointer
    assets:gadgets                6.85 EUR    ; FM Transmitter
    expenses:handy               17.89 EUR

""")

    test_journal2 = io.StringIO("""; journal created 2015-09-23 by hledger
; some journal comment
; next line of journal comment
2013-08-19 DealExtreme  ; paypal:XYXYXYXYXYABC,
    liability:visa              -60.3 EUR
    assets:inventory             2 Waffeln @@ 1 EUR = 2 Waffeln
    expenses:geocaching          57.3 EUR
    expenses:apparel             4 Waffeln @@ 2 EUR

2013-08-29 DealExtreme  ; Eine Nette Transaktion paypal:ZZZZ-XXX-XXX,
    liability:visa          -31 EUR = -91.3 EUR
    expenses:geocaching      10.7 EUR = 68 EUR
    expenses:apparel           -4 Waffeln @ 0.5 EUR = 0 Waffeln
    assets:inventory         7 Waffeln @ 0.5 EUR = 9 Waffeln
    assets:inventory         3 Autos @@ 3 EUR = 9 Waffeln
    expenses:bicycle

2013-08-30 Check
    expenses:bicycle  0 = 15.80 EUR

""")

    test_journal3 = io.StringIO("""
2013-08-19 DealExtreme  ; paypal:XYXYXYXYXYABC,
    liability:visa              -60.3000 EUR = -60.3010 EUR
    expenses:geocaching
""")

    test_journal4 = io.StringIO("""
2015-08-19 Transaction 1
    liability:mastercard        -60.3 EUR
    expenses:geocaching          20.3 EUR ; item 1
    expenses:geocaching          40.0 EUR ; item 2

2015-08-29 Transaction 2  ; yet another one
    liability:mastercard    -31 EUR
    expenses:apparel         15 EUR
    expenses:geocaching      15 EUR
    assets:inventory          1 EUR

2015-09-10 Transaction 3  ; yeah yeah
    assets:inventory         -1 EUR
    expenses:geocaching       1 EUR
""")

    class TextParseWrite(unittest.TestCase):
        def test_ParseWrite(self):
            output_journal = io.StringIO()
            test_journal1.seek(0)
            j = parseJournal(test_journal1)
            for t in j:
                output_journal.write("%s\n\n" % t)
            self.maxDiff=None
            self.assertEqual(test_journal1.getvalue(),output_journal.getvalue())

        def test_Assertions(self):
            test_journal2.seek(0)
            j = parseJournal(test_journal2)
            s,asstr = sumUpJournalVerifyAssertions(sortTransactionsByDate(j))
            print(showSums(s))
            self.assertEqual(asstr, True)
            self.assertEqual(s["assets:inventory"]["Waffeln"].quantity, 9)
            self.assertEqual(s["assets:inventory"]["Waffeln"].currency, "Waffeln")
            self.assertEqual(s["assets:inventory"]["Waffeln"].totalprice.quantity, 4.5)
            self.assertEqual(s["assets:inventory"]["Waffeln"].totalprice.currency, "EUR")
            self.assertEqual(s["assets:inventory"]["Waffeln"].perunitprice.quantity, 0.5)
            self.assertEqual(s["assets:inventory"]["Waffeln"].perunitprice.currency, "EUR")
            self.assertEqual(s["assets:inventory"]["Autos"].quantity, 3)
            self.assertEqual(s["assets:inventory"]["Autos"].currency, "Autos")
            self.assertEqual(s["assets:inventory"]["Autos"].totalprice.quantity, 3)
            self.assertEqual(s["assets:inventory"]["Autos"].totalprice.currency, "EUR")
            self.assertEqual(s["assets:inventory"]["Autos"].perunitprice.quantity, 1)
            self.assertEqual(s["assets:inventory"]["Autos"].perunitprice.currency, "EUR")
            self.assertEqual(s["expenses:apparel"]["Waffeln"].quantity, 0)
            self.assertEqual(s["expenses:apparel"]["Waffeln"].currency, "Waffeln")
            self.assertEqual(s["expenses:apparel"]["Waffeln"].totalprice.quantity, 0)
            self.assertEqual(s["expenses:apparel"]["Waffeln"].totalprice.currency, "EUR")
            self.assertEqual(s["expenses:apparel"]["Waffeln"].perunitprice.quantity, 0.5)
            self.assertEqual(s["expenses:apparel"]["Waffeln"].perunitprice.currency, "EUR")

            ss = runningSumOfJournal(parseJournal(test_journal3))
            self.assertEqual(list(ss)[0][2], False)

        def test_Histogram(self):
            test_journal1.seek(0)
            j = parseJournal(test_journal1)
            h = histogramOfJournal(j)
            pprint(h)
            self.assertEqual(h["name"]["sum"], 4)
            self.assertEqual(h["name"]["counts"]["DealExtreme"], 3)
            self.assertEqual(len(h["name"]["histogram"]), 2)
            self.assertEqual(h["name"]["histogram"][0][0], "DealExtreme")
            self.assertEqual(round(h["name"]["histogram"][0][1],2), 0.75)
            self.assertEqual(h["accounts"]["sum"], 15)
            self.assertEqual(h["accounts"]["counts"]["liability:visa"], 4)
            self.assertEqual(round(h["accounts"]["histogram"][0][1],2), 0.27)

        def test_MonthMerge(self):
            test_journal4.seek(0)
            j = parseJournal(test_journal4)
            mi = mergeByMonthQuarterYear(j, mergeBy="month")
            nextt = next(mi)
            self.assertEqual(nextt.date, datetime.date(2015, 8, 31))
            self.assertEqual(len(nextt.postings), 4)
            self.assertEqual(nextt.postings[0].account, "liability:mastercard")
            self.assertEqual(nextt.postings[1].account, "expenses:geocaching")
            self.assertEqual(nextt.postings[3].account, "assets:inventory")
            nextt = next(mi)
            self.assertEqual(nextt.date, datetime.date(2015, 9, 30))
            self.assertEqual(len(nextt.postings), 2)
            self.assertRaises(StopIteration, next, mi)

            test_journal4.seek(0)
            j = parseJournal(test_journal4)
            mi = mergeByMonthQuarterYear(j, mergeBy="quarter")
            nextt = next(mi)
            self.assertEqual(nextt.date, datetime.date(2015, 9, 30))  # Q3 ends Sept 30
            self.assertEqual(len(nextt.postings), 4)
            self.assertEqual(nextt.postings[0].account, "liability:mastercard")
            self.assertEqual(nextt.postings[1].account, "expenses:geocaching")
            self.assertEqual(nextt.postings[3].account, "assets:inventory")
            self.assertEqual(nextt.postings[3].amount.quantity, 0)
            self.assertRaises(StopIteration, next, mi)
            
            test_journal4.seek(0)
            j = parseJournal(test_journal4)
            mi = mergeByMonthQuarterYear(j, mergeBy="year")
            nextt = next(mi)
            self.assertEqual(nextt.date, datetime.date(2015, 12, 31))
            self.assertEqual(len(nextt.postings), 4)
            self.assertRaises(StopIteration, next, mi)


    unittest.main()
