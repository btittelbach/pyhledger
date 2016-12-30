#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys, os, io
import csv
import sqlite3 as lite
import itertools
import datetime
import dateutil.relativedelta
from r3member import R3Member
import dialogs

sqlite_db_=os.path.split(__file__)[0]+'/../Ledgers/members.sqlite'

def findMemberInSqLite(searchstr):
    con = lite.connect(sqlite_db_)
    cur = con.cursor()
    searchstr = "%"+searchstr+"%"
    cur.execute('Select p_id, p_name, p_nick, p_birthday, p_note from persons where p_name like ? or p_nick like ?',(searchstr,searchstr) )
    rows = cur.fetchall()
    if len(rows) == 0:
        print "Nobody found"
        return None
    if len(rows) > 1:
        print "More than one person found, using first match"
    member = R3Member(rows[0][1],rows[0][2])
    p_id = rows[0][0]
    if rows[0][3]:
        member.birthdate = datetime.datetime.strptime(rows[0][3], "%Y-%m-%d").date()
    member.note = rows[0][4]

    ## TODO
    member.firstmonth = None
    member.membershipfee = None

    cur = con.cursor()
    cur.execute('SELECT ct_type, c_contact FROM contact left join contacttype using (ct_id) where p_id=?', (p_id,))
    for row in cur.fetchall():
        member.addcontact(row[0],row[1])
    con.close()
    return member


def addMemberToSqLite(member):
    assert(isinstance(member,R3Member))
    try:
        con = lite.connect(sqlite_db_)

        cur = con.cursor()
        cur.execute('Insert into persons(p_name,p_nick,p_birthday,p_note) values (?,?,?,?)',(
                    member.name,
                    member.nick,
                    member.birthdate.isoformat() if isinstance(member.birthdate, datetime.date) else None,
                    member.note)
        )

        p_id = cur.lastrowid
        assert(isinstance(p_id,int))

        cur.execute('Insert into membership(p_id,m_firstmonth,m_lastmonth,m_fee) values (?,?,?,?)',(
                    p_id,
                    member.firstmonth.isoformat(),
                    member.lastmonth.isoformat() if isinstance(member.lastmonth, datetime.date) else None,
                    member.membershipfee))

        sql_contact_info = []
        for tel in member.contact_tel:
            sql_contact_info.append((p_id,1,tel))
        for email in member.contact_email:
            sql_contact_info.append((p_id,2,email))
        for address in member.contact_address:
            sql_contact_info.append((p_id,3,address))
        for xmpp in member.contact_xmpp:
            sql_contact_info.append((p_id,4,xmpp))

        cur.executemany('Insert into contact(p_id,ct_id,c_contact) values (?,?,?)',sql_contact_info)

        if member.special_regex:
            cur.execute('Insert into wiretransferregex(p_id,w_searchregex) values (?,?)',(p_id,member.special_regex))

        con.commit()
        con.close()

    except (lite.Error) as e:
        print("Error %s:" % e.args[0])
        sys.exit(1)

def makeWikiACL(member):
    assert(isinstance(member,R3Member))
    nick = member.nick.lower().replace(":","")
    return "%s:*\t%s\t16\n%s:*\t@ALL\t1" % ((nick,)*3)

def enterMemberWithGui():
    new_member = dialogs.showDialogNewMember()
    if new_member:
        addMemberToSqLite(new_member)
        dialogs.showInfoMessage("Successfully added to sqlite DB")
        wikiacl = makeWikiACL(new_member)
        print(wikiacl)
        dialogs.showInfoMessage(wikiacl)


if len(sys.argv) > 1:
    print findMemberInSqLite(sys.argv[1])
else:
    enterMemberWithGui()
