#!/usr/bin/python

import asyncio

from datetime import datetime, date, timedelta
from typing import Optional, List
from tortoise import Tortoise, fields
from tortoise.models import Model
from tortoise.exceptions import IntegrityError
from nicegui import ui, app, Client
import calendar
import sys, os
import re
import subprocess
from pathlib import Path

default_fee_ = 30.0
fee_options_ = [15.0, 30.0, 35.0, 60.0]

def parseIsoDateString(datestr :str) -> date:
    datestr = datestr.strip()
    if len(datestr) < 0:
        raise ValueError("Empty String is not a date")
    ## replace any extra --- with single -
    datestr = re.compile(r"--+").sub("-",datestr)
    ## extract datestr from any leading or following garbage characters:
    m = re.compile(r"\d{2,4}-\d{2}-\d{2}").search(datestr)
    if m is None:
        raise ValueError("not a isodate str")
    datestr = m.group(0)
    try:
        return datetime.strptime(datestr, '%Y-%m-%d').date()
    except ValueError as e:
        if "day is out of range for month" in str(e):
            parts = datestr.split('-')
            year = int(parts[0])
            month = int(parts[1])
            # return date with last valid day of that month
            return datetime(year, month, calendar.monthrange(year, month)[1]).date()
        else:
            # otherwise re-raise
            raise e

def conditional_capitalize(s: str) -> str:
    """Capitalizes the string if it is not all uppercase."""
    if not s.isupper():
        return s.capitalize()
    return s

# Tortoise ORM Models
class ContactType(Model):
    ct_id = fields.IntField(pk=True)
    ct_type = fields.CharField(max_length=50)

    class Meta:
        table = "contacttype"

class Person(Model):
    p_id = fields.IntField(pk=True)
    p_name = fields.CharField(max_length=255)
    p_birthday = fields.DateField(null=True)
    p_note = fields.TextField(null=True)
    p_nick = fields.CharField(max_length=100, unique=True)

    class Meta:
        table = "persons"

class Contact(Model):
    c_id = fields.IntField(pk=True, allows_generated=True)
    p_id = fields.IntField()
    ct_id = fields.IntField()
    c_contact = fields.TextField()

    class Meta:
        table = "contact"

class Membership(Model):
    m_id = fields.IntField(pk=True, allows_generated=True)
    p_id = fields.IntField()
    # p = fields.ForeignKeyField(
    #     'Person',
    #     related_name='memberships',
    #     db_column='p_id',
    #     on_delete=fields.CASCADE
    # )
    m_firstmonth = fields.DateField()
    m_lastmonth = fields.DateField(null=True)
    m_fee = fields.FloatField()

    class Meta:
        table = "membership"
        unique_together = (("p_id", "m_firstmonth"),("p_id", "m_lastmonth")) # per Person there should not be overlapping periods

class CustomWireTransferRegex(Model):
    p_id = fields.IntField(pk=True, unique=True)
    # p = fields.ForeignKeyField(
    #     'app.Person',
    #     related_name='wiretransferregex',
    #     db_column='p_id',
    #     on_delete=fields.CASCADE  # delete this entry if related entry in Persons get's deleted
    # )
    w_searchregex = fields.TextField()

    class Meta:
        table = "wiretransferregex"

class RecuringTransactions(Model):
    hrt_id = fields.IntField(pk=True)
    hrt_firstmonth = fields.DateField()
    hrt_lastmonth = fields.DateField(null=True)
    hrt_description = fields.TextField()
    hp_id = fields.IntField()

    class Meta:
        table = "hledger_recurringtransactions"

class RecuringTransactionPostings(Model):
    hp_id = fields.IntField(pk=True)
    hp_account = fields.TextField()
    hp_amount = fields.FloatField()
    hp_currency = fields.TextField(default="EUR")

    class Meta:
        table = "hledger_postings"

