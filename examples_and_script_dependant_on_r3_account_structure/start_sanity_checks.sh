#!/bin/zsh

local r3ledger=(hledger -f "${0:A:h}"/../Ledgers/r3.ledger)

section() {
  echo ""
  echo "============================================================"
  echo -e "$1"
  echo "============================================================"
}

local primary_account="$(cd ${0:h}; python3 -c "from config import *;print(elba_primary_account_)")"
local unknownexp="$( $r3ledger print expenses:---UNKNOWN--- date:from2024 )"
local unknownrev="$( $r3ledger print revenue:---UNKNOWN--- date:from2024 )"
local unnamedt="$( $r3ledger print desc:'(pay stuff|^$|receive money)' date:from2023 )"
local tags=($(grep 'addTag(' "${0:A:h}"/config.py | sed 's/.*addTag("\([^)]*\)",\s*"\([^)]*\)").*/\1=\2/;s/.*addTag("\([^)]*\)").*/\1/;/addTag([^,)]*,[^")]*)/d' | sort | uniq ))
local einzahlungen="$($r3ledger print acct:$primary_account not:tag:cash note:"einzahlung|bar" date:from2020)"
local noinvoice="$($r3ledger print expr:"acct:$primary_account and acct:expenses" code:'(^$|todo|fixme|missing)' date:from2024-05-01 not:desc:'(receive membership-fee|pay insurance|pay rent|pay utilities|pay bank fees|Kaufmiete Lasercutter|Bar Auszahlung|Bankomatzahlung Kassa)')"
# local allinvoices=( ${(f)"$($r3ledger print acct:$primary_account code:'^.+$' date:from2023 -O json | jq -r '.[].tcode' | sed 's/, */\n/g' | sort | uniq)"} )
local allinvoices=( ${(f)"$($r3ledger codes acct:$primary_account date:from2023 | sed 's/, */\n/g' | sort | uniq)"} )

if [[ -n $unknownexp ]]; then
	section "Transations in expenses:---UNKNOWN--- found!\nPlease fix them!\nPlease update config.py so this does not happen again."
	print $unknownexp
fi
if [[ -n $unknownrev ]]; then
	section "Transations in revenue:---UNKNOWN--- found!\nPlease fix them!\nPlease update config.py so this does not happen again."
	print $unknownrev
fi
if [[ -n $unnamedt ]]; then
	section "Transations without proper description found!\nPlease fix them!\nPlease update config.py so this does not happen again."
	print $unnamedt
fi

for tag in $tags; do
  #echo $tag
  local substr=$tag
  if [[ $tag =~ ".*=(\S*)" ]]; then
    substr=$match[1]
  fi
  local untagged="$( $r3ledger print acct:$primary_account not:tag:$tag note:$substr date:from2020 )"
  if [[ -n $untagged ]]; then
	section "Entries not tagged with tag '$tag' but maybe they should be, as they match the string '$substr':"
	echo "$untagged"
	exit 1
  fi
done
if [[ -n $einzahlungen  ]]; then
	section "These transactions should be tagged 'cash'!\nPlease fix them!\nPlease update config.py so this does not happen again."
	print $einzahlungen
fi
if [[ -n $noinvoice  ]]; then
	section "These transactions are missing an invoice!\nPlease fix them!"
	print $noinvoice
fi


local missing_invoices=()
local -A groupinvoices
## go through all ledger 'code's
for invoice in "${allinvoices[@]}"; do
	## search a file with exactly that name in the bezahlt folders
	local invoicefile=( "${0:A:h}"/../Rechnungen/bezahlt*/"$invoice"(N:t) )
	## if not found, search for a file that contains the code as substring
	if [[ $#invoicefile -eq 0 ]]; then
		local invoicefile_substr=( "${0:A:h}"/../Rechnungen/bezahlt*/*"$invoice"*(N:t) )
		if [[ $#invoicefile_substr -eq 0 ]]; then
			missing_invoices+=($invoice)
		else
			groupinvoices[$invoice]="$invoicefile_substr"
		fi
	fi
done

if [[ ${#missing_invoices[@]} -gt 0 ]]; then
	section "These invoices are missing!"
	print -l $missing_invoices
fi

if [[ ${#groupinvoices} -gt 0 ]]; then
	print ${(k)groupinvoices}
	print ${groupinvoices}
	section "These invoices are matched by an invoice-group-tag substring. Please check if they match only exactly the files they should"
	for key in ${(k)groupinvoices}; do
		echo "InvoiceKey: $key"
		print -l ${groupinvoices[$key]}
		echo ""
	done
fi

### this takes forever .. don't do it
# local orphaned_invoice_files=()
# for rfile in "${0:A:h}"/../Rechnungen/bezahlt*/*(.); do
# 	if ! $r3ledger print acct:assets:current:checking-r3 code:"${rfile:t:r}" &> /dev/null; then
# 		orphaned_invoice_files+=("${rfile:t}")
# 		print "${rfile:t}"
# 	fi
# done

# if [[ -n $orphaned_invoice_files  ]]; then
# 	section "These files might not be associated with a transaction!"
# 	print -l $orphaned_invoice_files
# fi

exit 0
