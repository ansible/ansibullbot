#!/usr/bin/env python

import glob
import json
import os
import sys
import subprocess

from pprint import pprint


def main():
    base_path = os.path.expanduser(u'~/.ansibullbot/cache/ansible/ansible/issues')
    meta_files = glob.glob(u'%s/*/meta.json' % base_path)

    ranks = []

    for mf in meta_files:
        with open(mf, 'r') as f:
            meta = json.loads(f.read())
        if meta.get(u'state', u'closed') != u'open':
            continue
        if meta.get(u'shipit_count_vtotal', 0) == 0:
            continue
        if u'shipit' in meta.get(u'labels', []):
            continue

        # TBD
        #if meta.get('submitter_previous_commits_for_pr_files', 0) == 0:
        #    continue

        print(meta[u'html_url'])
        print(u'submitter: ' + str(meta[u'submitter']))
        print(u'previous_commits: ' + str(meta[u'submitter_previous_commits']))
        print(u'previous_related_commits: ' + str(meta[u'submitter_previous_commits_for_pr_files']))
        print(u'vshipits: ' + str(meta[u'shipit_count_vtotal']))
        for x in meta[u'component_filenames']:
            print(u'\t' + x)

        ranks.append([
            mf,
            meta[u'html_url'],
            meta[u'title'],
            meta[u'shipit_count_vtotal'],
            meta[u'submitter_previous_commits'],
            meta[u'submitter_previous_commits_for_pr_files']
        ])


if __name__ == "__main__":
    main()
