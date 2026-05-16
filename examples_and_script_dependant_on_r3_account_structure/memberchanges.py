#!/usr/bin/python3

import sys
import codecs
import textwrap
import os, io
import sqlite3 as lite
from datetime import datetime, date
import dateutil.relativedelta
from collections import defaultdict

sqlite_db_=os.path.split(__file__)[0]+'/../Ledgers/members.sqlite'
dateformat_monthonly_ = "%Y-%m"

def getVeryFirstMonth(con):
	cur = con.cursor()
	cur.execute("SELECT min(m_firstmonth) from membership")
	strdate = cur.fetchone()[0]
	rdate = date.fromisoformat(strdate())
	return normalizeDateToFirstInMonth(rdate)

### @return datetime.date with the day of given datetime.date set to 1
def normalizeDateToFirstInMonth(rdate):
    if rdate.day != 1:
        rdate += dateutil.relativedelta.relativedelta(days=1-rdate.day)
    return rdate

### returns results from membership table in sqlite db
### @return [(p_id, m_firstmonth :: datetime.date, m_lastmonth :: datetime.date || None, m_fee: float), (...), (...), ...]
def getMemberships(con):
	cur = con.cursor()
	cur.execute('SELECT p_id, m_firstmonth, m_lastmonth, m_fee from membership order by m_firstmonth')
	rows = cur.fetchall()
	print(rows)
	return [(r[0],date.fromisoformat(r[1]), date.fromisoformat(r[2]) if not (r[2] is None or len(r[2]) < 1) else None, r[3]) for r in rows]

### constants member event
evt_mstart_w_fee = "Membership period started with fee > 0"
evt_mstart_zero = "Membership period started with fee equal to 0"
evt_mend_w_fee = "Membership period with fee > 0 ended the month before"
evt_mend_zero = "Membership period with fee equal to 0 ended the month before"

### constants mstate
# mstate_joined = "Member {0} joins"
# mstate_joined_paused = "Member {0} joins only in name with paused membership"
# mstate_gone = "Member {0} is now gone"
# mstate_paused = "Member {0} pauses membership"
# mstate_unpaused = "Member {0} resumes previously paused membership"

mstate_joined = "+ Member {0} joins"
mstate_joined_paused = "Ø Member {0} joins only in name with paused membership"
mstate_gone = "- Member {0} is now gone"
mstate_paused = "↓ Member {0} pauses membership"
mstate_unpaused = "↑ Member {0} resumes previously paused membership"

### Helperclass, basically a struct with a __str__ method
### used to save per month chnages of members
class MemberChangeDict(dict):
	def __init__(self, *arg, **kw):
		super(MemberChangeDict, self).__init__(*arg, **kw)

	def setAndCheck(self, key, item):
		if key in self:
			## if member previously paid 0 and now starts paying something
			if (item == evt_mstart_w_fee and self[key] == evt_mend_zero) or (item == evt_mend_zero and self[key] == evt_mstart_w_fee):
				self[key] = mstate_unpaused
			## if member previously paid something and now starts paying 0
			if (item == evt_mstart_zero and self[key] == evt_mend_w_fee) or (item == evt_mend_w_fee and self[key] == evt_mstart_zero):
				self[key] = mstate_paused
			## if member previously paid something and from now on still pays something (although maybe a different ammount)
			if (item == evt_mstart_w_fee and self[key] == evt_mend_w_fee) or (item == evt_mend_w_fee and self[key] == evt_mstart_w_fee):
				del self[key]
		elif item in [evt_mstart_w_fee,evt_mstart_zero,evt_mend_w_fee,evt_mend_zero]:
			self[key] = item
		else:
			## ignore value
			pass

	### @return dict with items transformed mstate constants, if not already transformed in setitem
	def derive_states(self):
		mapping = {evt_mstart_w_fee:mstate_joined,evt_mstart_zero:mstate_joined_paused,evt_mend_w_fee:mstate_gone,evt_mend_zero:mstate_gone}
		rv = {}
		for k,v in self.items():
			if v in mapping.keys():
				rv[k] = mapping[v]
			else:
				rv[k] = v
		return rv

	def getTransformedString(self, member_id_to_name_dict):
		d = self.derive_states()
		s=""
		for k,v in d.items():
			s += v.format("%s aka %s" % member_id_to_name_dict[k])
			s += "\n"
		return s


### lists for each month, the members who joined, left or paused their membership
### @return dict of dates -> MemberChangeStruct
def extractMembershipChangesPerMonth(membership):
	mc_dates = defaultdict(lambda:MemberChangeDict())
	is_duration_paused_membership = lambda x: x == 0

	for p_id, fmonth, lmonth, m_fee in membership:
		if is_duration_paused_membership(m_fee):
			mc_dates[fmonth.strftime(dateformat_monthonly_)].setAndCheck(p_id, evt_mstart_zero)
		else:
			mc_dates[fmonth.strftime(dateformat_monthonly_)].setAndCheck(p_id, evt_mstart_w_fee)

		if lmonth:
			lmonth = normalizeDateToFirstInMonth(lmonth) + dateutil.relativedelta.relativedelta(months=1)
			if is_duration_paused_membership(m_fee):
				mc_dates[lmonth.strftime(dateformat_monthonly_)].setAndCheck(p_id, evt_mend_zero)
			else:
				mc_dates[lmonth.strftime(dateformat_monthonly_)].setAndCheck(p_id, evt_mend_w_fee)


	return mc_dates


### @return dict[ p_id :(p_nick,p_name) ] for all members
def getMemberNames(con):
	cur = con.cursor()
	cur.execute('SELECT p_id, p_nick, p_name from membership left join persons using (p_id) order by p_id')
	rows = cur.fetchall()
	return dict([(a,(b,c)) for a,b,c in rows])



con = lite.connect(sqlite_db_)
memberships = getMemberships(con)
member_name_nick = getMemberNames(con)
con.close()

member_changes = extractMembershipChangesPerMonth(memberships)
for month, changes in sorted(member_changes.items()):
	print(month)
	print(textwrap.indent(changes.getTransformedString(member_name_nick)," "*2))
