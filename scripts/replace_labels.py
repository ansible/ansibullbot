#!/usr/bin/env python

"""
Usage: ./scripts/list_docs_report.sh | ./scripts/replace_labels.py --add docs --remove docs_report
"""


import argparse
import json
import sys
import requests

import ansibullbot.constants as C


HEADERS = {'Authorization': 'token %s' % C.DEFAULT_GITHUB_TOKEN}
ISSUE_URL_FMT = 'https://api.github.com/repos/ansible/ansible/issues/{}'
LABEL_URL_FMT = 'https://api.github.com/repos/ansible/ansible/issues/{}/labels{}'


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--add', dest='add_label', action='store')
    parser.add_argument('-r', '--remove', dest='remove_label', action='store')

    args = parser.parse_args()

    return args


def main():
    args = parse_args()
    lines = sys.stdin.readlines()
    for line in lines:
        numbers = json.loads(line)
        numbers = sorted(set(numbers))

        for number in numbers:
            print(number)

            iurl = ISSUE_URL_FMT.format(number)
            ir = requests.get(iurl, headers=HEADERS)
            idata = ir.json()
            try:
                labels = [l['name'] for l in idata['labels']]
            except KeyError:
                continue

            if args.remove_label in labels:
                url = LABEL_URL_FMT.format(number, '/'+args.remove_label)
                r = requests.delete(url, headers=HEADERS)
                if r.status_code != 200:
                    import epdb; epdb.st()

                if args.add_label not in labels:
                    url = LABEL_URL_FMT.format(number, '')
                    r = requests.post(url, data=json.dumps([args.add_label]), headers=HEADERS)
                    if r.status_code != 200:
                        import epdb; epdb.st()


if __name__ == "__main__":
    main()
