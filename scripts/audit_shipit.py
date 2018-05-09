#!/usr/bin/env python

import glob
import json
import os
import sys
import subprocess

from pprint import pprint


def main():
    base_path = os.path.expanduser('~/.ansibullbot/cache/ansible/ansible/issues')
    meta_files = glob.glob('%s/*/meta.json' % base_path)

    ranks = []

    for mf in meta_files:
        with open(mf, 'r') as f:
            meta = json.loads(f.read())
        if meta.get('state', 'closed') != 'open':
            continue
        if meta.get('shipit_count_vtotal', 0) == 0:
            continue
        if 'shipit' in meta.get('labels', []):
            continue

        # TBD
        #if meta.get('submitter_previous_commits_for_pr_files', 0) == 0:
        #    continue

        print(meta['html_url'])
        print('submitter: ' + str(meta['submitter']))
        print('previous_commits: ' + str(meta['submitter_previous_commits']))
        print('previous_related_commits: ' + str(meta['submitter_previous_commits_for_pr_files']))
        print('vshipits: ' + str(meta['shipit_count_vtotal']))
        for x in meta['component_filenames']:
            print('\t' + x)

        ranks.append([
            mf,
            meta['html_url'],
            meta['title'],
            meta['shipit_count_vtotal'],
            meta['submitter_previous_commits'],
            meta['submitter_previous_commits_for_pr_files']
        ])
        #import epdb; epdb.st()

    import epdb; epdb.st()


if __name__ == "__main__":
    main()
