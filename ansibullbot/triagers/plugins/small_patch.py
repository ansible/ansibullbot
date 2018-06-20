#!/usr/bin/env python

import re


FILE_MAX_CHANGED_LINES = 6
SMALL_CHUNKS_MAX_COUNT = 2

RE_CHUNK = r'@@ -\d+,\d+ \+\d+,\d+ @@'


def get_small_patch_facts(iw):
    sfacts = {
        'is_small_patch': False
    }

    if not iw.is_pullrequest():
        return sfacts

    small_chunks_changed = 0

    for commit in iw.get_commits():
        for changed_file in commit.files:
            if changed_file.filename.startswith('test/'):
                continue

            if not changed_file.raw_data['status'] == 'modified':
                return sfacts

            chunks_in_file_count = len(re.findall(RE_CHUNK, changed_file.raw_data['patch']))

            if changed_file.changes > FILE_MAX_CHANGED_LINES:
                return sfacts
            elif changed_file.changes:
                small_chunks_changed += chunks_in_file_count

        if small_chunks_changed > SMALL_CHUNKS_MAX_COUNT:
            return sfacts


    if small_chunks_changed:
        sfacts['is_small_patch'] = True

    return sfacts
