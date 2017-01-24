#!/usr/bin/env python

import json
import glob
import pickle
import os

DATA = {}

CPATH = os.path.join(
    os.path.expanduser('~/.ansibullbot'),
    'cache',
    'ansible',
    'ansible',
    'issues'
)

ISSUES = glob.glob('%s/*' % CPATH)
for ISSUE in ISSUES:
    mfile = os.path.join(ISSUE, 'meta.json')
    if not os.path.isfile(mfile):
        continue

    number = os.path.basename(ISSUE)

    with open(mfile, 'rb') as f:
        jdata = json.load(f)

    if jdata.get('template_data'):
        if 'component_raw' not in jdata['template_data']:
            pass
        if not jdata['template_data'].get('component_raw'):
            continue

        mm = jdata.get('module_match')
        if mm:
            mm = mm['filepath']

        # need the title ...
        if 'title' not in jdata:
            rdfile = os.path.join(ISSUE, 'raw_data.pickle')
            if os.path.isfile(rdfile):
                with open(rdfile, 'rb') as f:
                    rdata = pickle.load(f)
                jdata['title'] = rdata[1]['title']
        if 'title' not in jdata:
            rdfile = os.path.join(ISSUE, 'issue.pickle')
            if os.path.isfile(rdfile):
                with open(rdfile, 'rb') as f:
                    rdata = pickle.load(f)
                jdata['title'] = rdata.title

        DATA[number] = {
            'title': jdata.get('title'),
            'issue_type': jdata['template_data'].get('issue type'),
            'ansible_version': jdata['template_data'].get('ansible version'),
            'component_raw': jdata['template_data'].get('component_raw'),
            'component_name': jdata['template_data'].get('component name'),
            'module_match': mm,
            'summary': jdata['template_data'].get('summary')
        }

print(json.dumps(DATA, indent=2, sort_keys=True))
