#!/usr/bin/env python


import json
from fuzzywuzzy import fuzz
from pprint import pprint


def get_matches(errors, pattern):
    return [x for x in errors if x['component'] == pattern]


with open('component_errors.json', 'rb') as f:
    errors = json.loads(f.read())

GROUPS = []

for error in errors:

    component = error['component']
    print(f'checking: {component}')

    for idg,group in enumerate(GROUPS):

        if all(fuzz.ratio(component, gcomponent) > 50 for gcomponent in group):
            group.append(component)
            group = sorted(group)
            break

    else:
        GROUPS.append([component])

GROUPS.sort(key=len)
for group in GROUPS:
    print('')
    print('############################')
    pprint(sorted(group))
    print('----------------------------')

    '''
    for x in group:
        matches = get_matches(errors, x)
        if not matches:
            continue
        matches = [m for m in matches if len(m['result']) > 0]
        if matches:

            print('---------------------')
            print('## {}'.format(x))
            pprint(matches)
    '''

import epdb; epdb.st()
