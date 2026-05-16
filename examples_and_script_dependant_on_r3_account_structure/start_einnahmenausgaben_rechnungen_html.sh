#!/usr/bin/zsh


local defaultquery="date:from$(date +%Y-%m-%d -d "2 year ago")"
local query=${*:-$defaultquery}

local outfilename=einnahmenausgaben.html
local port=8333

local D=$(mktemp -d); 
trap "rm -Rf $D" EXIT
python ${0:h}/einnahmenausgabenrechnung_csvhtml.py --html $query not:acct:revenue:membership-fees >| $D/$outfilename
ln -s ${0:h}/../Rechnungen(:A) $D/; 

(sleep 1; open "http://localhost:$port/$outfilename" &>/dev/null)&

cd $D
echo "Exit with Ctrl-C"
echo ""
python -m http.server $port