# Initialize database
async def init_db():
    await Tortoise.init(
        db_url='sqlite://'+str(Path(__file__).parent.joinpath('../Ledgers/members.sqlite')),
        modules={'models': ['__main__']}
    )
    # Create tables if they don't exist
    await Tortoise.generate_schemas(safe=True)

    # Get database connection for raw SQL
    conn = Tortoise.get_connection('default')

    # Create the view and triggers using raw SQL
    view_and_triggers_sql = """
    CREATE VIEW IF NOT EXISTS "paying_members_list" AS 
    SELECT p_nick, p_name, p_birthday, p_note, m_firstmonth, m_lastmonth, m_fee, 
           replace(lower(trim(p_name))," ","_")||".jpg" as "p_fotofile", 
           c_contact, p_id, contact.rowid as "c_id" 
    FROM persons 
    LEFT JOIN "membership" USING (p_id) 
    LEFT JOIN "contact" USING (p_id) 
    WHERE m_firstmonth <= date('now') 
      AND (m_lastmonth IS NULL OR m_lastmonth IS "" OR m_lastmonth > date('now')) 
      AND (ct_id IS 2 OR ct_id IS NULL);
    CREATE VIEW IF NOT EXISTS "members_list" AS
    SELECT p_nick, p_name, p_birthday, p_note, m_firstmonth, 
        (select m_fee from membership where p_id=persons.p_id and m_lastmonth is NULL) as m_fee, 
        case when count(m_lastmonth)<count(*) then NULL else max(m_lastmonth) end as m_lastmonth, 
        w_searchregex, p_id
    FROM persons
    LEFT JOIN "membership" USING (p_id)
    LEFT JOIN "wiretransferregex" USING (p_id)
    GROUP BY p_id;

    """

    # Create triggers
    triggers_sql = """
    CREATE TRIGGER IF NOT EXISTS paymember_name_change
    INSTEAD OF UPDATE OF p_name ON "paying_members_list"
    BEGIN
      UPDATE persons SET p_name=NEW.p_name WHERE p_id=NEW.p_id;
    END;

    CREATE TRIGGER IF NOT EXISTS paymember_nick_change
    INSTEAD OF UPDATE OF p_nick ON "paying_members_list"
    BEGIN
      UPDATE persons SET p_nick=NEW.p_nick WHERE p_id=NEW.p_id;
    END;

    CREATE TRIGGER IF NOT EXISTS paymember_birthday_change
    INSTEAD OF UPDATE OF p_birthday ON "paying_members_list"
    BEGIN
      UPDATE persons SET p_birthday=NEW.p_birthday WHERE p_id=NEW.p_id;
    END;

    CREATE TRIGGER IF NOT EXISTS paymember_note_change
    INSTEAD OF UPDATE OF p_note ON "paying_members_list"
    BEGIN
      UPDATE persons SET p_note=NEW.p_note WHERE p_id=NEW.p_id;
    END;

    CREATE TRIGGER IF NOT EXISTS paymember_firstmonth_change
    INSTEAD OF UPDATE OF m_firstmonth ON "paying_members_list"
    BEGIN
      UPDATE membership SET m_firstmonth=NEW.m_firstmonth WHERE p_id=NEW.p_id;
    END;

    CREATE TRIGGER IF NOT EXISTS paymember_lastmonth_change
    INSTEAD OF UPDATE OF m_lastmonth ON "paying_members_list"
    BEGIN
      UPDATE membership SET m_lastmonth=NEW.m_lastmonth WHERE p_id=NEW.p_id;
    END;

    CREATE TRIGGER IF NOT EXISTS paymember_fee_change
    INSTEAD OF UPDATE OF m_fee ON "paying_members_list"
    BEGIN
      UPDATE membership SET m_fee=NEW.m_fee WHERE p_id=NEW.p_id;
    END;

    CREATE TRIGGER IF NOT EXISTS paymember_email_change
    INSTEAD OF UPDATE OF c_contact ON "paying_members_list"
    BEGIN
      INSERT INTO "contact"("rowid","p_id","ct_id","c_contact") VALUES (NEW.c_id,NEW.p_id,2,NEW.c_contact);
    END;
    """

    # Create unique index for persons table
    index_sql = """
    CREATE UNIQUE INDEX IF NOT EXISTS person_nick ON persons(p_nick);
    """

    # Execute the SQL scripts to create view, triggers, and indexes
    await conn.execute_script(view_and_triggers_sql)
    await conn.execute_script(triggers_sql)
    await conn.execute_script(index_sql)

    # Initialize contact types if empty
    contact_types = [
        (1, "handy"),
        (2, "email"),
        (3, "homeaddress"),
        (4, "xmpp"),
        (5, "matrix"),
        (6, "IBAN")
    ]
    contact_types_num_in_db = await ContactType.all().count()
    for ct_id, ct_type in contact_types:
        if ct_id > contact_types_num_in_db:
            await ContactType.create(ct_id=ct_id, ct_type=ct_type)

    ## Sanitize and clean up birthday entries
    await conn.execute_query(
        "UPDATE persons SET p_birthday = NULL WHERE p_birthday = '' OR p_birthday = ' '"
    )
    ## Sanitize and clean up membership dates
    await conn.execute_query(
        "UPDATE membership SET m_lastmonth = NULL WHERE m_lastmonth = '' OR m_lastmonth = ' '"
    )


