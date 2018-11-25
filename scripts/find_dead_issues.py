#!/usr/bin/env python

import datetime
import json
import os
import sys

from ansibullbot.utils.receiver_client import get_receiver_metadata
from ansibullbot.utils.receiver_client import get_receiver_summaries


def main():

    # define where to dump the resulting files
    if len(sys.argv) > 1:
        destdir = sys.argv[1]
    else:
        destdir = '/tmp'

    if not os.path.isdir(destdir):
        os.makedirs(destdir)

    ISSUES = {}
    BYFILE = {}
    BYISSUE = {}
    BYMAINTAINER = {}
    BYFILE_STATS = {}

    summaries = get_receiver_summaries('ansible', 'ansible')
    for summary in summaries:
        number = summary['github_number']
        this_meta = get_receiver_metadata('ansible', 'ansible', number=number)

        if not this_meta:
            continue

        this_meta = this_meta[0]
        url = this_meta['html_url']
        ISSUES[url] = this_meta
        BYISSUE[url] = []

        try:
            this_meta.get('component_matches', [])
        except Exception as e:
            print(e)
            #import epdb; epdb.st()
            continue

        if summary['state'] == 'open':
            created = datetime.datetime.strptime(
                summary['created_at'].split('T')[0], '%Y-%m-%d'
            )
            age = (datetime.datetime.now() - created).days
        else:
            print(summary)
            import epdb; epdb.st()

        for component in this_meta.get('component_matches', []):
            # we seem to have some variation in the keys ...
            filename = None
            try:
                filename = component['repo_filename']
            except KeyError:
                filename = component['filename']

            if not filename:
                continue

            if 'maintainers' in component:
                for maintainer in component['maintainers']:
                    if maintainer not in BYMAINTAINER:
                        BYMAINTAINER[maintainer] = []
                    if url not in BYMAINTAINER[maintainer]:
                        BYMAINTAINER[maintainer].append(url)

            if filename not in BYFILE_STATS:
                BYFILE_STATS[filename] = {
                    'open_ages': [],
                    'closed_ages': []
                }

            if summary['state'] == 'open':
                BYFILE_STATS[filename]['open_ages'].append([
                    age,
                    this_meta['template_data']['issue type']
                ])
            else:
                import epdb; epdb.st()

            BYISSUE[url].append(filename)

            if filename not in BYFILE:
                BYFILE[filename] = []
            if url not in BYFILE[filename]:
                BYFILE[filename].append(url)

    # median closure time?
    import epdb; epdb.st()

    # most active files?
    import epdb; epdb.st()


    '''
    destfile = os.path.join(destdir, 'byissue.json')
    with open(destfile, 'w') as f:
        f.write(json.dumps(BYISSUE, indent=2, sort_keys=True))

    destfile = os.path.join(destdir, 'byfile.json')
    with open(destfile, 'w') as f:
        f.write(json.dumps(BYFILE, indent=2, sort_keys=True))

    tuples = BYFILE.items()
    for idx, x in enumerate(tuples):
        x = [x[0]] + x[1]
        tuples[idx] = x
    tuples.sort(key=len)
    tuples.reverse()

    destfile = os.path.join(destdir, 'byfile_sorted.txt')
    with open(destfile, 'w') as f:
        for tup in tuples:
            f.write('{}\n'.format(tup[0]))
            for issue in tup[1:]:
                issue = issue.encode('ascii', 'ignore')
                title = ISSUES[issue]['title']
                title = title.encode('ascii', 'ignore')
                f.write('\t{}\t{}\n'.format(issue, title))

    destfile = os.path.join(destdir, 'byfile_sorted.html')
    with open(destfile, 'w') as f:
        for tup in tuples:
            f.write('<div style="background-color: #cfc ; padding: 10px; border: 1px solid green;">\n')
            file_ref = '<a href="https://github.com/ansible/ansible/blob/devel/{}">https://github.com/ansible/ansible/blob/devel/{}</a>'.format(tup[0], tup[0])
            f.write('{}\n'.format(file_ref))
            f.write('</div>')
            f.write('<br>\n')
            for issue in tup[1:]:
                issue = issue.encode('ascii', 'ignore')
                title = ISSUES[issue]['title']
                title = title.encode('ascii', 'ignore')

                issue_ref = '<a href="{}">{}</a>'.format(issue, issue)
                f.write('\t{}\t{}<br>\n'.format(issue_ref, title))
            f.write('<br>\n')

    tuples = BYMAINTAINER.items()
    for idx, x in enumerate(tuples):
        x = [x[0]] + x[1]
        tuples[idx] = x
    tuples.sort(key=len)
    tuples.reverse()

    destfile = os.path.join(destdir, 'bymaintainer.json')
    with open(destfile, 'w') as f:
        f.write(json.dumps(BYMAINTAINER, indent=2, sort_keys=True))

    destfile = os.path.join(destdir, 'bymaintainer_sorted.txt')
    with open(destfile, 'w') as f:
        for tup in tuples:
            f.write('{}\n'.format(tup[0]))
            for issue in tup[1:]:
                f.write('\t{}\n'.format(issue))
    '''


if __name__ == "__main__":
    main()
