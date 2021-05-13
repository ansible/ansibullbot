import re


FILE_MAX_CHANGED_LINES = 6
SMALL_CHUNKS_MAX_COUNT = 2

RE_CHUNK = r'@@ -\d+,\d+ \+\d+,\d+ @@'


class CommitFile:
    def __init__(self, raw_data):
        self.raw_data = raw_data

    @property
    def filename(self):
        return self.raw_data.get('filename')

    @property
    def changes(self):
        return self.raw_data.get('changes')


def get_small_patch_facts(iw):
    sfacts = {
        'is_small_patch': False
    }

    if not iw.is_pullrequest():
        return sfacts

    small_chunks_changed = 0

    for commit in iw.commits:
        if iw.get_commit_files(commit) is None:
            # "Sorry, this diff is temporarily unavailable due to heavy server load."
            # Preserve small_patch label to prevent potential waffling
            sfacts['is_small_patch'] = 'small_patch' in iw.labels
            return sfacts

        for changed_file in iw.get_commit_files(commit):

            if isinstance(changed_file, dict):
                changed_file = CommitFile(changed_file)

            if changed_file.filename.startswith('test/'):
                continue

            if not changed_file.raw_data['status'] == 'modified':
                return sfacts

            try:
                chunks_in_file_count = len(re.findall(RE_CHUNK, changed_file.raw_data['patch']))
            except KeyError:
                continue

            if changed_file.changes > FILE_MAX_CHANGED_LINES:
                return sfacts
            elif changed_file.changes:
                small_chunks_changed += chunks_in_file_count

        if small_chunks_changed > SMALL_CHUNKS_MAX_COUNT:
            return sfacts


    if small_chunks_changed:
        sfacts['is_small_patch'] = True

    return sfacts
