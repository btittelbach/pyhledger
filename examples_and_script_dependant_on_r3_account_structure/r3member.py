#!/usr/bin/python
# -*- coding: utf-8 -*-
import datetime
import dateutil.relativedelta

class R3Member(object):
	def __init__(self,name,nick):
		self.name=name.strip()
		self.nick=nick.strip()
		self.birthdate=None
		self.firstmonth=datetime.date.today() 
		## set to start of month and start with next month per default
		self.firstmonth += dateutil.relativedelta.relativedelta(months=1, days=1-self.firstmonth.day)
		self.lastmonth=None
		self.membershipfee=25.0
		self.contact_tel=[]
		self.contact_address=[]
		self.contact_email=[]
		self.contact_xmpp=[]
		self.special_regex=None
		self.note=None	

	def addtel(self,t):
		t=t.strip()
		if t:
			self.contact_tel.append(t)
	def addxmpp(self,t):
		t=t.strip()
		if t:
			self.contact_xmpp.append(t)
	def addaddress(self,t):
		t=t.strip()
		if t:
			self.contact_address.append(t)
	def addemail(self,t):
		t=t.strip()
		if t:
			self.contact_email.append(t)

	def addcontact(self,ctype,t):
		__contact_handlers={"email":self.addemail,"xmpp":self.addxmpp,"homeaddress":self.addaddress,"handy":self.addtel,"phone":self.addtel,"tel":self.addtel}		
		if ctype in __contact_handlers:
			__contact_handlers[ctype](t)


	def __str__(self):
		return str(self.__dict__)