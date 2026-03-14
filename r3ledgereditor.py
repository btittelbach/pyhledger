#!/usr/bin/env python3
"""
Accounting Web Application
A NiceGUI-based webapp for viewing and editing hledger transactions.
"""

import asyncio
import os, sys
import io
from pathlib import Path
from nicegui import ui, app, Client
from ledger import parseJournal, Transaction, queryHledgerForAccountList, Amount
from collections import defaultdict
from datetime import datetime, date, timedelta
from typing import Set, List, Optional
import shlex
import re
import subprocess

# --- Configuration ---
os.chdir(Path(__file__).parent) ## needed for os.system("git add") later

if len(sys.argv) < 2:
    LEDGER_FILE_ = Path(__file__).parent.joinpath("../Ledgers/r3.ledger").resolve()  # Change this to your ledger file path
else:
    LEDGER_FILE_ = Path(sys.argv[1]).resolve()

if len(sys.argv) < 3:
    INVOICE_PATH_ = Path(__file__).parent.joinpath("../Rechnungen/").resolve()  # Change this to your ledger file path
else:
    INVOICE_PATH_ = Path(sys.argv[2]).resolve()

INVOICE_SAVE_PATH_ = INVOICE_PATH_.joinpath("bezahlt/")
DEFAULT_ACCOUT_ = "assets:current:checking-r3"

CONFIGPY_PATH_ = Path(__file__).parent.joinpath("config.py").resolve()
LEDGER_CHECKING_DIR_ = LEDGER_FILE_.parent.joinpath("checking-r3")
ELBA_IMPORT_DIR_ = Path(__file__).parent.joinpath("../Umsätze/elba/neu")
ELBA_PREVIOUSLY_IMPORTED_CSVS_DIR_ = Path(__file__).parent.joinpath("../Umsätze/elba/imported/")

SAVE_INVOICE_IN_TAGS_ = False  ## else invoice is saved in code
INVOICE_TAG_NAME_ = "invoice"
invoice_code_todo_placeholder_strings_ = ["TODO","todo","missing","Missing","MISSING"]


# --- Global State ---
class AppState:
    def __init__(self):
        self.journal: list[Transaction] = []
        self.accounts: list[str] = []
        self.selected_account: str = ""
        self.filter_before_date: str = (date.today() - timedelta(weeks=52*1)).isoformat()
        self.selected_transaction: Transaction | None = None
        self.original_transaction_text: str = ""
        self.filtered_transactions: list[dict] = []
        self.table = None
        self.invoice_display = None
        self.transaction_textarea = None
        self.editor_selection = None

state_ = AppState()



class LocalFilePickerAndUploadDialog:
    def __init__(self, directory: Path, upload_directory: Optional[Path] = None, autoselect_regex = None):
        self.directory = directory
        self.upload_directory = upload_directory or directory
        self.dialog: Optional[ui.dialog] = None
        self.table: Optional[ui.table] = None
        self.result: Optional[List[Path]] = None
        self.autoselect_regex: Optional[re.Pattern] = autoselect_regex

    def get_all_files(self) -> List[dict]:
        """Get all files from the directory."""
        if not self.directory.exists():
            return []

        files = []
        for f in self.directory.glob("**/*.*"):
            if f.is_file():
                files.append({
                    "name": f.name,
                    "size": f"{f.stat().st_size / 1024:.1f} KB",
                    "mtime": f.stat().st_mtime_ns,
                    "path": str(f)
                })
        return files

    def preselect_using_regex(self):
        """Preselect files matching the autoselect regex."""
        if self.autoselect_regex is None or self.table is None or not isinstance(self.autoselect_regex, re.Pattern):
            return

        for row in self.table.rows:
            if self.autoselect_regex.search(row["name"]):
                self.table.selected.append(row)

    def on_ok_click(self):
        """Handle OK button click."""
        self.result = list([ Path(r["path"]) for r in self.table.selected ])
        self.dialog.close()

    def on_cancel_click(self):
        """Handle Cancel button click."""
        self.result = None
        self.dialog.close()

    async def handle_upload(self, e):
        filepath = Path(e.file.name)
        savepath = self.upload_directory.joinpath(filepath.name)
        await e.file.save(savepath)

        self.table.rows.append({
            "name": savepath.name,
            "size": f"{savepath.stat().st_size / 1024:.1f} KB",
            "mtime": savepath.stat().st_mtime_ns,
            "path": str(savepath)
        })

        self.table.selected.append(self.table.rows[-1])
        self.table.update()


    async def open(self) -> Optional[List[Path]]:
        """Open the file picker dialog and return selected paths."""
        columns = [
            {"name": "name", "label": "Filename", "field": "name", "sortable": True, "align": "left"},
            {"name": "size", "label": "Size", "field": "size", "sortable": True, "align": "right"},
            {"name": "mtime", "label": "Date", "field": "mtime", "sortable": True, "align": "right"},
        ]

        with ui.dialog() as self.dialog, ui.card().classes("w-1/3 max-w-full p-4"):
            ui.label("Select Files").classes("text-xl font-bold mb-2")
            ui.label(f"Directory: {self.directory}").classes("text-sm text-gray-500 mb-4")

            self.table = ui.table(
                columns=columns,
                rows=self.get_all_files(),
                selection="multiple",
                row_key="path",
                pagination={"rowsPerPage": 12, "sortBy": "mtime", "descending": True},
            ).classes("w-full")

            self.preselect_using_regex()

            ui.input(
                label="Filter",
                placeholder="Type to filter files...",
            ).bind_value(self.table, 'filter').classes("w-full mt-4")

            ui.label("Or Upload New File:").classes("text-sm font-semibold mt-4 mb-2")
            ui.upload(on_upload=self.handle_upload, auto_upload=True).classes('w-full')

            with ui.row().classes("w-full justify-end mt-4 gap-2"):
                ui.button("Cancel", on_click=self.on_cancel_click).props("flat")
                ui.button("OK", on_click=self.on_ok_click).props("color=primary")

        await self.dialog
        return self.result



