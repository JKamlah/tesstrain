#!/usr/bin/env python3

import argparse
import io
from collections import Counter
from collections import defaultdict
from pathlib import Path
from functools import reduce
from pprint import pprint
import unicodedata
from PIL import Image

# Command line arguments.
arg_parser = argparse.ArgumentParser(description='Analyze the ground truth texts for the given text files.')
arg_parser.add_argument("filename", type =lambda x: Path(x), help="filename of text file or path to files", nargs='*')
arg_parser.add_argument("-n", "--dry-run", help="show which files would be normalized but don't change them", action="store_true")
arg_parser.add_argument("-v", "--verbose", help="show ignored files", action="store_true")
arg_parser.add_argument("-f", "--form", help="normalization form (default: NFC)", choices=["NFC", "NFKC", "NFD", "NFKD"], default="NFC")
arg_parser.add_argument("-c", "--categorize", help="Customized unicodedata categories", type=str, default=["Fraktur"], nargs='*')


args = arg_parser.parse_args()


def get_defaultdict(infodictstage, newstage, instance=dict):
    infodictstage[newstage] = defaultdict(instance) if not infodictstage.get(newstage, None) else infodictstage[newstage]


def load_catdata():
    import re
    catdata = defaultdict(dict)
    cat,subcat = None, None
    with open(Path("./unicode.categories"),"r") as fin:
        for line in fin.readlines():
            line = line.strip()
            if len(line) < 1 or line[0] == "#": continue
            if line[0]+line[-1] == "[]":
                cat = line.strip("[]")
                get_defaultdict(catdata,cat, instance=list)
                continue
            if cat:
                if "=" in line:
                    subcat, line = re.sub('\s', '', line).split('=')
                    #catdata[cat][subcat] = []
                if subcat and isinstance(catdata[cat][subcat],list):
                    for values in line.split(','):
                        if '-' in values and len(values.split('-')) == 2:
                            catdata[cat][subcat].append(range(*sorted([int(val) if not "0x" in val else int(val,16) for val in values.split("-")])))
                        elif '-' not in values:
                            if values.isdigit():
                                catdata[cat][subcat].append(int(values))
                            elif values[:2] == "0x":
                                catdata[cat][subcat].append(int(values,16))
                            elif len(values) > 1:
                                catdata[cat][subcat].append(values)
                            else:
                                catdata[cat][subcat].append(ord(values))
        if cat and subcat:
            return catdata


def categorize(infodict:defaultdict,category="unicode"):
    if category == "unicode":
        for key, val in infodict["overall"]["character"].items():
            uname = unicodedata.name(key)
            ucat = unicodedata.category(key)
            usubcat = uname.split(' ')[0]
            get_defaultdict(infodict["overall"], ucat[0])
            get_defaultdict(infodict["overall"][ucat[0]], usubcat)
            get_defaultdict(infodict["overall"][ucat[0]][usubcat], ucat[1])
            infodict["overall"][ucat[0]][usubcat][ucat[1]].update({key: val})
    else:
        catdata = load_catdata()
        if catdata and category in catdata.keys():
            for key, val in infodict['overall']['character'].items():
                for subcat, subdata in catdata[category].items():
                    for subdat in subdata:
                        if ord(key) == subdat or subdat in unicodedata.name(key).replace(" ",""):
                            get_defaultdict(infodict,category)
                            get_defaultdict(infodict[category],subcat)
                            infodict[category][subcat][key] = val
    return

# Set filenames or Path
if len(args.filename) == 1 and not args.filename[0].is_file():
    args.filename = Path(args.filename[0]).rglob("*.txt")

infodict = defaultdict(dict)

# Read all files.
for filename in args.filename:
    with io.open(filename, "r", encoding="utf-8") as f:
        try:
            text = unicodedata.normalize('NFC', f.read().strip())
            infodict["single"][filename.name] = Counter(text)
        except UnicodeDecodeError:
            if args.verbose:
                print(filename.name + " (ignored)")
            continue

get_defaultdict(infodict, "overall")
infodict["overall"]["character"] = reduce(lambda x, y: x+y, infodict["single"].values())
categorize(infodict,category="unicode")
for category in args.categorize:
    categorize(infodict,category = category)
pprint(infodict["overall"],indent=4)
pprint(infodict["Fraktur"])