#!/bin/zsh
${EDITOR:-vim -p} $(rg --field-match-separator=' +' --line-number --vimgrep --stop-on-nonmatch -M 1 "$*" ${0:h}/../Ledgers | cut -d+ -f 1-2 )