def load_ledger():
    """Load and parse the ledger file."""
    if LEDGER_FILE_.is_file():
        with open(LEDGER_FILE_, 'r') as f:
            state_.journal = parseJournal(f)
        for txn in state_.journal:
            txn.unelideJokerPostings() #  fill in elided posting Amounts
        state_.accounts = queryHledgerForAccountList(LEDGER_FILE_)
    else:
        state_.journal = []
        state_.accounts = []


async def reload_ledger():
    load_ledger()
    state_.selected_transaction = []
    state_.original_transaction_text = ""
    await refilter_table()


def find_invoice_files_from_tags(tx: Transaction) -> list[Path]:
    """
        Search for invoice-files give in transaction tags `invoice` or `invoicesubstr`
        @returns [Path | str] list of found file paths or not-found codes
    """
    if not isinstance(tx, Transaction):
        return []

    filepaths_list:List[Path] = []
    for iv in tx.getTagList(INVOICE_TAG_NAME_):
        filepaths_list += INVOICE_PATH_.glob("**/"+iv.strip())

    ## make relative
    filepaths_list = [fpath.relative_to(INVOICE_PATH_) for fpath in filepaths_list]

    return filepaths_list


def find_matching_invoice_files(tx: Transaction) -> list[Path]:
    """
        Search for invoice-files matching the invoice code in the Transaction and return list of FilePaths
        invoice file names are either stored in the transaction "code", separated by `,`
        or in tag `invoice` where the tag in repeated for each file and the filename is unabbreviated
        @returns [Path | str] list of found file paths or not-found codes
    """
    if not isinstance(tx, Transaction):
        return []
    if hasattr(tx,"invoice_files") and not tx.invoice_files is None:
        return tx.invoice_files ## singleton

    notfiles_code_list = []
    filepaths_list:List[Path] = []
    code = tx.code
    if code is None or len(code)<1:
        return []

    ## append found files with exact name to list
    filepaths_list += INVOICE_PATH_.glob("**/"+code.strip())

    ## nothing found? maybe extensions was left out? try searching with .???
    if len(filepaths_list) == 0 and "." not in code[-5:]:
        filepaths_list += INVOICE_PATH_.glob("**/"+code.strip()+os.path.extsep+"*")
    ## still no match? maybe it's multiple files, separated by ','
    if len(filepaths_list) == 0 and "," in code:
        for scode in code.split(","):
            sflist = list(INVOICE_PATH_.glob("**/"+scode.strip()))
            filepaths_list += sflist
            if len(sflist) == 0 and "." not in scode[-5:]:
                ## maybe extensions was left out? try searching with .???
                sflist = list(INVOICE_PATH_.glob("**/"+scode.strip()+os.path.extsep+"*"))
                filepaths_list += sflist
            if len(sflist) == 0:
                notfiles_code_list += [scode]
    else:
        ## maybe the code is a code that is part of several files?
        ## e.g. Transaction: 2019/07/18  (Amazon429) Duct Tape Einkauf
        ## would match files "Rechnung_1_(Amazon429).pdf" and "2019-07-18_Amazon_ZweiteRechnung_(Amazon429).pdf"
        if len(filepaths_list) == 0 and len(code) >= 4:
            flist = list(INVOICE_PATH_.glob("**/*[( -)]"+code.strip()+"[) -]*"))
            if len(flist) <= 10:  ## only add if matches that are not too generic
                filepaths_list += flist
        ## finally try wider match for single file
        if len(filepaths_list) == 0:
            filepaths_list += INVOICE_PATH_.glob("**/*"+code.strip()+"*")
        ## still no file found? then it's a code that is not a filename
        if len(filepaths_list) == 0:
            notfiles_code_list = [code]

    ## make relative
    filepaths_list = [fpath.relative_to(INVOICE_PATH_) for fpath in filepaths_list]

    filepaths_list += find_invoice_files_from_tags(tx)

    return filepaths_list #+ notfiles_code_list


async def filter_transactions_by_account_and_date(account: str, start_isodate: str="") -> list[dict]:
    """Filter transactions and compute register with running sum."""
    register = []
    # running_sum = defaultdict(float)

    if start_isodate is None:
        start_isodate = ""

    for idx, txn in enumerate(state_.journal):
        if txn.isEmpty():
            continue

        if txn.getDate().isoformat() < start_isodate:
            continue

        center_postings = txn.findPostingWithAccount(account)

        if not center_postings:
            continue

        txn.invoice_files = find_matching_invoice_files(txn)

        # for center_posting in center_postings:
        #     if center_posting.amount and hasattr(center_posting.amount, 'quantity'):
        #         ## if center_posting has not elided amount, add to running sum
        #         if center_posting.amount.currency and len(center_posting.amount.currency) > 0:
        #             running_sum[center_posting.amount.currency] += center_posting.amount.quantity
        #     else:
        #         ## otherwise we need to calculate it
        #         unitamounts = defaultdict(list)
        #         for p in txn.postings:
        #             if p.amount.totalprice is None:
        #                 ## add normal price
        #                 unitamounts[p.amount.currency].append(p.amount)
        #             else:
        #                 ## is a conversion, so we add the totalprice
        #                 unitamounts[p.amount.totalprice.currency].append(Amount(p.amount.sgn() * p.amount.totalprice.quantity, p.amount.totalprice.currency))
        #         for currency, alist in unitamounts.items():
        #             if currency and len(currency) > 0:
        #                 cur_sum = round(sum([a.quantity for a in alist]),4)
        #                 if cur_sum != 0:
        #                     running_sum[currency] += -1*cur_sum

        for posting in txn.postings:
            if posting.account != account:
                register.append({
                    'id': idx,
                    'isodate': txn.date.isoformat(),
                    'description': txn.name,
                    'account': posting.account,
                    'amount': str(posting.amount),
                    'code': txn.code if txn.code else "",
                    # 'running_sum': "; ".join([f"{amt:.2f} {c}" for c,amt in running_sum.items()]),
                    'transaction_idx': idx,
                })
    return register


def parse_transaction_from_string(text: str) -> Transaction | None:
    """Parse a transaction string back into a Transaction object."""
    try:
        reader = io.StringIO(text)
        transactions = parseJournal(reader)
        if transactions and len(transactions) > 0:
            transactions[0].unelideJokerPostings()
            return transactions[0]
    except Exception as e:
        ui.notify(f"Error parsing transaction: {e}", type='negative')
    return None