# Close database connection
async def close_db():
    await Tortoise.close_connections()

# Global variable to store table reference
members_table = None
checkbox_mkmembershipfees_ = None

async def regenMembershipFeeLedger():
    if checkbox_mkmembershipfees_ and checkbox_mkmembershipfees_.value:
        # Here we would regenerate the membershipfee.ledger file
        # For now, just simulate with a notification
        n = ui.notification(timeout=25000, message="Regenerating membershipfee.ledger...", spinner=True)
        mkmf_proc = await asyncio.create_subprocess_exec(Path(__file__).parent.joinpath('mkmemberfees.sh'), stdout=None, stderr=None)
        await mkmf_proc.wait()
        n.message = 'Done!'
        n.spinner = False
        await asyncio.sleep(0.5)
        n.dismiss()

async def show_datepicker_dialog(title: str, description: str, initial_date: Optional[date]=None) -> Optional[date]:
    """
    Display a datepicker dialog and return the selected date.

    Args:
        title: The dialog title
        description: The dialog description text
        initial_date: The initial date to show in the datepicker

    Returns:
        The optional selected date if not cancelled
    """
    with ui.dialog() as dialog, ui.card():
        ui.label(title).classes('text-h6')
        ui.label(description)

        # Create the date picker
        date_picker = ui.date(value=initial_date.isoformat() if initial_date else date.today().isoformat())

        with ui.row():
            ui.button('Cancel', on_click=lambda: dialog.submit(None))
            ui.button('OK', on_click=lambda: dialog.submit(date.fromisoformat(date_picker.value)))

    result = await dialog
    return result

# Add Member Function
async def add_member():
    name = {'value': ''}
    nick = {'value': ''}
    fee = {'value': default_fee_}
    birthday = {'value': None}
    note = {'value': ''}
    contacts = {'values': {}}

    with ui.dialog() as dialog, ui.card():
        ui.label('Add New Member').classes('text-h6')

        ui.input('Name', placeholder='Last Name First Name').bind_value_to(name, 'value')
        ui.input('Nick', placeholder='Nickname').bind_value_to(nick, 'value')

        ui.select(
            label='Fee',
            options=fee_options_,
            value=default_fee_
        ).bind_value_to(fee, 'value')

        ui.date_input('Birthday (optional)', placeholder='YYYY-MM-DD').bind_value_to(birthday, 'value')
        ui.input('Notes', placeholder='').bind_value_to(note, 'value')

        ui.label('Contact Information (optional)\nseparate with ;').classes('text-subtitle2 mt-4')

        contact_types = await ContactType.all()
        for ct in contact_types:
            contacts['values'][ct.ct_id] = {'value': ''}
            ui.input(
                conditional_capitalize(ct.ct_type),
                placeholder=f'Enter {ct.ct_type}'
            ).bind_value_to(contacts['values'][ct.ct_id], 'value')

        with ui.row():
            async def save():
                try:
                    if not name['value'] or not nick['value']:
                        ui.notify('Name and Nick are required!', type='negative')
                        return


                    # Create person
                    person = await Person.create(
                        p_name=name['value'],
                        p_nick=nick['value'],
                        p_birthday=(None if len(birthday['value'].strip())<1 else birthday['value']),
                        p_note=note['value']
                    )

                    # Create membership
                    current_month = date.today().replace(day=1)
                    await Membership.create(
                        p_id=person.p_id,
                        m_firstmonth=current_month,
                        m_fee=fee['value']
                    )

                    # Create contacts if provided
                    for ct_id, contact_data in contacts['values'].items():
                        if contact_data['value']:
                            for contact_part in contact_data['value'].split(';'):
                                await Contact.create(
                                    p_id=person.p_id,
                                    ct_id=ct_id,
                                    c_contact=contact_part
                                )

                    ui.notify(f'Member {name["value"]} added successfully!', type='positive')
                    dialog.close()
                    await refresh_members_table()

                except IntegrityError:
                    ui.notify('Nick already exists!', type='negative')
                except Exception as e:
                    ui.notify(f'Error: {str(e)}', type='negative')

            ui.button('Save', on_click=save).props('color=primary')
            ui.button('Cancel', on_click=dialog.close)

    dialog.open()

