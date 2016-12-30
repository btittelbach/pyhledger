#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2011-2015 Author: Bernhard Tittelbach
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License v2 for more details.

# You should have received a copy of the GNU General Public License v2
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA
# or look here: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html

import sys,os
import wx
from r3member import R3Member
import datetime

_wxapp = wx.App(redirect=False)

def showSelectFileDialog(msg, preselected_file=None, wildcard=None, multiple=False, parent=None):
    """ show a wx.FileDialog
        @param preselected_file if given, change to this directory and select that file on dialog creation
        @param wildcard a wx.FileDialog wildcard string
        @param multiple boolean if selection of multiple files should be allowed
        @param parent parent window
        @retval None if dialog was aborted
        @retval str() if multiple==False: full path of selected file
        @retval [str(),str(),...] if multiple==True: list of strings of full paths of all selected files
    """
    dial_style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_PREVIEW
    if multiple:
        dial_style |= wx.FD_MULTIPLE
    dial = wx.FileDialog(parent, msg, os.path.dirname(preselected_file) if preselected_file else wx.EmptyString, preselected_file if preselected_file else wx.EmptyString, wildcard if wildcard else wx.FileSelectorDefaultWildcardStr, style=dial_style)
    if dial.ShowModal() == wx.ID_OK:
        if multiple:
            return dial.GetPaths()
        else:
            return dial.GetPath()
    else:
        return None

def showErrorMessage(msg, parent=None):
    """ show a simple error message
        @param msg error message to display
        @param parent parent window
    """
    dial = wx.MessageDialog(parent, msg, u"PySimPa", wx.ICON_ERROR)
    dial.ShowModal()

def showInfoMessage(msg, parent=None):
    """ show a simple information message
        @param msg info message to display
        @param parent parent window
    """
    dial = wx.MessageDialog(parent, msg, u"PySimPa", wx.ICON_INFORMATION)
    dial.ShowModal()

def showProgressInfo(msg, maximum=None, parent=None):
    """ show a progress information dialog
        @param msg info message to display
        @param parent parent window
    """
    progressdial = wx.ProgressDialog(title=u"PySimPa", message=msg, parent=parent, maximum=maximum, style = wx.PD_APP_MODAL | wx.PD_ELAPSED_TIME | wx.PD_AUTO_HIDE)
    return progressdial


class ProgressStdStream:
    def __init__(self, msg, maximum=None, dupe=False, update_with_stdout=True, parent=None):
        self.dlg = showProgressInfo(msg, maximum if maximum else 1, parent=parent)
        self.lastmsg = msg
        self.maximum = maximum
        self.curpos = 0
        self.oldstdout = sys.stdout
        self.dupe = dupe
        self.update_with_stdout = update_with_stdout
        sys.stdout = self

    def write(self, string):
        #wx.CallAfter(self.dlg.Pulse, string)
        msg = string if self.update_with_stdout else self.lastmsg
        if self.maximum:
            self.curpos += 1
            self.curpos %= self.maximum+1
            self.dlg.Update(self.curpos, msg)
        else:
            self.dlg.Pulse(msg)
        if __debug__ or self.dupe:
            self.oldstdout.write(string)

    def Pulse(self, msg):
        self.lastmsg = msg
        self.write(msg)

    def Destroy(self):
        sys.stdout = self.oldstdout
        self.dlg.Destroy()

class FileExistsValidator(wx.PyValidator):
    """ wx.Validator that checks if the text in an associated wx.TextCtrl corresponds to the path of an existing file

        @see documentation on wxWidgets Validator and dialogs
    """
    def __init__(self, errormsg):
        """ @param errormsg Message to display it this wx.TextCtrl value is not the path to an existing file """
        self.errormsg = errormsg
        wx.PyValidator.__init__(self)

    def Clone(self):
        return FileExistsValidator(self.errormsg)

    def Validate(self, win):
        textCtrl = self.GetWindow()
        isfile = os.path.isfile(textCtrl.GetValue())
        if not isfile:
            showErrorMessage(self.errormsg, parent=win)
            textCtrl.SetBackgroundColour("pink")
            textCtrl.SetFocus()
            textCtrl.Refresh()
        else:
            textCtrl.SetBackgroundColour(wx.SystemSettings_GetColour(wx.SYS_COLOUR_WINDOW))
            textCtrl.Refresh()
        return isfile

    def TransferToWindow(self):
        return True

    def TransferFromWindow(self):
        return True

