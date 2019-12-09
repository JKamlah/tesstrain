#!/usr/bin/env python3

import argparse
import io
import json
import re
import sys
import unicodedata
from collections import defaultdict, Counter, OrderedDict
from pathlib import Path

# Command line arguments.
arg_parser = argparse.ArgumentParser(description='Analyze the ground truth texts for the given text files.')
arg_parser.add_argument("filename", type=lambda x: Path(x), help="filename of text file or path to files", nargs='*')
arg_parser.add_argument("-o", "--output", type=lambda x: Path(x) if x is not None else None, default=None,
                        help="filename of the output report, \
                        if none is given the result is printed to stdout")
arg_parser.add_argument("-j", "--json", help="will also output the all results as json file (including the guideline_violations)",
                        action="store_true")
arg_parser.add_argument("-n", "--dry-run", help="show which files would be normalized but don't change them",
                        action="store_true")
arg_parser.add_argument("-f", "--form", help="normalization form (default: NFC)",
                        choices=["NFC", "NFKC", "NFD", "NFKD"], default="NFC")
arg_parser.add_argument("-c", "--categorize", help="Customized unicodedata categories", type=str, default=["Good Practice"],
                        nargs='*')
arg_parser.add_argument("-g", "--guidelines", help="Evaluated the dataset against some guidelines", type=str,
                        default="OCRD-1", choices=["OCRD-1", "OCRD-2", "OCRD-3"])
arg_parser.add_argument("-t", "--textnormalization", help="Textnormalization settings", type=str, default="NFC",
                        choices=["NFC", "NFKC", "NFD", "NFKD"])
arg_parser.add_argument("-v", "--verbose", help="show ignored files", action="store_true")


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
                    line = line.strip()
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


def validate_guidelines(results, args):
    guideline = args.guidelines
    guidelines = load_settings("settings/analyse/guidelines")
    if guidelines and guideline in guidelines.keys():
        for file, fileinfo in results['single'].items():
            text = fileinfo['text']
            for conditionkey, conditions in guidelines[guideline].items():
                for condition in conditions:
                    if "REGEX" in conditionkey.upper():
                        count = re.findall(rf"{condition}", text)
                        if count:
                            get_defaultdict(results, guideline)
                            get_defaultdict(results[guideline], conditionkey, instance = int)
                            results[guideline][conditionkey][condition] += len(count)
                            if args.json:
                                get_defaultdict(results['single'][file],'guideline_violation',instance = int)
                                results['single'][file]['guideline_violation'][condition] += len(count)
                    else:
                        for glyphe in text:
                            if ord(glyphe) == condition or \
                                isinstance(condition, str) and \
                                    condition.upper() in unicodedata.name(glyphe):
                                get_defaultdict(results, guideline)
                                get_defaultdict(results[guideline], conditionkey, instance = int)
                                results[guideline][conditionkey][condition] += 1
    return


def report_subsection(fout, subsection, result, header="", subheaderinfo=""):
    addline = '\n'
    fout.write(f"""
    {header}
    {subheaderinfo}{addline if subheaderinfo != "" else ""}""")
    if not result:
        fout.write(f"""{"-" * 60}\n""")
        return
    for condition, conditionres in result[subsection].items():
        fout.write(f"""
        {condition}
        {"-" * len(condition)}""")
        for key, val in conditionres.items():
            if isinstance(val, dict):
                fout.write(f"""
            {key}:""")
                for subkey, subval in sorted(val.items()):
                    fout.write(f"""
                {subval:-{6}}: [{subkey}]""")
            else:
                fout.write(f"""
            {val:-{6}}: [{key}]""")
    fout.write(f"""
    \n{"-" * 60}\n""")
    return


def sum_statistics(result, section):
    return sum([val for subsection in result[section].values() for val in subsection.values()])


def summerize(results, category):
    if category == "character": return
    if category in results:
        get_defaultdict(results, "sum")
        results["sum"]["sum"] = results["sum"].get('sum', 0)
        get_defaultdict(results["sum"], category)
        results["sum"][category]["sum"] = 0
        for sectionkey, sectionval in results[category].items():
            get_defaultdict(results["sum"][category], sectionkey)
            results["sum"][category][sectionkey]["sum"] = 0
            if isinstance(sectionval, dict):
                for subsectionkey, subsectionval in sorted(sectionval.items()):
                    get_defaultdict(results["sum"][category][sectionkey], subsectionkey)
                    intermediate_sum = sum(subsectionval.values())
                    results["sum"][category][sectionkey][subsectionkey]["sum"] = intermediate_sum
                    results["sum"][category][sectionkey]["sum"] += intermediate_sum
                    results["sum"][category]["sum"] += intermediate_sum
                    results["sum"]["sum"] += intermediate_sum

            else:
                intermediate_sum = sum(sectionval.values())
                results["sum"][category][sectionkey]["sum"] = intermediate_sum
                results["sum"][category]["sum"] += intermediate_sum
                results["sum"]["sum"] += intermediate_sum


