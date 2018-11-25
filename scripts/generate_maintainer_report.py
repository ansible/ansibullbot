#!/usr/bin/env python

import argparse
import datetime
import json
import os
import requests
import sys

from ansibullbot.utils.receiver_client import get_receiver_metadata
from ansibullbot.utils.receiver_client import get_receiver_summaries


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("destdir", default='/tmp/ansibot_data')
    parser.add_argument('--usecache', action="store_true")
    args = parser.parse_args()

    '''
    # define where to dump the resulting files
    if len(sys.argv) > 1:
        destdir = sys.argv[1]
    else:
        destdir = '/tmp/ansibot_data'
    '''
    destdir = args.destdir
    #import epdb; epdb.st()

    if not os.path.isdir(destdir):
        os.makedirs(destdir)

    META = {}
    MAINTAINERS = []
    USERNAMES = []
    HISTORY = []
    LAST_SEEN = {}


    meta_cachefile = os.path.join(destdir, '.meta.json')
    if args.usecache and os.path.isfile(meta_cachefile):
        try:
            with open(meta_cachefile, 'r') as f:
                META = json.loads(f.read())
        except Exception as e:
            print(e)
            META = {}

    summaries = get_receiver_summaries('ansible', 'ansible')
    for summary in summaries:
        number = summary['github_number']

        if args.usecache and str(number) in META:
            this_meta = META.get(str(number))
            if not this_meta:
                continue
        else:
            this_meta = get_receiver_metadata(
                'ansible',
                'ansible',
                number=number,
                keys=[
                    'html_url',
                    'submitter',
                    'created_at',
                    'history',
                    'component_matches'
                ]
            )
            if not this_meta:
                META[str(number)] = None
                continue
            this_meta = this_meta[0]

        if not this_meta:
            continue

        url = this_meta['html_url']
        META[str(number)] = this_meta.copy()

        created_by = this_meta.get('submitter', None)
        if created_by and created_by not in USERNAMES:
            USERNAMES.append(created_by)
            HISTORY.append({
                'actor': created_by,
                'event': 'opened',
                'created_at': this_meta['created_at']
            })
        if 'merged_at' in this_meta:
            import epdb; epdb.st()
        elif 'merged_at' in this_meta:
            import epdb; epdb.st()

        for x in this_meta.get('history', []):
            newx = {
                'actor': x['actor'],
                'event': x['event'],
                'created_at': x['created_at']
            }
            HISTORY.append(newx)

        components = this_meta.get('component_matches', [])
        for component in components:
            if 'maintainers' in component:
                for x in component['maintainers']:
                    if x not in MAINTAINERS:
                        MAINTAINERS.append(x)

    if args.usecache:
        with open(meta_cachefile, 'w') as f:
            f.write(json.dumps(META))

    for x in HISTORY:
        actor = x['actor']
        timestamp = x['created_at']
        if actor not in LAST_SEEN:
            LAST_SEEN[actor] = timestamp
        else:
            if LAST_SEEN[actor] < timestamp:
                LAST_SEEN[actor] = timestamp

    for actor in USERNAMES:
        if actor not in LAST_SEEN:
            LAST_SEEN[actor] = None

    destfile = os.path.join(destdir, 'last_seen.json')
    with open(destfile, 'w') as f:
        f.write(json.dumps(LAST_SEEN, indent=2, sort_keys=True))

    ABSENT = {}
    for maintainer in MAINTAINERS:
        exists = True
        is_absent = False
        ts = LAST_SEEN.get(maintainer)
        if not ts:
            is_absent = True
        else:
            # 2018-01-26T13:24:08+00:00
            ts1 = ts.split('T')[0]
            ts1 = datetime.datetime.strptime(ts1, '%Y-%m-%d')
            days = (datetime.datetime.now() - ts1).days
            if days > 180:
                is_absent = True
                rr = requests.get('https://github.com/{}'.format(maintainer))
                if rr.status_code != 200:
                    exists = False

        if is_absent and maintainer not in ABSENT:
            ABSENT[maintainer] = {
                'last_seen': ts,
                'exists': exists
            }

    destfile = os.path.join(destdir, 'absent_maintainers.json')
    with open(destfile, 'w') as f:
        f.write(json.dumps(ABSENT, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
