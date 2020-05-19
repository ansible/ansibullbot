#!/usr/bin/env python

import logging
import re

import six

from ansibullbot._text_compat import to_text
from ansibullbot.parsers.botmetadata import BotMetadataParser
from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.moduletools import ModuleIndexer


class FileIndexer(ModuleIndexer):

    DEFAULT_COMPONENT_MATCH = {
        u'supported_by': u'core',
        u'filename': None,
        u'labels': [],
        u'owners': [],
        u'notify': []
    }

    files = []

    def __init__(self, botmeta=None, botmetafile=None, gitrepo=None):
        self.botmetafile = botmetafile
        if botmeta:
            self.botmeta = botmeta
        else:
            self.botmeta = {}
        self.CMAP = {}
        self.FILEMAP = {}
        self.gitrepo = gitrepo
        self.update(force=True)

    def parse_metadata(self):

        if not self.botmeta:
            if self.botmetafile is not None:
                with open(self.botmetafile, 'rb') as f:
                    rdata = f.read()
            else:
                fp = u'.github/BOTMETA.yml'
                rdata = self.get_file_content(fp)
            if rdata:
                logging.info('fileindexder parsing botmeta')
                self.botmeta = BotMetadataParser.parse_yaml(rdata)
            else:
                self.botmeta = {}

        # reshape meta into old format
        logging.info('reshape botmeta')
        self.CMAP = {}
        for k, v in self.botmeta.get(u'files', {}).items():
            if not v:
                continue
            if u'keywords' not in v:
                continue
            for keyword in v[u'keywords']:
                if keyword not in self.CMAP:
                    self.CMAP[keyword] = []
                if k not in self.CMAP[keyword]:
                    self.CMAP[keyword].append(k)

        # update the data
        self.get_files()
        self.get_filemap()

    def get_files(self):

        cmd = u'find %s' % self.gitrepo.checkoutdir
        (rc, so, se) = run_command(cmd)
        files = to_text(so).split(u'\n')
        files = [x.strip() for x in files if x.strip()]
        files = [x.replace(self.gitrepo.checkoutdir + u'/', u'') for x in files]
        files = [x for x in files if not x.startswith(u'.git')]
        self.files = files

    def get_filemap(self):
        '''Read filemap and make re matchers'''

        self.FILEMAP = {}
        bfiles = self.botmeta.get(u'files', {})
        for k, v in bfiles.items():
            self.FILEMAP[k] = {}
            reg = k
            if reg.endswith(u'/'):
                reg += u'*'
            self.FILEMAP[k] = {
                u'inclusive': True,
                u'exclusive': False,
                u'assign': [],
                u'notify': [],
                u'labels': []
            }
            self.FILEMAP[k][u'regex'] = re.compile(reg)
            if not v:
                continue

            if u'maintainers' in v:
                self.FILEMAP[k][u'maintainers'] = v[u'maintainers']
            if u'assign' in v or u'maintainers' in v:
                if u'assign' in v:
                    self.FILEMAP[k][u'assign'] = v[u'assign']
                if u'maintainers' in v:
                    self.FILEMAP[k][u'assign'] += v[u'maintainers']
                    self.FILEMAP[k][u'assign'] = sorted(set(self.FILEMAP[k][u'assign']))
            if u'notify' in v or u'maintainers' in v:
                if u'notify' in v:
                    self.FILEMAP[k][u'notify'] = v[u'notify']
                if u'maintainers' in v:
                    self.FILEMAP[k][u'notify'] += v[u'maintainers']
                    self.FILEMAP[k][u'notify'] = sorted(set(self.FILEMAP[k][u'notify']))
            if u'labels' in v:
                labels = v[u'labels']
                labels = [x for x in labels if x not in [u'lib', u'ansible']]
                self.FILEMAP[k][u'labels'] = labels

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

            for k, v in six.iteritems(self.FILEMAP):
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
