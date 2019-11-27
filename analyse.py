#!/usr/bin/env python3

import argparse
import io
from collections import Counter
from collections import defaultdict
from pathlib import Path
from functools import reduce
from pprint import pprint
import unicodedata
import re
from PIL import Image

# Command line arguments.
arg_parser = argparse.ArgumentParser(description='Analyze the ground truth texts for the given text files.')
arg_parser.add_argument("filename", type =lambda x: Path(x), help="filename of text file or path to files", nargs='*')
arg_parser.add_argument("-n", "--dry-run", help="show which files would be normalized but don't change them", action="store_true")
arg_parser.add_argument("-v", "--verbose", help="show ignored files", action="store_true")
arg_parser.add_argument("-f", "--form", help="normalization form (default: NFC)", choices=["NFC", "NFKC", "NFD", "NFKD"], default="NFC")
arg_parser.add_argument("-c", "--categorize", help="Customized unicodedata categories", type=str, default=["Fraktur"], nargs='*')
arg_parser.add_argument("-g", "--guidelines", help="Evaluated the dataset against some guidelines", type=str, default="OCRD-1", choices=["OCRD-1","OCRD-2","OCRD-3"])


args = arg_parser.parse_args()


def get_defaultdict(infodictstage, newstage, instance=dict):
    infodictstage[newstage] = defaultdict(instance) if not infodictstage.get(newstage, None) else infodictstage[newstage]


def load_settings(filename):
    settings = defaultdict(dict)
    setting,subsetting = None, None
    with open(Path(filename),"r") as fin:
        for line in fin.readlines():
            line = line.strip().strip(",")
            if len(line) < 1 or line[0] == "#": continue
            if line[0]+line[-1] == "[]":
                setting = line.strip("[]")
                get_defaultdict(settings,setting, instance=list)
                continue
            if setting:
                if "=" in line:
                    subsetting, line = re.sub('\s', '', line).split('=')
                    #settings[setting][subsetting] = []
                if subsetting and isinstance(settings[setting][subsetting],list):
                    for values in line.split(','):
                        if '-' in values and len(values.split('-')) == 2:
                            settings[setting][subsetting].append(range(*sorted([int(val) if not "0x" in val else int(val,16) for val in values.split("-")])))
                        elif '-' not in values:
                            if values.isdigit():
                                settings[setting][subsetting].append(int(values))
                            elif values[:2] == "0x":
                                settings[setting][subsetting].append(int(values,16))
                            elif len(values) > 1:
                                settings[setting][subsetting].append(values)
                            else:
                                settings[setting][subsetting].append(ord(values))
        if setting and subsetting:
            return settings


def categorize(infodict:defaultdict,category="unicode"):
    if category == "unicode":
        for glyphe, count in infodict["overall"]["character"].items():
            uname = unicodedata.name(glyphe)
            ucat = unicodedata.category(glyphe)
            usubcat = uname.split(' ')[0]
            get_defaultdict(infodict["overall"], ucat[0])
            get_defaultdict(infodict["overall"][ucat[0]], usubcat)
            get_defaultdict(infodict["overall"][ucat[0]][usubcat], ucat[1])
            infodict["overall"][ucat[0]][usubcat][ucat[1]].update({glyphe: count})
    else:
        categories = load_settings("./analyse-settings/categories")
        if categories and category in categories.keys():
            for glyphe, count in infodict['overall']['character'].items():
                for subcat, subkeys in categories[category].items():
                    for subkey in subkeys:
                        if ord(glyphe) == subkey or subkey in unicodedata.name(glyphe).replace(" ",""):
                            get_defaultdict(infodict,category)
                            get_defaultdict(infodict[category],subcat)
                            infodict[category][subcat][glyphe] = count
    return


def guidelines(text, infodict, gdlname):
    gdl = load_settings("./analyse-settings/guidelines")
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

# Analyse the overall statistics
get_defaultdict(infodict, "overall")
infodict["overall"]["character"] = reduce(lambda x, y: x+y, infodict["single"].values())

# Analyse the overall statistics with category statistics
categorize(infodict,category="unicode")

# Analyse the overall statistics with customized categories
for category in args.categorize:
    categorize(infodict,category = category)

# Analyse the text versus the guidelines
guidelines(text, infodict, args.guidelines)

# Print the information
pprint(infodict["overall"],indent=4)
pprint(infodict["Fraktur"])
print(ord("A"))