class DateValidator(wx.PyValidator):
    """ wx.Validator that checks if the text in an associated wx.TextCtrl has corrent data

        @see documentation on wxWidgets Validator and dialogs
    """
    def __init__(self, errormsg, dateformat="%Y-%m-%d", emptyok=False):
        """ @param errormsg Message to display if this wx.TextCtrl value is not correct """
        self.errormsg = errormsg
        self.dateformat = dateformat
        self.emptyok=emptyok
        self.date = None
        wx.PyValidator.__init__(self)

    def Clone(self):
        return DateValidator(self.errormsg, self.dateformat,self.emptyok)

    def Validate(self, win):
        textCtrl = self.GetWindow()
        self.date = None
        if self.emptyok and len(textCtrl.GetValue().strip()) == 0:
            textCtrl.SetBackgroundColour(wx.SystemSettings_GetColour(wx.SYS_COLOUR_WINDOW))
            return True
        try:
            self.date = datetime.datetime.strptime(textCtrl.GetValue(), self.dateformat).date()
            textCtrl.SetBackgroundColour(wx.SystemSettings_GetColour(wx.SYS_COLOUR_WINDOW))
            return True
        except ValueError:
            textCtrl.SetBackgroundColour("pink")
            textCtrl.SetFocus()
            textCtrl.Refresh()
            return False

    def TransferToWindow(self):
        return True

    def TransferFromWindow(self):
        return True

class NotEmptyValidator(wx.PyValidator):
    """ wx.Validator that checks if the text in an associated wx.TextCtrl is not empty

        @see documentation on wxWidgets Validator and dialogs
    """
    def __init__(self, errormsg):
        """ @param errormsg Message to display if this wx.TextCtrl value is not correct """
        self.errormsg = errormsg
        wx.PyValidator.__init__(self)

    def Clone(self):
        return NotEmptyValidator(self.errormsg)

    def Validate(self, win):
        textCtrl = self.GetWindow()
        if len(textCtrl.GetValue()) == 0:
            textCtrl.SetBackgroundColour("pink")
            textCtrl.SetFocus()
            textCtrl.Refresh()
            return False
        else:
            textCtrl.SetBackgroundColour(wx.SystemSettings_GetColour(wx.SYS_COLOUR_WINDOW))
            return True

    def TransferToWindow(self):
        return True

    def TransferFromWindow(self):
        return True