# Member Details and Membership Management
async def show_member_details(person_id: int):
    person = await Person.filter(p_id=person_id).first()
    if not person:
        ui.notify('Person not found!', type='negative')
        return

    memberships = await Membership.filter(p_id=person_id).all().order_by('m_firstmonth')

    with ui.dialog() as dialog, ui.card().classes('w-full'):
        ui.label(f'Member Details: {person.p_name} ({person.p_nick})').classes('text-h6')

        # Membership periods table
        ui.label('Membership Periods').classes('text-subtitle1 mt-4')

        columns = [
            {'name': 'warning', 'label': '', 'field': 'warning', 'align': 'center'},
            {'name': 'start', 'label': 'Start Month', 'field': 'start', 'align': 'left'},
            {'name': 'end', 'label': 'End Month', 'field': 'end', 'align': 'left'},
            {'name': 'fee', 'label': 'Monthly Fee', 'field': 'fee', 'align': 'left'},
            {'name': 'actions', 'label': 'Actions', 'field': 'actions', 'align': 'center'}
        ]

        # Store memberships in a dictionary for easy lookup
        membership_dict = {}
        for m in memberships:
            membership_dict[m.m_id] = m  # Store the ORM object separately

        def build_rows_and_sanity_check_dates():
            rows = []

            previous_end_date = None
            lastmonth_null_count = 0
            for m in memberships:
                # print(m.m_id, m.m_firstmonth, m.m_lastmonth, previous_end_date)
                warning = ''

                # Sanity check start date
                if previous_end_date and m.m_firstmonth <= previous_end_date:
                    # ui.notify(f'Start date {m.m_firstmonth} overlaps with previous end date {previous_end_date}', type='negative')
                    print(f'Start date {m.m_firstmonth} overlaps with previous end date {previous_end_date}')
                    warning = '⚠️'
                if previous_end_date and m.m_firstmonth - previous_end_date > timedelta(days=15):
                    warning = '⟿'

                # Sanity check end date
                if not m.m_lastmonth is None:
                    if m.m_lastmonth < m.m_firstmonth:
                        # ui.notify(f'End date {m.m_lastmonth} is before start date {m.m_firstmonth}', type='negative')
                        print(f'End date {m.m_lastmonth} is before start date {m.m_firstmonth}')
                        warning ='❗'
                    previous_end_date = m.m_lastmonth
                else:
                    previous_end_date = None
                    lastmonth_null_count += 1
                    if (lastmonth_null_count > 1):
                        # ui.notify(f'Multiple Active periods detected!', type='negative')
                        print(f'Multiple Active periods detected!')
                        warning ='⚠️'

                rows.append({
                    'id': m.m_id,
                    'warning': warning,
                    'start': str(m.m_firstmonth),
                    'end': str(m.m_lastmonth) if m.m_lastmonth else 'Active',
                    'fee': m.m_fee,
                })
            return rows

        table = ui.table(columns=columns, rows=build_rows_and_sanity_check_dates(), row_key='id')

        # Make cells editable
        table.add_slot('body-cell-start', '''
            <q-td :props="props">
                <q-input v-model="props.row.start" dense borderless @change="$parent.$emit('update_start', props.row)" />
            </q-td>
        ''')

        table.add_slot('body-cell-end', '''
            <q-td :props="props">
                <q-input v-model="props.row.end" dense borderless @change="$parent.$emit('update_end', props.row)" />
            </q-td>
        ''')

        table.add_slot('body-cell-fee', '''
            <q-td :props="props">
                <q-input v-model.number="props.row.fee" type="number" dense borderless @change="$parent.$emit('update_fee', props.row)" />
            </q-td>
        ''')

        table.add_slot('body-cell-actions', '''
            <q-td :props="props">
                <q-btn size="sm" color="negative" round dense icon="delete" @click="$parent.$emit('delete', props.row)" />
            </q-td>
        ''')


        async def update_membership_field(e):
            row = e.args
            m = membership_dict.get(row['id'])  # Retrieve the ORM object from dictionary

            if not m:
                ui.notify('Membership not found', type='negative')
                return

            try:
                m.m_firstmonth = parseIsoDateString(row['start'])
                if row['end'] == 'Active':
                    m.m_lastmonth = None
                else:
                    try:
                        m.m_lastmonth = parseIsoDateString(row['end'])
                    except ValueError:
                        m.m_lastmonth = None
                m.m_fee = float(row['fee'])

                await m.save(update_fields=['m_firstmonth','m_lastmonth','m_fee'])
                ui.notify('Updated successfully', type='positive')
                table.update_rows(build_rows_and_sanity_check_dates())
            except Exception as ex:
                ui.notify(f'Error: {str(ex)}', type='negative')

        async def delete_membership(e):
            row = e.args
            row_id = row['id']
            m = membership_dict.get(row_id)  # Retrieve the ORM object from dictionary

            if m:
                memberships.remove(m)
                await m.delete()
                ui.notify('Membership period deleted', type='info')
                table.update_rows(build_rows_and_sanity_check_dates())
            else:
                ui.notify('Membership not found', type='negative')

        table.on('update_start', update_membership_field)
        table.on('update_end', update_membership_field)
        table.on('update_fee', update_membership_field)
        table.on('delete', delete_membership)

        async def start_membership_period(fee=default_fee_, start_date=None, end_date=None):
            if start_date is None:
                start_date = await show_datepicker_dialog("Start Membership Period", "Select month in which membership will start")
                if not start_date:
                    ui.notify('operation cancelled', type='info')
                    return
            current_month = start_date.replace(day=1)
            m = None
            if end_date is None:
                m = await Membership.create(
                    p_id=person.p_id,
                    m_firstmonth=current_month,
                    m_fee=fee
                )
            else:
                m = await Membership.create(
                    p_id=person.p_id,
                    m_firstmonth=current_month,
                    m_lastmonth=end_date,
                    m_fee=fee
                )

            memberships.append(m)
            membership_dict[m.m_id] = m  # Store the ORM object separately
            table.update_rows(build_rows_and_sanity_check_dates())

        # End membership button
        async def end_membership():
            active_membership = None
            for m in memberships:
                if not m.m_lastmonth:
                    active_membership = m
                    break

            if active_membership:

                last_member_month = await show_datepicker_dialog("End Membership", "Select month in which membership will end", active_membership.m_firstmonth+timedelta(days=31))
                if not last_member_month:
                    ui.notify('operation cancelled', type='info')
                    return

                last_member_month.replace(day=28)
                # last_member_month = date.today().replace(day=28)
                active_membership.m_lastmonth = last_member_month
                # for row in table.rows:
                #     if row['id'] == f'{active_membership.m_id}':
                #         row['end'] = str(last_member_month)
                #         break
                await active_membership.save(update_fields=['m_lastmonth'])
                ui.notify('Membership ended', type='info')
                table.update_rows(build_rows_and_sanity_check_dates())
            else:
                ui.notify('No active membership found', type='warning')

        # Change Fee Button
        async def change_membership_fee():
            active_membership = None
            for m in memberships:
                if not m.m_lastmonth:
                    active_membership = m
                    break

            if active_membership:
                membership_restart_date = await show_datepicker_dialog("Change Memberfee", "Select month in which new fee applies")
                if not membership_restart_date:
                    ui.notify('operation cancelled', type='info')
                    return

                membership_restart_date = membership_restart_date.replace(day=1)
                last_fee = active_membership.m_fee
                new_fee = default_fee_ if last_fee < default_fee_ else last_fee
                current_period_end_date = (membership_restart_date-timedelta(days=15)).replace(day=28)
                active_membership.m_lastmonth = current_period_end_date
                await active_membership.save(update_fields=['m_lastmonth'])
                await start_membership_period(fee=new_fee, start_date=membership_restart_date)
                ui.notify('New Membership-Fee Period started', type='info')
                table.update_rows(build_rows_and_sanity_check_dates())
            else:
                ui.notify('No active membership to change fee found', type='warning')

        # Pause Membership for 6 months Button
        async def pause_membership():
            active_membership = None
            for m in memberships:
                if not m.m_lastmonth:
                    active_membership = m
                    break

            if active_membership:
                membership_restart_date = await show_datepicker_dialog("Pause Membership", "Select month in which membership restarts", (date.today()+timedelta(days=31*4+30*3)).replace(day=1))
                if not membership_restart_date:
                    ui.notify('operation cancelled', type='info')
                    return

                membership_restart_date = membership_restart_date.replace(day=1)
                last_fee = active_membership.m_fee
                current_month = max(date.today().replace(day=28), (active_membership.m_firstmonth+timedelta(days=31)).replace(day=28))
                pause_start_date = (current_month+timedelta(days=15)).replace(day=1)
                pause_end_date = (membership_restart_date-timedelta(days=15)).replace(day=28)
                active_membership.m_lastmonth = current_month
                # for row in table.rows:
                #     if row['id'] == f'{active_membership.p_id}_{active_membership.m_firstmonth}':
                #         row['end'] = str(current_month)
                #         break
                await active_membership.save(update_fields=['m_lastmonth'])
                await start_membership_period(fee=0.0, start_date=pause_start_date, end_date=pause_end_date)
                await start_membership_period(fee=last_fee, start_date=membership_restart_date)
                ui.notify('Membership Pause created', type='info')
                table.update_rows(build_rows_and_sanity_check_dates())
            else:
                ui.notify('No active membership to pause found', type='warning')


        with ui.row():
            # ui.button('Sanity Check', on_click=sanity_check_dates_and_style_table)
            ui.button('End Active Membership on...', on_click=end_membership).props('color=warning')
            ui.button('Pause Membership until...', on_click=pause_membership)
            ui.button('(Re)Start Membership Period', on_click=start_membership_period)
            ui.button('Change Fee', on_click=change_membership_fee)
            ui.button('Close', on_click=dialog.close)

        dialog.on('hide', regenMembershipFeeLedger)

    dialog.open()

