#!/usr/bin/env python3

import argparse
import io
from collections import defaultdict, Counter, OrderedDict
from pathlib import Path
from functools import reduce
import unicodedata
import json
import re
import sys

# Command line arguments.
arg_parser = argparse.ArgumentParser(description='Analyze the ground truth texts for the given text files.')
arg_parser.add_argument("filename", type=lambda x: Path(x), help="filename of text file or path to files", nargs='*')
arg_parser.add_argument("-o","--output", type=lambda x: Path(x) if x is not None else None, default=None,help="filename of the output report, \
                        if none is given the result is printed to stdout")
arg_parser.add_argument("-j", "--json", help="will also output the all results as json file",
                        action="store_true")
arg_parser.add_argument("-n", "--dry-run", help="show which files would be normalized but don't change them",
                        action="store_true")
arg_parser.add_argument("-v", "--verbose", help="show ignored files", action="store_true")
arg_parser.add_argument("-f", "--form", help="normalization form (default: NFC)",
                        choices=["NFC", "NFKC", "NFD", "NFKD"], default="NFC")
arg_parser.add_argument("-c", "--categorize", help="Customized unicodedata categories", type=str, default=["Fraktur"],
                        nargs='*')
arg_parser.add_argument("-g", "--guidelines", help="Evaluated the dataset against some guidelines", type=str,
                        default="OCRD-1", choices=["OCRD-1", "OCRD-2", "OCRD-3"])
arg_parser.add_argument("-t", "--textnormalization", help="Textnormalization settings", type=str, default="NFC",
                        choices=["NFC", "NFKC", "NFD", "NFKD"])


args = arg_parser.parse_args()


def get_defaultdict(resultslvl, newlvl, instance=OrderedDict):
    resultslvl[newlvl] = defaultdict(instance) if not resultslvl.get(newlvl, None) else resultslvl[newlvl]


def load_settings(filename):
    settings = defaultdict(dict)
    setting, subsetting = None, None
    with open(Path(filename), 'r') as fin:
        for line in fin.readlines():
            line = line.strip()
            if len(line) < 1 or line[0] == '#': continue
            if line[0] + line[-1] == '[]':
                setting = line.strip('[]')
                get_defaultdict(settings, setting, instance=list)
                continue
            if setting:
                if '==' in line:
                    subsetting, line = line.split("==")
                    line = re.sub(r' ', '', line)
                if subsetting and isinstance(settings[setting][subsetting], list):
                    for values in line.split('||'):
                        if '-' in values and len(values.split('-')) == 2:
                            settings[setting][subsetting].append(range(
                                *sorted([int(val) if not '0x' in val else int(val, 16) for val in values.split('-')])))
                        elif '-' not in values:
                            if values.isdigit():
                                settings[setting][subsetting].append(int(values))
                            elif values[:2] == '0x':
                                settings[setting][subsetting].append(int(values, 16))
                            elif len(values) > 1:
                                settings[setting][subsetting].append(values)
                            else:
                                settings[setting][subsetting].append(ord(values))
        if setting and subsetting:
            return settings


def categorize(results: defaultdict, category='overall'):
    if category == 'overall':
        for glyphe, count in results[category]['character'].items():
            uname = unicodedata.name(glyphe)
            ucat = unicodedata.category(glyphe)
            usubcat = uname.split(' ')[0]
            get_defaultdict(results[category], ucat[0])
            get_defaultdict(results[category][ucat[0]], usubcat)
            get_defaultdict(results[category][ucat[0]][usubcat], ucat)
            results[category][ucat[0]][usubcat][ucat].update({glyphe: count})
    else:
        categories = load_settings("settings/analyse/categories")
        if categories and category in categories.keys():
            for glyphe, count in results['overall']['character'].items():
                for subcat, subkeys in categories[category].items():
                    for subkey in subkeys:
                        if ord(glyphe) == subkey or subkey in unicodedata.name(glyphe).replace(' ', ''):
                            get_defaultdict(results, category)
                            get_defaultdict(results[category], subcat)
                            results[category][subcat][glyphe] = count
    return