class AddNewR3Member(wx.Dialog):
    """ display nice and pretty dialog to enter realraum member information.
    """
    def __init__(self, parent, title, prefill=None):
        """ @param parent Parent window
            @param title dialogwindow title
        """
        super(AddNewR3Member, self).__init__(parent=parent, title=title)

        ## Init Sizers
        top_sizer = wx.FlexGridSizer(10,1,5,5)
        #top_sizer = wx.BoxSizer(wx.VERTICAL)

        membername_box = wx.StaticBox(self, label='Lastname Firstname')
        membername_sizer = wx.StaticBoxSizer(membername_box, wx.HORIZONTAL)

        membernick_box = wx.StaticBox(self, label='Nickname')
        membernick_sizer = wx.StaticBoxSizer(membernick_box, wx.HORIZONTAL)

        memberbirthdate_box = wx.StaticBox(self, label='Birthdayte YYYY-MM-DD')
        memberbirthdate_sizer = wx.StaticBoxSizer(memberbirthdate_box, orient=wx.HORIZONTAL)

        contacts_telnumbers_box = wx.StaticBox(self, label='Cellphonenumbers (separate with ;)')
        contacts_telnumbers_sizer = wx.StaticBoxSizer(contacts_telnumbers_box, orient=wx.HORIZONTAL)

        contacts_address_box = wx.StaticBox(self, label='Postal Address')
        contacts_address_sizer = wx.StaticBoxSizer(contacts_address_box, orient=wx.HORIZONTAL)

        contacts_xmpps_box = wx.StaticBox(self, label='xmpp (separate with ;)')
        contacts_xmpps_sizer = wx.StaticBoxSizer(contacts_xmpps_box, orient=wx.HORIZONTAL)

        contacts_emails_box = wx.StaticBox(self, label='e-mails (separate with ;)')
        contacts_emails_sizer = wx.StaticBoxSizer(contacts_emails_box, orient=wx.HORIZONTAL)

        junior_box = wx.StaticBox(self, label='Membership Type?')
        junior_sizer = wx.StaticBoxSizer(junior_box, orient=wx.HORIZONTAL)

        bottom_button_sizer = wx.StdDialogButtonSizer()

        ## Init and fill membername
        self.membername_txt = wx.TextCtrl(self, -1, prefill.name if prefill and prefil.name else "", validator = NotEmptyValidator("Name can't be empty"))
        membername_sizer.Add(self.membername_txt, 3, border=8, flag=wx.EXPAND | wx.ALL)

        ## Init and fill membernick
        self.membernick_txt = wx.TextCtrl(self, -1, prefill.nick if prefill and prefil.nick else "", validator = NotEmptyValidator("Nickname can't be empty"))
        membernick_sizer.Add(self.membernick_txt, 3, border=8, flag=wx.EXPAND | wx.LEFT | wx.TOP | wx.BOTTOM)

        ## Init and fill memberbirthdate
        self.memberbirthdate_txt = wx.TextCtrl(self, -1, "", validator = DateValidator("Date must be YYYY-MM-DD", emptyok=True))
        memberbirthdate_sizer.Add(self.memberbirthdate_txt, 3, border=8, flag=wx.EXPAND | wx.LEFT | wx.TOP | wx.BOTTOM)

        ## Init and fill contacts_telnumbers
        self.contacts_telnumbers_txt = wx.TextCtrl(self, -1, "")
        contacts_telnumbers_sizer.Add(self.contacts_telnumbers_txt, 3, border=8, flag=wx.EXPAND | wx.LEFT | wx.TOP | wx.BOTTOM)

        ## Init and fill contacts_address
        self.contacts_address_txt = wx.TextCtrl(self, -1, "")
        contacts_address_sizer.Add(self.contacts_address_txt, 3, border=8, flag=wx.EXPAND | wx.LEFT | wx.TOP | wx.BOTTOM)

        ## Init and fill contacts_xmpps
        self.contacts_xmpps_txt = wx.TextCtrl(self, -1, "")
        contacts_xmpps_sizer.Add(self.contacts_xmpps_txt, 3, border=8, flag=wx.EXPAND | wx.LEFT | wx.TOP | wx.BOTTOM)

        ## Init and fill contacts_emails
        self.contacts_emails_txt = wx.TextCtrl(self, -1, "")
        contacts_emails_sizer.Add(self.contacts_emails_txt, 3, border=8, flag=wx.EXPAND | wx.LEFT | wx.TOP | wx.BOTTOM)

        ## Init and fill membershiptype
        self.junior_choice = wx.Choice(self, choices=["Normal Member (25.00)","Junior Member (15.00)", "Sponsoring Member (30.00)"], style=0)
        junior_sizer.Add(self.junior_choice, 1, border=8, flag=wx.ALL|wx.ALIGN_RIGHT)


        ## Init and fill bottom buttons
        okButton = wx.Button(self, wx.ID_OK)
        okButton.SetDefault()
        closeButton = wx.Button(self, wx.ID_CANCEL)
        bottom_button_sizer.AddButton(okButton)
        bottom_button_sizer.AddButton(closeButton)
        bottom_button_sizer.Realize()

        ## Fill Top Sizer
        top_sizer.Add(junior_sizer, border=8, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.EXPAND)
        top_sizer.Add(membername_sizer, border=8, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.EXPAND)
        top_sizer.Add(membernick_sizer, border=8, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.EXPAND)
        top_sizer.Add(memberbirthdate_sizer, border=8, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.EXPAND)
        top_sizer.Add(contacts_telnumbers_sizer, border=8, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.EXPAND)
        top_sizer.Add(contacts_address_sizer, border=8, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.EXPAND)
        top_sizer.Add(contacts_xmpps_sizer, border=8, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.EXPAND)
        top_sizer.Add(contacts_emails_sizer, border=8, flag=wx.LEFT | wx.TOP | wx.RIGHT | wx.EXPAND)
        top_sizer.Add(bottom_button_sizer, border=8, flag=wx.ALIGN_CENTER | wx.ALL)

        ## Fill Dialog
        self.SetSizer(top_sizer)
        self.Layout()
        top_sizer.Fit(self)

        ## Bind Events
        # self.history_choice.Bind(wx.EVT_CHOICE, self.OnSelectHistoryEntry)
        # self.membernick_txt.SendTextUpdatedEvent()

    def getMemberInfo(self):
        """ intented to be called after dialog returns but before it is destroyed
            @return dialog data in format R3Member class
        """
        member = R3Member(self.membername_txt.GetValue(),self.membernick_txt.GetValue())
        try:
            membertypetext = self.junior_choice.GetItems()[self.junior_choice.GetSelection()]
            member.membershipfee = float(membertypetext[-6:-1])
        except:
            pass
        if self.memberbirthdate_txt.GetValidator().date:
            member.birthdate=self.memberbirthdate_txt.GetValidator().date
        map(member.addtel, self.contacts_telnumbers_txt.GetValue().split(";"))
        member.contact_address = [self.contacts_address_txt.GetValue()] if self.contacts_address_txt.GetValue() else []
        map(member.addxmpp,self.contacts_xmpps_txt.GetValue().split(";"))
        map(member.addemail,self.contacts_emails_txt.GetValue().split(";"))
        return member



def showDialogNewMember():
    """ show the NewMember dialog
        @retval None the dialog was aborted
        @retval R3Member
    """
    dial = AddNewR3Member(None, "New realraum Member")
    try:
        if dial.ShowModal() == wx.ID_OK:
            return dial.getMemberInfo()
        else:
            return None
    finally:
        dial.Destroy()


############# Unit Tests ###############

if __name__ == '__main__':
    print(showDialogNewMember())
