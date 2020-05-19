#!/usr/bin/env python

import re
import six


class FileIndexer(object):
    def __init__(self, botmeta=None, gitrepo=None):
        botmeta = botmeta if botmeta else {}
        self.gitrepo = gitrepo
        self._filemap = {}

        self.update(botmeta=botmeta)

    def update(self, botmeta=None):
        if botmeta is not None:
            self.botmeta = botmeta
        self.get_filemap()

    def get_filemap(self):
        '''Read filemap and make re matchers'''
        self._filemap = {}
        bfiles = self.botmeta.get(u'files', {})
        for k, v in bfiles.items():
            self._filemap[k] = {}
            reg = k
            if reg.endswith(u'/'):
                reg += u'*'
            self._filemap[k] = {
                u'inclusive': True,
                u'exclusive': False,
                u'assign': [],
                u'notify': [],
                u'labels': []
            }
            self._filemap[k][u'regex'] = re.compile(reg)
            if not v:
                continue

            if u'maintainers' in v:
                self._filemap[k][u'maintainers'] = v[u'maintainers']
            if u'assign' in v or u'maintainers' in v:
                if u'assign' in v:
                    self._filemap[k][u'assign'] = v[u'assign']
                if u'maintainers' in v:
                    self._filemap[k][u'assign'] += v[u'maintainers']
                    self._filemap[k][u'assign'] = sorted(set(self._filemap[k][u'assign']))
            if u'notify' in v or u'maintainers' in v:
                if u'notify' in v:
                    self._filemap[k][u'notify'] = v[u'notify']
                if u'maintainers' in v:
                    self._filemap[k][u'notify'] += v[u'maintainers']
                    self._filemap[k][u'notify'] = sorted(set(self._filemap[k][u'notify']))
            if u'labels' in v:
                labels = v[u'labels']
                labels = [x for x in labels if x not in [u'lib', u'ansible']]
                self._filemap[k][u'labels'] = labels

    def get_filemap_labels_for_files(self, files):
        '''Get expected labels from the filemap'''
        labels = []
        exclusive = False
        for f in files:
            if f is None:
                continue

            # only one match
            if exclusive:
                continue

            for k, v in six.iteritems(self._filemap):
                if not v[u'inclusive'] and v[u'regex'].match(f):
                    labels = v[u'labels']
                    exclusive = True
                    break

                if u'labels' not in v:
                    continue

                if v[u'regex'].match(f):
                    for label in v[u'labels']:
                        if label not in labels:
                            labels.append(label)

        return labels