# Contact Management
async def manage_contacts(person_id: int):
    person = await Person.filter(p_id=person_id).first()
    if not person:
        ui.notify('Person not found!', type='negative')
        return

    with ui.dialog() as dialog, ui.card().classes('w-full'):
        ui.label(f'Manage Contacts: {person.p_name}').classes('text-h6')

        contacts = await Contact.filter(p_id=person_id).all()
        contact_types = await ContactType.all()
        ct_dict = {ct.ct_id: ct.ct_type for ct in contact_types}

        # Display existing contacts
        ui.label('Existing Contacts').classes('text-subtitle1 mt-4')

        for contact in contacts:
            with ui.row():
                ct_type = ct_dict.get(contact.ct_id, 'Unknown')

                contact_value = {'value': contact.c_contact}
                ui.label(f'{conditional_capitalize(ct_type)}:').classes('w-32')
                ui.input(value=contact.c_contact).bind_value_to(contact_value, 'value').classes('w-64')

                async def update_contact(c=contact, cv=contact_value):
                    c.c_contact = cv['value']
                    await c.save()
                    ui.notify('Contact updated', type='positive')

                async def delete_contact(c=contact):
                    await c.delete()
                    ui.notify('Contact deleted', type='info')
                    dialog.close()
                    await manage_contacts(person_id)

                ui.button('Update', on_click=update_contact).props('size=sm')
                ui.button('Delete', on_click=delete_contact).props('size=sm color=negative')

        # Add new contact
        ui.label('Add New Contact').classes('text-subtitle1 mt-4')

        new_ct_type = {'value': 1}
        new_contact = {'value': ''}

        with ui.row():
            ui.select(
                label='Type',
                options={ct.ct_id: conditional_capitalize(ct.ct_type) for ct in contact_types},
                value=1
            ).bind_value_to(new_ct_type, 'value')

            ui.input('Contact Value').bind_value_to(new_contact, 'value')

            async def add_contact():
                if new_contact['value']:
                    await Contact.create(
                        p_id=person_id,
                        ct_id=new_ct_type['value'],
                        c_contact=new_contact['value']
                    )
                    ui.notify('Contact added', type='positive')
                    dialog.close()
                    await manage_contacts(person_id)

            ui.button('Add', on_click=add_contact).props('color=primary')

        ui.button('Close', on_click=dialog.close).classes('mt-4')

    dialog.open()