def create_report(result, output):
    fpoint = 6
    if not output:
        fout = sys.stdout
    else:
        fout = open(output, 'w')
    fout.write(f"""
    Analyse-Report Version 0.1
    Input: {";".join(set([str(fname.resolve().parent) for fname in args.filename]))}
    \n{"-" * 60}\n""")
    if "overall" in result.keys():
        subheader = f"""
        {result.get('overall', 0).get('sum', 0).get('Z', 0).get('SPACE', 0).get('Zs', 0).get('sum', 0):-{fpoint}} : ASCII Spacing Symbols
        {result.get('overall', 0).get('sum', 0).get('N', 0).get('DIGIT', 0).get('Nd', 0).get('sum', 0):-{fpoint}} : ASCII Digits
        {result.get('overall', 0).get('sum', 0).get('L', 0).get('LATIN', 0).get('sum', 0):-{fpoint}} : ASCII Letters
        {result.get('overall', 0).get('sum', 0).get('L', 0).get('LATIN', 0).get('Ll', 0).get('sum', 0):-{fpoint}} : ASCII Lowercase Letters
        {result.get('overall', 0).get('sum', 0).get('L', 0).get('LATIN', 0).get('Lu', 0).get('sum', 0):-{fpoint}} : ASCII Uppercase Letters
        {result.get('overall', 0).get('sum', 0).get('P', 0).get('sum', 0):-{fpoint}} : Punctuation & Symbols
        {result.get('overall', 0).get('sum', 0).get('sum', 0):-{fpoint}} : Total Glyphes
    """
        report_subsection(fout, "L", {}, header="Statistics overall", subheaderinfo=subheader)
    if args.guidelines in result.keys():
        violations = sum_statistics(result, args.guidelines)
        report_subsection(fout, args.guidelines, result, \
                          header=f"{args.guidelines} Guidelines Evaluation",
                          subheaderinfo=f"Guideline violations overall: {violations}")
    for category in args.categorize:
        if category in result.keys():
            occurences = sum_statistics(result, category)
            report_subsection(fout, category, result, \
                              header=f"Category statistics: {category}",
                              subheaderinfo=f"Overall occurrences: {occurences}")
    if "overall" in result.keys():
        report_subsection(fout, "L", result["overall"], header="Overall Letter statistics")
    fout.flush()
    if fout != sys.stdout:
        fout.close()
    return


def create_json(results, output):
    if output:
        jout = open(output.with_suffix(".json"), "w", encoding='utf-8')
    else:
        jout = sys.stdout
    json.dump(results, jout, indent=4, ensure_ascii=False).encode('utf8')
    jout.flush()
    jout.close()
    return


def validate_output(args):
    output = args.output
    if not output: return
    if not output.parent.exists():
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
    for filename in args.filename:
        with io.open(filename, 'r', encoding='utf-8') as fin:
            try:
                text = unicodedata.normalize(args.textnormalization, fin.read().strip())
                get_defaultdict(results['single'], filename.name)
                results['single'][filename.name]['text'] = text
            except UnicodeDecodeError:
                if args.verbose:
                    print(filename.name + " (ignored)")
                continue

    # Analyse the overall statistics
    get_defaultdict(results, 'overall')
    results['overall']['character'] = Counter("".join([text for fileinfo in results['single'].values() for text in fileinfo.values()]))

    # Analyse the overall statistics with category statistics
    categorize(results, category='overall')

    # Analyse the overall statistics with customized categories
    for category in args.categorize:
        categorize(results, category=category)

    # Validate the text versus the guidelines
    validate_guidelines(results, args)

    # Summerize category data
    for key in set(results["overall"].keys()):
        summerize(results["overall"], key)

    # Print the information
    validate_output(args)
    create_report(results, args.output)
    if args.json: create_json(results, args.output)

if __name__ == '__main__':
    main()
