#!/usr/bin/env python


import json
from fuzzywuzzy import fuzz
from pprint import pprint


def get_matches(errors, pattern):
    pprint([x for x in errors if x['component'] == pattern])


with open('component_errors.json', 'rb') as f:
    errors = json.loads(f.read())

GROUPS = []

for error in errors:

    component = error['component']
    print('checking: {}'.format(component))

    for idg,group in enumerate(GROUPS):

        if all(fuzz.ratio(component, gcomponent) > 50 for gcomponent in group):
            group.append(component)
            group = sorted(group)
            break

    else:
        GROUPS.append([component])

GROUPS.sort(key=len)
for group in GROUPS:
    pprint(sorted(group))
import epdb; epdb.st()