# Paying Members List View
async def refresh_members_table():
    global members_table
    if not members_table:
        return

    try:
        # Execute raw SQL for the view
        conn = Tortoise.get_connection('default')
        query = """
            SELECT p_nick, p_name, p_birthday, p_note, m_firstmonth, m_lastmonth, 
                   m_fee, w_searchregex, p_id 
            FROM members_list ORDER by m_lastmonth IS NULL DESC, m_lastmonth DESC, p_nick ASC;
        """
        result = await conn.execute_query_dict(query)

        rows = []
        for r in result:
            rows.append({
                'p_id': r['p_id'],
                'p_nick': r['p_nick'] or '',
                'p_name': r['p_name'] or '',
                'p_birthday': str(r['p_birthday']) if r['p_birthday'] else '',
                'p_note': r['p_note'] or '',
                'm_firstmonth': str(r['m_firstmonth']) if r['m_firstmonth'] else '',
                'm_lastmonth': str(r['m_lastmonth']) if r['m_lastmonth'] else 'Active',
                'm_fee': r['m_fee'] or 0,
                'w_searchregex': r['w_searchregex'] or ''
            })

        members_table.update_rows(rows)
    except Exception as e:
        ui.notify(f'Error refreshing table: {str(e)}', type='negative')

# Main page
@ui.page('/')
async def main(client: Client):
    global members_table, checkbox_mkmembershipfees_

    # Initialize database when page loads
    await init_db()

    # GUI Layout
    ui.label('realraum Accounting - Member Management System').classes('text-h4')

    with ui.row().classes('w-full gap-4'):
        ui.button('Add New Member', on_click=add_member).props('color=primary')
        ui.button('Refresh', on_click=refresh_members_table)
        checkbox_mkmembershipfees_ = ui.checkbox('Auto-Make membershipfee.ledger', value=True)

    ui.label('realraum Members List').classes('text-h5 mt-6')

    columns = [
        {'name': 'p_nick', 'label': 'Nick', 'field': 'p_nick', 'align': 'left'},
        {'name': 'p_name', 'label': 'Name', 'field': 'p_name', 'align': 'left'},
        {'name': 'p_birthday', 'label': 'Birthday', 'field': 'p_birthday', 'align': 'left'},
        {'name': 'm_fee', 'label': 'Fee', 'field': 'm_fee', 'align': 'left'},
        {'name': 'm_lastmonth', 'label': 'Status', 'field': 'm_lastmonth', 'align': 'left'},
        {'name': 'w_searchregex', 'label': 'WireTransfer CustomRE', 'field': 'w_searchregex', 'align': 'left'},
        {'name': 'actions', 'label': 'Actions', 'field': 'actions', 'align': 'center'}
    ]

    members_table = ui.table(columns=columns, rows=[], row_key='p_id').classes('w-full')

    # Make cells editable
    members_table.add_slot('body-cell-p_nick', '''
    <q-td :props="props">
        <q-input v-model="props.row.p_nick" dense borderless @change="$parent.$emit('mt_update_nick', props.row)" />
    </q-td>
    ''')

    members_table.add_slot('body-cell-p_name', '''
    <q-td :props="props">
        <q-input v-model="props.row.p_name" dense borderless @change="$parent.$emit('mt_update_name', props.row)" />
    </q-td>
    ''')

    members_table.add_slot('body-cell-w_searchregex', '''
    <q-td :props="props">
        <q-input v-model="props.row.w_searchregex" dense borderless @change="$parent.$emit('mt_update_searchregex', props.row)" />
    </q-td>
    ''')

    members_table.add_slot('body-cell-actions', '''
        <q-td :props="props">
            <q-btn size="sm" color="primary" round dense icon="info" @click="$parent.$emit('details', props.row)" />
            <q-btn size="sm" color="secondary" round dense icon="contacts" @click="$parent.$emit('contacts', props.row)" class="q-ml-sm" />
        </q-td>
    ''')

    async def show_details(e):
        await show_member_details(e.args['p_id'])

    async def show_contacts(e):
        await manage_contacts(e.args['p_id'])

    async def update_member_name(e):
        row = e.args
        try:
            person = await Person.filter(p_id=row['p_id']).first()
            if person:
                oldname = person.p_name
                person.p_name = row['p_name'].strip()
                await person.save(update_fields=['p_name'])
                ui.notify('Member name updated', type='positive')
                ui.notify(f'Change of name in DB requires change of hledger accounts.\nPlease replace all occurances of assets:current:membership A/R:{oldname} with assets:current:membership A/R:{person.p_name}', type='ongoing', close_button='OK', multi_line=True)
            else:
                ui.notify('Person not found', type='negative')
        except Exception as ex:
            ui.notify(f'Error: {str(ex)}', type='negative')

    async def update_member_nick(e):
        row = e.args
        try:
            person = await Person.filter(p_id=row['p_id']).first()
            if person:
                person.p_nick = row['p_nick'].strip()
                await person.save(update_fields=['p_nick'])
                ui.notify('Member nick updated', type='positive')
            else:
                ui.notify('Person not found', type='negative')
        except Exception as ex:
            ui.notify(f'Error: {str(ex)}', type='negative')

    async def update_member_searchregex(e):
        row = e.args
        new_custom_regex = row['w_searchregex'].strip()
        if len(new_custom_regex)>0:
            try:
                re.compile(new_custom_regex)
            except re.error:
                ui.notify('Regular Expression does not compile', type='negative')
                return
        try:
            regex_entry = await CustomWireTransferRegex.filter(p_id=row['p_id']).first()
            if regex_entry:
                if len(new_custom_regex) < 1:
                    await regex_entry.delete()
                    ui.notify('WireTransfer CustomRegEx deleted', type='info')
                    return
                else:
                    regex_entry.w_searchregex = new_custom_regex
                    await regex_entry.save(update_fields=['w_searchregex'])
            else:
                await CustomWireTransferRegex.create(
                    p_id=row['p_id'],
                    w_searchregex=new_custom_regex
                )
            ui.notify('WireTransfer CustomRegEx updated', type='positive')
        except Exception as ex:
            ui.notify(f'Error: {str(ex)}', type='negative')

    members_table.on('mt_update_nick', update_member_nick)
    members_table.on('mt_update_name', update_member_name)
    members_table.on('mt_update_searchregex', update_member_searchregex)
    members_table.on('details', show_details)
    members_table.on('contacts', show_contacts)

    # Initial load
    await refresh_members_table()
    await client.disconnected()
    # Close database when client disconnects
    await close_db()
    app.shutdown()

# Run the application with proper lifecycle handling
ui.run(
    title='realraum Member Database',
    host='127.0.0.1',
    port=8080,
    on_air=False,
    reload=False,
    native=False
)