def validate_guidelines(fulltext, results, guideline):
    guidelines = load_settings("settings/analyse/guidelines")
    delregex = []
    if guidelines and guideline in guidelines.keys():
        for conditionkey, conditions in guidelines[guideline].items():
            if "REGEX" not in conditionkey.upper(): continue
            for condition in conditions:
                count = re.findall(rf"{condition}", fulltext)
                if count:
                    get_defaultdict(results, guideline)
                    get_defaultdict(results[guideline], conditionkey)
                    results[guideline][conditionkey][condition] = len(count)
            delregex.append(conditionkey)
        #tbd: replace with elegant implementation
        for conditionkey in delregex:
            del guidelines[guideline][conditionkey]
        for glyphe, count in results['overall']['character'].items():
            for conditionkey, conditions in guidelines[guideline].items():
                for condition in conditions:
                    if ord(glyphe) == condition or \
                            isinstance(condition, str) and condition.upper() in unicodedata.name(glyphe).replace(' ', ''):
                        get_defaultdict(results, guideline)
                        get_defaultdict(results[guideline], conditionkey)
                        results[guideline][conditionkey][glyphe] = count
    return


def report_subsection(fout, subsection, result, header="", subheaderinfo=""):
    addline = '\n'
    fout.write(f"""
{header}
{subheaderinfo}{addline if subheaderinfo != "" else ""}""")
    for condition, conditionres in result[subsection].items():
        fout.write(f"""
        {condition}
        {"-"*len(condition)}""")
        for key, val in conditionres.items():
            if isinstance(val,dict):
                fout.write(f"""
            {key}:""")
                for keyy, vall in sorted(val.items()):
                    fout.write(f"""
                {keyy}: {vall}""")
            else:
                fout.write(f"""
            {key}: {val}""")
    fout.write(f"""
    \n{"-"*60}\n""")
    return


def sum_statistics(result, section):
    return sum([val for subsection in result[section].values() for val in subsection.values()])


def create_report(result, output):
    if not output:
        fout = sys.stdout
    else:
        fout = open(output,'w')
    fout.write(f"""
Analyse-Report Version 0.1
Input: {";".join(set([str(fname.resolve().parent) for fname in args.filename]))}
\n{"-"*60}\n""")
    if args.guidelines in result.keys():
        violations = sum_statistics(result,args.guidelines)
        report_subsection(fout,args.guidelines,result, \
                          header=f"{args.guidelines} Guidelines Evaluation", subheaderinfo=f"Guideline violations overall: {violations}")
    for category in args.categorize:
        if category in result.keys():
            occurences = sum_statistics(result, category)
            report_subsection(fout,category,result, \
                              header=f"Category statistics: {category}", subheaderinfo=f"Overall occurrences: {occurences}")
    if "overall" in result.keys():
        report_subsection(fout, "L", result["overall"], header="Overall Letter statistics")
        #pass
        #create_subsection(fout, "overall",result, header="Overall statistics")
    if "single" in result.keys():
        pass
        #create_subsection(fout,"single",result, header="Single statistics")
    fout.flush()
    fout.close()
    return

def create_json(results,output):
    if output:
        jout = open(output.join(".json"), "w")
    else:
        jout = sys.stdout
    json.dump(jout, results, indent=4)
    jout.flush()
    jout.close()
    return


def validate_output(args):
    output = args.output
    if not output: return
    if not output.parent.exist():
        output.parent.mkdir()
    if not output.is_file():
        output.join("result.txt")
    args.output = output
    return

def main():
    # Set filenames or path
    if len(args.filename) == 1 and not args.filename[0].is_file():
        args.filename = list(Path(args.filename[0]).rglob("*.txt"))

    results = defaultdict(OrderedDict)

    # Read all files.
    fulltext = ""
    for filename in args.filename:
        with io.open(filename, 'r', encoding='utf-8') as fin:
            try:
                text = unicodedata.normalize(args.textnormalization, fin.read().strip())
                fulltext += text
                results['single'][filename.name] = Counter(text)
            except UnicodeDecodeError:
                if args.verbose:
                    print(filename.name + " (ignored)")
                continue

    # Analyse the overall statistics
    get_defaultdict(results, 'overall')
    results['overall']['character'] = reduce(lambda x, y: x + y, results['single'].values())

    # Analyse the overall statistics with category statistics
    categorize(results, category='overall')

    # Analyse the overall statistics with customized categories
    for category in args.categorize:
        categorize(results, category=category)

    # Validate the text versus the guidelines
    validate_guidelines(fulltext, results, args.guidelines)

    # Print the information
    #pprint(results['overall'], indent=4)
    #pprint(results['Fraktur'])
    #pprint(results['OCRD-1'])
    validate_output(args)
    create_report(results,args.output)
    if args.json: create_json(results,args.output)


if __name__ == '__main__':
    main()