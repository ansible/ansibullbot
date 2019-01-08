#!/usr/bin/env python

import json
import os
import sys

from ansibullbot._text_compat import to_bytes
from ansibullbot.utils.receiver_client import get_receiver_metadata
from ansibullbot.utils.receiver_client import get_receiver_summaries
from ansibullbot.utils.sentry import initialize_sentry


def main():
    initialize_sentry()

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

    summaries = get_receiver_summaries('ansible', 'ansible', state='open')
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
            continue

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

            BYISSUE[url].append(filename)

            if filename not in BYFILE:
                BYFILE[filename] = []
            if url not in BYFILE[filename]:
                BYFILE[filename].append(url)

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
    with open(destfile, 'wb') as f:
        for tup in tuples:
            f.write(b'%s\n' % to_bytes(tup[0]))
            for issue in tup[1:]:
                issue = to_bytes(issue)
                title = to_bytes(ISSUES[issue]['title'])
                f.write(b'\t%s\t%s\n' % (issue, title))

    destfile = os.path.join(destdir, 'byfile_sorted.html')
    with open(destfile, 'wb') as f:
        for idp, tup in enumerate(tuples):
            f.write(b'<div style="background-color: #cfc ; padding: 10px; border: 1px solid green;">\n')
            file_ref = b'%s. <a href="https://github.com/ansible/ansible/blob/devel/%s">https://github.com/ansible/ansible/blob/devel/%s</a> %s total' % (
                (idp+1), to_bytes(tup[0]), to_bytes(tup[0]), len(tup[1:])
            )
            f.write(b'%s\n' % (file_ref))
            f.write(b'</div>')
            f.write(b'<br>\n')
            for issue in tup[1:]:
                issue = to_bytes(issue)
                title = to_bytes(ISSUES[issue]['title'])
                issue_ref = b'<a href="%s">%s</a>' % (issue, issue)
                f.write(b'\t%s\t%s<br>\n' % (issue_ref, title))
            f.write(b'<br>\n')

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
    with open(destfile, 'wb') as f:
        for tup in tuples:
            f.write(b'%s\n' % to_bytes(tup[0]))
            for issue in tup[1:]:
                f.write(b'\t%s\n' % to_bytes(issue))


if __name__ == "__main__":
    main()