class CSVImportWizard:
    def __init__(self):
        self.dialog = None
        self.steps_funs = [
            self.select_csvfiles_enter_assertionbalance_step,
            self.process_files_step,
            self.handle_veryoldtxs_step,
            self.handle_unknowns_step,
            self.finalize_import_step
        ]
        self.current_step = 0
        self.selected_files = []
        self.converted_txns = []
        self.unknown_txns = []
        self.config_mtime = self.get_config_mtime()
        self.assertionbalance = ""
        self.filter_for_new_txs = True
        self.result_earliest_import_date = None

    async def open(self, startnotification=None):
        with ui.dialog().props('persistent') as self.dialog, ui.card().classes('w-2/3 max-w-7xl p-6'):
            with ui.column().classes('w-full gap-4'):
                self.step_indicator = ui.stepper().props('navigation infinite').classes('w-full')
                with self.step_indicator:
                    for i, _ in enumerate(self.steps_funs):
                        ui.step(f'Step {i+1}')

                self.content_area = ui.column().classes('w-full mt-4')
                self.navigation = ui.row().classes('w-full justify-end mt-4')
                await self.render_current_step()
            if startnotification:
                startnotification.dismiss()
            await self.dialog

    async def next_step(self):
        if self.current_step < len(self.steps_funs) - 1:
            self.current_step += 1
            await self.render_current_step()

    async def previous_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            await self.render_current_step()

    async def finish(self):
        if not self.dialog:
            return
        self.dialog.close()
        if self.filter_for_new_txs:
            # Adjust filter to show newly imported transactions
            if self.converted_txns:
                self.result_earliest_import_date = min(txn.getDate() for txn in self.converted_txns)
                                # state_.filter_before_date = earliest_import_date.date().isoformat() if hasattr(earliest_import_date, 'date') else earliest_import_date.isoformat()
                if hasattr(self.result_earliest_import_date, 'date'):
                    self.result_earliest_import_date = self.result_earliest_import_date.date()
        ui.notify('Import process finished', type='positive')

    async def cancel(self):
        if not self.dialog:
            return
        self.dialog.close()

    async def render_current_step(self):
        self.step_indicator.set_value(f'Step {self.current_step+1}')

        self.content_area.clear()
        with self.content_area:
            await self.steps_funs[self.current_step]()

        self.navigation.clear()
        with self.navigation:
            if self.current_step < len(self.steps_funs) -1:
                if self.current_step > 0:
                    ui.button('Back', on_click=self.previous_step)

                if self.current_step < len(self.steps_funs) -2:
                    ui.button('Cancel', on_click=self.cancel, color='primary')
                    ui.button('Next', on_click=self.next_step, color='primary')
                else:
                    ui.button('Execute Import', on_click=self.next_step, color='primary')
            else:
                ui.button('OK', on_click=self.finish, color='positive')

    async def select_csvfiles_enter_assertionbalance_step(self):
        """Step 1: Select CSV files to import and give latest balance of ELBA account """

        ui.label('Select CSV Statements').classes('text-xl font-bold mb-2')
        ui.label(f'Select files from: {ELBA_IMPORT_DIR_}').classes('text-sm text-gray-500 mb-4')

        self.file_list = ui.list().classes('w-full border rounded p-2 max-h-60 overflow-auto')

        async def refresh_file_list():
            self.file_list.clear()
            with self.file_list:
                if len(self.selected_files)>0:
                    for f in self.selected_files:
                        ui.item(f.name)
                else:
                    ui.item("No files selected")
            self.file_list.update()

        async def update_selection():
            picker = LocalFilePickerAndUploadDialog(
                directory=ELBA_IMPORT_DIR_,
                upload_directory=ELBA_IMPORT_DIR_,
                autoselect_regex=re.compile(r".*\.csv$", re.IGNORECASE)
            )
            self.selected_files = await picker.open()
            if self.selected_files is None:
                self.selected_files = []
            assert(isinstance(self.selected_files, list))
            await refresh_file_list()

        await refresh_file_list()

        ui.button('Choose Files', on_click=update_selection, color='primary')

        ui.separator().classes('my-4')

        def validate_assert_amount_input(value):
            parts = value.strip().split()
            if len(parts) != 2:
                return 'Format must be: <amount> <currency>, e.g. 1234.56 EUR'
            if len(parts[1]) < 2:
                return 'Currency code seems too short'
            try:
                float(parts[0])
                return None
            except ValueError:
                return 'Amount must be a valid number'

        def change_assert_amount_input(e):
            self.assertionbalance = e.value

        ui.label('Enter latest Balance of Account:').classes('text-xl font-bold mb-2')
        ui.label('must match balance at time of csv-export').classes('text-sm text-gray-500 mb-4')
        ui.input(label='Latest Account Balance', value=self.assertionbalance, placeholder='e.g. 1234.56 EUR', validation=validate_assert_amount_input, on_change=change_assert_amount_input).classes('w-full font-mono')


    async def process_files_step(self):
        """Step 2: Convert CSV files to ledger format"""
        if not self.selected_files:
            ui.notify('No files selected', type='warning')
            return

        cpvalid, cperr = self.validate_config_py()
        if not cpvalid:
            ui.notify(f'Syntax error in config.py: {cperr}', type='negative')
            return

        # Show processing status
        num_skipped_already_imported = -1
        with ui.column().classes('w-full items-center p-4') as columnscreen:
            ui.spinner(size='lg').classes('mb-4')
            ui.label('Converting CSV files...').classes('text-lg')

            # Run conversion in background task
            try:
                self.converted_txns, num_skipped_already_imported = await self.run_conversion()

                # Check for unknown transactions
                self.unknown_txns = [
                    t for t in self.converted_txns
                    if any('---UNKNOWN---' in p.account for p in t.postings)
                ]

                # Check for very old transactions
                previously_newest_date = max([t.getDate() for t in state_.journal if not t.fileposition is None and t.fileposition.filepath.parent.samefile(LEDGER_CHECKING_DIR_)], default=date(2025,1,2)) - timedelta(days=1)
                self.suspiciously_old_txns = [
                    t for t in self.converted_txns
                    if t.getDate() < previously_newest_date
                ]

            except Exception as e:
                ui.notify(f'Conversion failed: {str(e)}', type='negative')
                await self.previous_step()
                return

            columnscreen.clear() # remove spinner when done

        # Show results summary
        with ui.column().classes('w-full gap-2'):
            ui.label(f'Skipped {num_skipped_already_imported} already seen transactions').classes('text-lg font-bold')
            ui.label(f'Parsed {len(self.converted_txns)} new transactions').classes('text-lg font-bold')
            if self.suspiciously_old_txns:
                ui.label(f'{len(self.suspiciously_old_txns)} transactions are older than expected').classes('text-red-500')
            else:
                ui.label('All transactions are as fresh as expected').classes('text-green-500')
            if self.unknown_txns:
                ui.label(f'{len(self.unknown_txns)} transactions need categorization in config.py').classes('text-red-500')
            else:
                ui.label('All transactions categorized with config.py rules').classes('text-green-500')

    async def handle_veryoldtxs_step(self):
        """Step 3: Handle transactions with unknown categories"""

        if not self.suspiciously_old_txns:
            ui.label('No suspicously old transactions found. Proceeding ...').classes('text-green-500 text-lg p-4')
            return

        ui.label(f'❕ {len(self.suspiciously_old_txns)} Transactions found which are older than already present ones').classes('text-xl font-bold mb-2')
        ui.label('🤔 This is suspicous and could be an error, please check!').classes('mb-4')

        # Show unknown transactions table
        columns = [
            {'name': 'date', 'label': 'Date', 'field': 'date', 'align': 'left'},
            {'name': 'comment', 'label': 'Booking-line', 'field': 'comment', 'align': 'left'},
            {'name': 'amt', 'label': 'Amount', 'field': 'amt', 'align': 'right'},
        ]

        rows = [
            {
                'date': txn.date.isoformat(),
                'amt': str(next(p.amount for p in txn.postings if p.amount)),
                'comment': '\n'.join(txn.comments),
            } for txn in self.suspiciously_old_txns
        ]

        ui.table(columns=columns, rows=rows, row_key='date').classes('w-full')

        # Config update instructions
        with ui.column().classes('w-full bg-yellow-50 p-4 mt-4 rounded'):
            ui.label('Caution Recommended').classes('font-bold text-lg text-yellow-800')
            ui.label('❕ Check if you are importing the correct files.').classes('mb-2')
            ui.label('❕ Check if these statements were really missing from last imports.').classes('mb-2')

        ui.button('Refresh', on_click=self.refresh_conversion, color='warning').classes('mt-4')

    async def handle_unknowns_step(self):
        """Step 3: Handle transactions with unknown categories"""
        if not self.unknown_txns:
            ui.label('No transactions need categorization. Proceeding ...').classes('text-green-500 text-lg p-4')
            return

        ui.label('Transactions May Need Categorization').classes('text-xl font-bold mb-2')
        ui.label('❕ The following transactions could not be automatically categorized.').classes('mb-4')
        ui.label('❕ If they are a common occurance, a rule should be written for them.').classes('mb-4')

        # Show unknown transactions table
        columns = [
            {'name': 'date', 'label': 'Date', 'field': 'date', 'align': 'left'},
            {'name': 'comment', 'label': 'Booking-line', 'field': 'comment', 'align': 'left'},
            {'name': 'amt', 'label': 'Amount', 'field': 'amt', 'align': 'right'},
        ]

        rows = [
            {
                'date': txn.date.isoformat(),
                'amt': str(next(p.amount for p in txn.postings if p.amount)),
                'comment': '\n'.join(txn.comments),
            } for txn in self.unknown_txns
        ]

        ui.table(columns=columns, rows=rows, row_key='date').classes('w-full')

        # Config update instructions
        with ui.column().classes('w-full bg-yellow-50 p-4 mt-4 rounded'):
            ui.label('Action Required').classes('font-bold text-lg text-yellow-800')
            ui.label('Edit config.py to add matching rules for these transactions:').classes('mb-2')
            ui.button('Open config.py',
                    on_click=lambda: open_file_in_editor(CONFIGPY_PATH_)).classes('mt-4')
            ui.label('After saving changes, click "Refresh" to retry categorization').classes('mt-2')

        ui.button('Refresh', on_click=self.refresh_conversion, color='warning').classes('mt-4')


    async def finalize_import_step(self):
        """Step 4: Finalize the import process"""

        from convert_elba_records import (
            getCSVExportDateFromFilename
        )

        exportdate = sorted([ getCSVExportDateFromFilename(fp) for fp in self.selected_files ])[-1]

        new_ledger_name = f"{exportdate.strftime('%Y-%m-%d')}-checking-r3.ledger"
        result_ledger = LEDGER_CHECKING_DIR_ / new_ledger_name

        with ui.column().classes('w-full gap-4'):
            ui.label('Actions done').classes('text-xl font-bold')

            with ui.card().classes('w-full p-4'):

                # Commit csv source files
                csv_file_list_for_shell = " ".join([shlex.quote(str(fp)) for fp in self.selected_files])
                os.system(f'git add {csv_file_list_for_shell}')
                os.system(f'git commit -m "pre-import, autocommit" {csv_file_list_for_shell}')
                ui.label(f'✅ git autocommit source CSV files').classes('mb-1')

                # Create directory if needed
                if not LEDGER_CHECKING_DIR_.exists():
                    LEDGER_CHECKING_DIR_.mkdir(parents=True)

                # Write new leder file
                with open(result_ledger,"w") as f:
                    f.truncate(0)
                    for txn in self.converted_txns:
                        f.write(str(txn))
                        f.write('\n\n')
                ui.label(f'✅ wrote new ledger file {new_ledger_name}').classes('mb-1')

                # Write "Import Statement" into main ledger
                with open(LEDGER_FILE_, 'a') as f:
                    f.write(f'\ninclude {LEDGER_CHECKING_DIR_.name}/{new_ledger_name}\n\n')
                ui.label(f'✅ included {new_ledger_name} into {LEDGER_FILE_.name}').classes('mb-1')

                # git add new ledger file
                os.system(f'git add "{result_ledger}" "{LEDGER_FILE_}"')
                ui.label(f'✅ git add {new_ledger_name} {LEDGER_FILE_.name}').classes('mb-1')

                # move imported CSVs to "imported" directory
                for filepath in self.selected_files:
                    destpath = ELBA_PREVIOUSLY_IMPORTED_CSVS_DIR_.joinpath(date.today().strftime("%Y-%m-%d_%H:%M_")+filepath.name)
                    # filepath.rename(destpath)
                    os.system(f'git mv {shlex.quote(str(filepath))} {shlex.quote(str(destpath))}')
                ui.label(f'✅ git mv source CSV to {ELBA_PREVIOUSLY_IMPORTED_CSVS_DIR_.name}/').classes('mb-1')



        # Show details
        with ui.column().classes('w-full gap-4'):
            ui.label('Import Summary').classes('text-xl font-bold')

            with ui.card().classes('w-full p-4'):
                ui.label(f'Total Transactions: {len(self.converted_txns)}').classes('mb-1')
                ui.label(f'Unknown Transactions: {len(self.unknown_txns)}').classes('mb-1')
                ui.label(f'Destination: {result_ledger}').classes('text-gray-600 text-sm')

        ## Check if ledger assertion holds
        with ui.column().classes('w-full gap-4'):
            ui.label('Running hledger balance-assertion checks').classes('text-xl font-bold')

            with ui.card().classes('w-full p-4'):
                retcode, stderroutput = await self.run_hledger_verify_assertions()
                if 0 == retcode:
                    ui.label(f'{LEDGER_FILE_.name} balances. All good!').classes('mb-1')
                else:
                    ui.label(f'❌ hledger check {LEDGER_FILE_.name} FAILED!').classes('text-red-500')
                    os.system(f'git commit -m "hledger check failed. file needs fixing" {result_ledger}')
                    ui.label(f'✅ made intermediary git autocommit of problematic file').classes('mb-1')
                    ui.textarea(value=stderroutput).props('readonly autogrow').classes('w-full h-auto mb-2 font-mono')
                    ui.label(f'❕ Please fix this manually').classes('text-red-500')


        # git commit and push reminder
        ui.label('Remember to "git commit" and "git push" after final edits!').classes('text-xl font-bold')

        # Final confirmation
        ui.checkbox('Adjust display-filter to show newly imported transactions', value=True,
                    on_change=lambda e: setattr(self, 'filter_for_new_txs', e.value))


    async def run_hledger_verify_assertions(self) -> tuple[int | None, str]:
        """ run hledger check """
        hlcheck_proc = await asyncio.create_subprocess_exec('hledger','-f',LEDGER_FILE_,"check", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (stdout_data, stderr_data) = await hlcheck_proc.communicate(input=None)
        return (hlcheck_proc.returncode, stderr_data.decode())


    def validate_config_py(self):
        """Validate config.py syntax."""
        try:
            with open(CONFIGPY_PATH_, 'r') as f:
                compile(f.read(), str(CONFIGPY_PATH_), 'exec')
            return True, ''
        except SyntaxError as e:
            return False, str(e)

    async def run_conversion(self):
        """Run the CSV conversion using logic from convert_elba_records.py"""
        from convert_elba_records import (
            generateDatabaseOfAlreadyImportedTransactionIDs,
            makeLedgerTransactionFromCSVFile,
            addAssertToAndSortTransactions,
            parseAssertAmt,
            runFunctionOnCSV,
            max_history_age_to_filter_duplicates_from_days_,
            getCSVExportDateFromFilename
        )

        assert_amount = parseAssertAmt(self.assertionbalance)
        if assert_amount is None:
            raise ValueError('Invalid assertion balance format')

        # Get previously imported transactions
        now = datetime.now()
        already_imported_csvfiles = (fp for fp in
            ELBA_PREVIOUSLY_IMPORTED_CSVS_DIR_.glob("**/*.csv", case_sensitive=False)
            if now - getCSVExportDateFromFilename(fp) < timedelta(days=max_history_age_to_filter_duplicates_from_days_)
            )
        already_imported_txids = generateDatabaseOfAlreadyImportedTransactionIDs(already_imported_csvfiles)


        # Process each selected file
        newly_imported_txns = []
        num_skipped_already_imported = 0
        for filepath_to_import in self.selected_files:
            newly_tx, num_skipped = runFunctionOnCSV(lambda csvfile: makeLedgerTransactionFromCSVFile(already_imported_txids, csvfile), filepath_to_import)
            newly_imported_txns += newly_tx
            num_skipped_already_imported += num_skipped
            # add just imported txids to already imported set to avoid duplicates within multiple new files
            # the reason we do this here, after the file has been fully processed and not within the makeLedgerTransactionFromCSVFile function
            # is, that if we did it within that function, we would skip duplicates within the same file, which is not desired
            # as duplicates within the same file, can only happen if the bank exports it like this, meaning our duplicate checking method is
            # more likely to be incorrect than the duplicates being an error
            already_imported_txids.update(generateDatabaseOfAlreadyImportedTransactionIDs([filepath_to_import]))

        return addAssertToAndSortTransactions(newly_imported_txns, assert_amount), num_skipped_already_imported

    async def refresh_conversion(self):
        """Re-run conversion after config.py changes"""
        self.config_mtime = self.get_config_mtime()
        await self.process_files_step()
        await self.render_current_step()

    def get_config_mtime(self):
        return CONFIGPY_PATH_.stat().st_mtime if CONFIGPY_PATH_.exists() else 0

async def open_import_wizard():
    """Launch the CSV import wizard dialog"""
    startnotification = ui.notification(timeout=10000, message='Starting Import Wizard...', spinner=True)
    startnotification.update()
    await asyncio.sleep(0.4)
    import_wizard = CSVImportWizard()
    await import_wizard.open(startnotification)
    if not import_wizard.result_earliest_import_date is None:
        state_.ui_date_filter.value = import_wizard.result_earliest_import_date.isoformat()
        select_account(DEFAULT_ACCOUT_)
    await reload_ledger()

# --- UI Components ---
async def create_ui():
    editor_selection = None

    # Main vertical splitter: left (70%) | right (30%)
    with ui.splitter(value=70).classes('w-full h-screen') as main_splitter:

        # === LEFT PANEL: Account selector and transaction table ===
        with main_splitter.before:
            # === Split Left Panel into Upper Left and Lower Left
            with ui.splitter(value=90, horizontal=True).classes('w-full h-full r-expand-after35') as left_splitter:
                with left_splitter.before:

                    # === UPPER LEFT: Transaction List ===
                    with ui.row().classes('w-full p-4'):
                        # Account select dropdown
                        state_.ui_account_select = ui.select(
                            options=state_.accounts,
                            label='Select Account',
                            on_change=lambda e: on_account_change(e.value)
                        ).classes('w-1/3 mb-4')

                        # Date filter input
                        state_.ui_date_filter = ui.date_input(
                            label='Only Show Transactions After',
                            value=state_.filter_before_date,
                            on_change=lambda e: on_date_change(e.value)
                        ).classes('w-1/6 ml-4 mb-4')

                        # Reload Ledger Button
                        ui.button('Reload Ledger', on_click=reload_ledger).classes('ml-4 mb-4')

                        ui.button('Import CSV Statements',on_click=open_import_wizard, color='primary').classes('ml-4 mb-4')

                    with ui.column().classes('w-full h-full p-4'):

                        # Transaction table
                        columns = [
                            {'name': 'actions', 'label': 'Actions', 'field': 'actions', 'sortable': False, 'align': 'center'},
                            {'name': 'isodate', 'label': 'Date', 'field': 'isodate', 'sortable': True, 'align': 'left'},
                            {'name': 'description', 'label': 'Description', 'field': 'description', 'sortable': True, 'align': 'left'},
                            {'name': 'account', 'label': 'Account', 'field': 'account', 'sortable': True, 'align': 'left'},
                            {'name': 'amount', 'label': 'Amount', 'field': 'amount', 'sortable': True, 'align': 'right'},
                            {'name': 'code', 'label': 'Code (Reciept/Invoice)', 'field': 'code', 'sortable': True, 'align': 'left'},
                            # {'name': 'running_sum', 'label': 'Balance', 'field': 'running_sum', 'sortable': False, 'align': 'right'},
                        ]

                        state_.table = ui.table(
                            columns=columns,
                            rows=[],
                            row_key='id',
                            selection='single',
                            on_select=lambda e: on_row_select(e),
                            # pagination={"rowsPerPage": 50, "sortBy": "isodate", "descending": True},
                        ).classes('w-full flex-grow')

                        # Add slot to jump to corresponding account
                        with state_.table.add_slot('body-cell-account'):
                            with state_.table.cell("account"):
                                ui.button().style('text-transform: none; font-weight: normal; font-style: normal; background: none; border: none; color: inherit; padding: 0;').props(':label=props.value flat').on('click',js_handler='() => emit(props.value)',handler=lambda e: select_account(e.args))
                        # state_.table.add_slot('body-cell-account', '''
                        #     <q-td :props="props">
                        #         <span style="font-family:monospace">{{ props.row.account }}</span>
                        #         <q-btn flat dense icon="➠" color="primary" @click="$parent.$emit('goto_account', props.row)" title="GotoAccount"/>
                        #     </q-td>
                        # ''')

                        # Add slot for transaction actions
                        state_.table.add_slot('body-cell-actions', '''
                            <q-td :props="props">
                                <q-btn flat dense icon="📝" color="primary" @click="$parent.$emit('open_editor', props.row)" title="Open in Editor"/>
                            </q-td>
                        ''')
                        state_.table.on('open_editor', lambda e: open_txn_in_editor_and_wait_until_editor_closes(state_.journal[e.args["transaction_idx"]]))

                # === LOWER LEFT: Transaction editor ===
                with left_splitter.after:
                    with ui.column().classes('w-full h-full p-4 bg-stone-50'):

                        # Textarea with transaction text
                        state_.transaction_textarea = ui.textarea(
                            label='Transaction',
                            placeholder='Select a transaction from the table...'
                        ).classes('w-full flex-grow font-mono text-sm').props('autogrow')


                        # Autocomplete and Buttons
                        with ui.row().classes('w-full mt-4'):
                            # Autocomplete input for account names (helper)
                            account_autocomplete = ui.input(
                                placeholder='Add account name...',
                                autocomplete=state_.accounts
                            ).classes('w-3/5 mb-2 font-mono')
                            account_autocomplete.on('change', lambda e: insert_account_to_textarea(e.args))
                            ui.space()
                            ui.button('Revert Text', on_click=revert_transaction_text).props('outline')
                            ui.button('Save Transaction', on_click=save_transaction).props('color=primary')
                            ui.button('Open in', on_click=lambda: open_txn_in_editor_and_wait_until_editor_closes(state_.selected_transaction)).props('color=primary')
                            state_.editor_selection = ui.select(
                                options=['nvim-qt', 'code', 'subl'],
                                label='Editor',
                                value='subl'
                            ).classes('w-32 ml-2')

        # === RIGHT PANEL: Invoice/PDF display ===
        with main_splitter.after:
            with ui.scroll_area().classes('w-full h-full p-2'):
                ui.label('Invoice Preview').classes('text-lg font-bold mb-2')
                state_.invoice_display = ui.column().classes('w-full')

    # await asyncio.sleep(0.1)
    if (state_.selected_account is None or 0 == len(state_.selected_account)) and DEFAULT_ACCOUT_ in state_.accounts:
        await asyncio.sleep(0.7)
        state_.ui_account_select.value = DEFAULT_ACCOUT_


async def refilter_table():
    """ReFilter Table."""
    n = ui.notification(timeout=5000, message="Loading Transactions ...", spinner=True)
    n.update()
    await asyncio.sleep(0.2)
    # Update Account Listing
    state_.filtered_transactions = await filter_transactions_by_account_and_date(state_.selected_account, state_.filter_before_date)
    state_.table.rows = list(reversed(state_.filtered_transactions))
    state_.table.update()

    # Update Notification Msg
    n.message = 'Done!'
    n.spinner = False
    await asyncio.sleep(0.1)

    # Clear displays if selected transaction no longer in filter
    clear_all = True
    if state_.table.selected and state_.selected_transaction:
        if any(state_.journal[r['transaction_idx']] == state_.selected_transaction for r in state_.table.selected):
            clear_all = False
    if clear_all:
        state_.invoice_display.clear()
        state_.transaction_textarea.value = ''
        state_.selected_transaction = None

    n.dismiss()

async def select_account(account: Optional[str]):
    if state_:
        state_.ui_account_select.value = account if account else DEFAULT_ACCOUT_

async def on_account_change(account: str):
    """Handle account selection change."""
    # Update Account Listing
    if account:
        state_.selected_account = account
        await refilter_table()

async def on_date_change(isodate: str):
    """Handle account selection change."""
    # Update Account Listing
    if isodate:
        state_.filter_before_date = isodate
        await refilter_table()

async def update_transactiontext_display(txn: Optional[Transaction]):
    """Update the transaction text area with the selected transaction."""
    if isinstance(txn, Transaction):
        state_.original_transaction_text = str(txn)
        state_.transaction_textarea.value = state_.original_transaction_text
    else:
        state_.transaction_textarea.value = ''
        state_.original_transaction_text = ''

async def on_row_select(event):
    """Handle row selection in the transaction table."""
    if event.selection:
        row = event.selection[0]
        txn_idx = row['transaction_idx']
        state_.selected_transaction = state_.journal[txn_idx]

        # Update textarea display
        await update_transactiontext_display(state_.selected_transaction)

        # Update invoice display
        await update_invoice_display(state_.selected_transaction)
    else:
        state_.selected_transaction = None
        await update_transactiontext_display(None)
        state_.invoice_display.clear()


async def update_invoice_display(transaction: Transaction):
    """Update the invoice preview panel with files from the transaction."""
    state_.invoice_display.clear()

    invoice_files = find_matching_invoice_files(transaction)

    with state_.invoice_display:
        ui.button('Add Invoice', icon="add", on_click=lambda : on_add_invoice(transaction)).props('outline')

        if not invoice_files:
            ui.label('No invoice files attached').classes('text-gray-500 italic')
        else:
            for filepath in [f for f in invoice_files if isinstance(f, Path)]:
                ext = filepath.suffix.lower()
                with ui.row().classes('w-full'):
                    ui.label(f'📄 {Path(filepath).name}').classes('font-semibold mt-2')
                    ui.space()
                    ui.button('Remove This Invoice', icon="delete", on_click=lambda e: on_remove_invoice(filepath, transaction)).props('outline')

                if ext == '.pdf':
                    # Embed PDF using iframe
                    ui.html(f'''
                        <iframe src="/rechnungen/{filepath}" style="width: 100%; height: 333mm; border: 1px solid #ccc;">
                        </iframe>
                    ''', sanitize=False).classes('w-full')
                elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                    # ui.image(INVOICE_PATH_.joinpath(filepath)).classes('w-full border rounded')
                    ui.html(f'''
                        <img src="/rechnungen/{filepath}" style="width: 100%; height: 500mm; border: 1px solid #ccc;" />
                    ''', sanitize=False).classes('w-full')
                elif ext in ['.txt', '.md']:
                    ui.textarea(value=INVOICE_PATH_.joinpath(filepath).read_text()).classes('w-full border rounded')
                else:
                    ui.label(f'❌ Unsupported file type: {ext}').classes('text-orange-500')

async def on_add_invoice(txn: Transaction):
    """Handle adding an invoice file to a transaction."""
    lfpdialog = LocalFilePickerAndUploadDialog(directory=INVOICE_PATH_, upload_directory=INVOICE_SAVE_PATH_)
    selected_filepaths = await lfpdialog.open()
    if selected_filepaths:
        new_rel_paths, new_names = list(zip(*[(fp.relative_to(INVOICE_PATH_),fp.name) for fp in selected_filepaths]))
        txn.invoice_files += new_rel_paths
        ## remove placeholder strings from code
        if txn.code in invoice_code_todo_placeholder_strings_:
            txn.setCode("")
        ## write invoice into txn
        if SAVE_INVOICE_IN_TAGS_ or not txn.getTag(INVOICE_TAG_NAME_) is None:
            for n in new_names:
                txn.addTag(INVOICE_TAG_NAME_,n)
        else:
            codes = (set(txn.code.split(",")) if txn.code else set()).union(new_names)
            txn.setCode(",".join(codes))
        ## write update to file
        linuenumber_changes = txn.writeUpdateIntoSourceFile()
        assert(linuenumber_changes == 0) ## should be no need to update startline/endline of all other transactions, as changing transaction-code does not change linecount
        os.system(f'git add {" ".join(shlex.quote(str(fp)) for fp in selected_filepaths)}')
        ui.notify(f'Added {len(selected_filepaths)} invoices', type='positive')

        await update_transactiontext_display(txn)
        await refilter_table()
        await asyncio.sleep(0.2)
        await update_invoice_display(txn)
        await asyncio.sleep(0.2)


async def on_remove_invoice(filepath: Path, txn: Transaction):
    """Handle removing an invoice file from a transaction."""

    ui.notify(f'Removing invoice {filepath.name}', type='info')
    # Remove invoice from code
    code = txn.code or ''
    codes = [ c for c in [c.strip() for c in code.split(',')] if c != filepath.name]
    txn.setCode(','.join(codes) if codes else None)
    txn.rmTag(INVOICE_TAG_NAME_,filepath.name) # rm from tags as well

    if filepath in txn.invoice_files:
        del txn.invoice_files[txn.invoice_files.index(filepath)]

    # save updated journal to file
    linecount_diff = txn.writeUpdateIntoSourceFile()
    assert(0 == linecount_diff) ## should be no need to update startline/endline of all other transactions, as changing transaction-code does not change linecount

    # Update Display
    await update_transactiontext_display(txn)
    await refilter_table()
    await asyncio.sleep(1)
    await update_invoice_display(txn)
    await asyncio.sleep(1)

async def insert_account_to_textarea(account: str):
    """Insert selected account name into textarea."""
    if account and state_.transaction_textarea.value:
        state_.transaction_textarea.value += f"\n    {account}  "
    elif account:
        state_.transaction_textarea.value = f"    {account}  "


async def revert_transaction_text():
    """Revert textarea to original transaction text."""
    state_.transaction_textarea.value = state_.original_transaction_text
    ui.notify('Transaction text reverted', type='info')


async def save_transaction():
    """Save the edited transaction back to the journal."""

    orig_txn = state_.selected_transaction

    if not orig_txn:
        ui.notify('No transaction selected', type='warning')
        return

    new_text = state_.transaction_textarea.value.strip()
    if not new_text:
        ui.notify('Transaction text is empty', type='warning')
        return

    # Parse the edited text back into a Transaction object
    new_txn = parse_transaction_from_string(new_text)

    # Check parser result
    if not new_txn or new_txn.isEmpty():
        ui.notify('Failed to parse transaction. Check syntax.', type='negative')
        return

    # Sanity Check the new transaction
    if not new_txn.isBalanced() or not new_txn.willStringifySanely():
        ui.notify("Transaction Not Balanced! Can't save!", type='negative')
        return

    # Find and replace the transaction in the journal
    txn_idx = state_.journal.index(orig_txn)
    str_new_tx = str(new_txn)

    if not (orig_txn.fileposition and orig_txn.fileposition.filepath):
        ui.notify('Transactions were not loaded from file. Cannot edit!', type='negative')
        return

    # Save to file
    try:
        linecount_diff = orig_txn.fileposition.replaceWithStr(str_new_tx) # this auto-adjusts the tx fileposition
    except Exception as e:
        ui.notify('Error saving file: '+str(e), type='negative')
        return

    new_txn.fileposition = orig_txn.fileposition  # preserve file position info
    new_txn.fileposition.endline += linecount_diff  # update file position info
    state_.journal[txn_idx] = new_txn
    orig_txn = new_txn
    state_.original_transaction_text = str_new_tx

    # Update linenumbers of all other transactions
    for idx in range(txn_idx+1, len(state_.journal)):
        txn = state_.journal[idx]
        if state_.journal[idx].fileposition and state_.journal[idx].fileposition.startline > (orig_txn.fileposition.endline-linecount_diff) and txn.fileposition.filepath == orig_txn.fileposition.filepath:
            state_.journal[idx].fileposition.startline += linecount_diff
            state_.journal[idx].fileposition.endline += linecount_diff

    # Refresh table
    ui.notify('Transaction saved successfully', type='positive')
    await refilter_table()
    # state_.filtered_transactions = await filter_transactions_by_account_and_date(state_.selected_account, state_.filter_before_date)
    # table.rows = state_.filtered_transactions
    # table.update()


async def open_txn_in_editor_and_wait_until_editor_closes(txn):
    """Open the ledger file in the selected editor."""
    editor_commands = {
        'nvim-qt': ['nvim-qt', '--nofork'] + [f'+{txn.fileposition.startline+1}', str(txn.fileposition.filepath)] if txn else [str(LEDGER_FILE_)] + ['--','-p'],
        'code': ['code','-n','-w','-a',LEDGER_FILE_.parent] + ['--goto', f"{txn.fileposition.filepath}:{txn.fileposition.startline+1}", txn.fileposition.filepath] if txn else [str(LEDGER_FILE_)],
        'subl': ['subl','--launch-or-new-window','--wait','--add',LEDGER_FILE_.parent, f"{txn.fileposition.filepath}:{txn.fileposition.startline+1}" if txn else str(LEDGER_FILE_)],
    }
    cmd = []
    if state_.editor_selection.value in editor_commands:
        cmd += editor_commands[state_.editor_selection.value]
    else:
        cmd += [state_.editor_selection.value]
    n = ui.notification(timeout=None, message="Opening in Editor", spinner=True)
    await asyncio.sleep(0.2)
    try:
        n.message = 'Waiting on Editor'
        await asyncio.sleep(0.2)
        editor_process = await asyncio.create_subprocess_exec(*cmd, stdout=None, stderr=None)
        await editor_process.wait()
        n.message = 'Reloading Ledger Files'
        await reload_ledger()
        n.message = 'Done'
        n.spinner = False
    except Exception as e:
        ui.notify(f'Error opening file: {e}', type='negative')
    finally:
        n.dismiss()

async def open_file_in_editor(filepath: Path):
    """Open an arbitrary file in the selected editor and run in background."""
    editor_commands = {
        'nvim-qt': ['nvim-qt'] + [str(filepath)] + ['--','-p'],
        'code': ['code','-n',str(filepath)],
        'subl': ['subl','--launch-or-new-window',str(filepath)],
    }
    cmd = []
    if state_.editor_selection.value in editor_commands:
        cmd += editor_commands[state_.editor_selection.value]
    else:
        cmd += [state_.editor_selection.value]
    editor_process = await asyncio.create_subprocess_exec(*cmd, stdout=None, stderr=None)
    await editor_process.wait()

# --- Main Entry Point ---
@ui.page('/')
async def main_page(client: Client):
    ui.dark_mode().disable()
    ui.add_css('''
        .r-expand-after35 .q-splitter__panel:last-child:hover {
            flex: 3 !important;
        }

        .r-expand-after35:has(.q-splitter__panel:last-child:hover) .q-splitter__panel:first-child {
            flex: 5 !important;
        }

        .r-expand-after13 .q-splitter__panel:last-child:hover {
            flex: 1 !important;
        }

        .r-expand-after13:has(.q-splitter__panel:last-child:hover) .q-splitter__panel:first-child {
            flex: 3 !important;
        }
    ''')
    await create_ui()

    await client.disconnected()
    app.shutdown()


if __name__ in {"__main__", "__mp_main__"}:
    load_ledger()
    print(f"Loaded {len(state_.journal)} transactions from {LEDGER_FILE_}")
    app.add_static_files('/rechnungen', INVOICE_PATH_)
    ui.run(
        title='r3 hledger Editor / Viewer',
        host='127.0.0.1',
        port=8081,
        on_air=None,
        reload=False,
        native=False,
        reconnect_timeout=8
)
