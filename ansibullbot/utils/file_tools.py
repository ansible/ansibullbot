#!/usr/bin/env python

import copy
import logging
import os
import re

import six

from fuzzywuzzy import fuzz as fw_fuzz
from textblob import TextBlob

from ansibullbot._text_compat import to_text
from ansibullbot.parsers.botmetadata import BotMetadataParser
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.systemtools import run_command
from ansibullbot.utils.moduletools import ModuleIndexer

import ansibullbot.constants as C


class FileIndexer(ModuleIndexer):

    DEFAULT_COMPONENT_MATCH = {
        u'supported_by': u'core',
        u'filename': None,
        u'labels': [],
        u'owners': [],
        u'notify': []
    }

    files = []

    def __init__(self, botmetafile=None, gitrepo=None, commit=None):
        self.botmetafile = botmetafile
        self.botmeta = {}
        self.CMAP = {}
        self.FILEMAP = {}
        self.match_cache = {}
        self.gitrepo = gitrepo
        self.commit = commit
        self.update(force=True)
        self.email_commits = {}

    def parse_metadata(self):

        if self.botmetafile is not None:
            with open(self.botmetafile, 'rb') as f:
                rdata = f.read()
        else:
            fp = u'.github/BOTMETA.yml'
            rdata = self.get_file_content(fp)
        if rdata:
            self.botmeta = BotMetadataParser.parse_yaml(rdata)
        else:
            self.botmeta = {}

        # reshape meta into old format
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

    def get_component_labels(self, files, valid_labels=[]):
        '''Matches a filepath to the relevant c: labels'''
        labels = [x for x in valid_labels if x.startswith(u'c:')]

        clabels = []
        for cl in labels:
            cl = cl.replace(u'c:', u'', 1)
            al = os.path.join(u'lib/ansible', cl)
            if al.endswith(u'/'):
                al = al.rstrip(u'/')
            for f in files:
                if not f:
                    continue
                if f.startswith(cl) or f.startswith(al):
                    clabels.append(cl)

        # use the more specific labels
        clabels = sorted(set(clabels))
        tmp_clabels = [x for x in clabels]
        for cl in clabels:
            for x in tmp_clabels:
                if cl != x and x.startswith(cl):
                    if cl in tmp_clabels:
                        tmp_clabels.remove(cl)
        if tmp_clabels != clabels:
            clabels = [x for x in tmp_clabels]
            clabels = sorted(set(clabels))

        # Use botmeta
        ckeys = self._filenames_to_keys(files)
        for ckey in ckeys:
            if not self.botmeta[u'files'].get(ckey):
                continue
            ckey_labels = self.botmeta[u'files'][ckey].get(u'labels', [])
            for cklabel in ckey_labels:
                if cklabel in valid_labels and cklabel not in clabels:
                    clabels.append(cklabel)

        return clabels

    def _filenames_to_keys(self, filenames):
        '''Match filenames to the keys in botmeta'''
        ckeys = set()
        for filen in filenames:
            if filen in self.botmeta[u'files']:
                ckeys.add(filen)
            for key in self.botmeta[u'files'].keys():
                if filen.startswith(key):
                    ckeys.add(key)
        return list(ckeys)

    def _string_to_cmap_key(self, text):
        text = text.lower()
        matches = []
        if text.endswith(u'.'):
            text = text.rstrip(u'.')
        if text in self.CMAP:
            matches += self.CMAP[text]
            return matches
        elif (text + u's') in self.CMAP:
            matches += self.CMAP[text + u's']
            return matches
        elif text.rstrip(u's') in self.CMAP:
            matches += self.CMAP[text.rstrip(u's')]
            return matches
        return matches

    def get_keywords_for_file(self, filename):
        keywords = []
        for k, v in self.CMAP.items():
            toadd = False
            for x in v:
                if x == filename:
                    toadd = True
            if toadd:
                keywords.append(k)
        return keywords

    def find_component_matches_by_file(self, filenames):
        '''Make a list of component matches based on filenames'''

        matches = []
        for filen in filenames:
            match = copy.deepcopy(self.DEFAULT_COMPONENT_MATCH)
            match[u'filename'] = filen

            ckeys = self._filenames_to_keys([filen])
            ckeys = sorted(set(ckeys))

            for ckey in ckeys:
                cdata = self.botmeta[u'files'].get(ckey)
                if not cdata:
                    continue

                if u'labels' in cdata:
                    for label in cdata[u'labels']:
                        if label not in match[u'labels']:
                            match[u'labels'].append(label)

                if u'support' in cdata:
                    match[u'supported_by'] = cdata[u'support'][0]

                if u'maintainers' in cdata:
                    for user in cdata[u'maintainers']:
                        if user not in match[u'owners']:
                            match[u'owners'].append(user)

                if u'notify' in cdata:
                    for user in cdata[u'notify']:
                        if user not in match[u'notify']:
                            match[u'notify'].append(user)

            matches.append(match)

        return matches

    def find_component_match(self, title, body, template_data):
        '''Make a list of matching files for arbitrary text in an issue'''

        # DistributionNotFound: The 'jinja2<2.9' distribution was not found and
        #   is required by ansible
        # File
        # "/usr/lib/python2.7/site-packages/ansible/plugins/callback/foreman.py",
        #   line 30, in <module>

        STOPWORDS = [u'ansible', u'core', u'plugin']
        STOPCHARS = [u'"', u"'", u'(', u')', u'?', u'*', u'`', u',']
        matches = []

        if u'Traceback (most recent call last)' in body:
            lines = body.split(u'\n')
            for line in lines:
                line = line.strip()
                if line.startswith(u'DistributionNotFound'):
                    matches = [u'setup.py']
                    break
                elif line.startswith(u'File'):
                    fn = line.split()[1]
                    for SC in STOPCHARS:
                        fn = fn.replace(SC, u'')
                    if u'ansible_module_' in fn:
                        fn = os.path.basename(fn)
                        fn = fn.replace(u'ansible_module_', u'')
                        matches = [fn]
                    elif u'cli/playbook.py' in fn:
                        fn = u'lib/ansible/cli/playbook.py'
                    elif u'module_utils' in fn:
                        idx = fn.find(u'module_utils/')
                        fn = u'lib/ansible/' + fn[idx:]
                    elif u'ansible/' in fn:
                        idx = fn.find(u'ansible/')
                        fn1 = fn[idx:]

                        if u'bin/' in fn1:
                            if not fn1.startswith(u'bin'):

                                idx = fn1.find(u'bin/')
                                fn1 = fn1[idx:]

                                if fn1.endswith(u'.py'):
                                    fn1 = fn1.rstrip(u'.py')

                        elif u'cli/' in fn1:
                            idx = fn1.find(u'cli/')
                            fn1 = fn1[idx:]
                            fn1 = u'lib/ansible/' + fn1

                        elif u'lib' not in fn1:
                            fn1 = u'lib/' + fn1

                        if fn1 not in self.files:
                            if C.DEFAULT_BREAKPOINTS:
                                logging.error(u'breakpoint!')
                                import epdb; epdb.st()
            if matches:
                return matches

        craws = template_data.get(u'component_raw')
        if craws is None:
            return matches

        # compare to component mapping
        matches = self._string_to_cmap_key(craws)
        if matches:
            return matches

        # do not re-process the same strings over and over again
        if craws.lower() in self.match_cache:
            return self.match_cache[craws.lower()]

        # make ngrams from largest to smallest and recheck
        blob = TextBlob(craws.lower())
        wordcount = len(blob.tokens) + 1

        for ng_size in reversed(xrange(2, wordcount)):
            ngrams = [u' '.join(x) for x in blob.ngrams(ng_size)]
            for ng in ngrams:

                matches = self._string_to_cmap_key(ng)
                if matches:
                    self.match_cache[craws.lower()] = matches
                    return matches

        # https://pypi.python.org/pypi/fuzzywuzzy
        matches = []
        for cr in craws.lower().split(u'\n'):
            ratios = []
            for k in self.CMAP.keys():
                ratio = fw_fuzz.ratio(cr, k)
                ratios.append((ratio, k))
            ratios = sorted(ratios, key=lambda tup: tup[0])
            if ratios[-1][0] >= 90:
                cnames = self.CMAP[ratios[-1][1]]
                matches += cnames
        if matches:
            self.match_cache[craws.lower()] = matches
            return matches

        # try to match to repo files
        if craws:
            clines = craws.split(u'\n')
            for craw in clines:
                cparts = craw.replace(u'-', u' ')
                cparts = cparts.split()

                for idx, x in enumerate(cparts):
                    for SC in STOPCHARS:
                        if SC in x:
                            x = x.replace(SC, u'')
                    for SW in STOPWORDS:
                        if x == SW:
                            x = u''
                    if x and u'/' not in x:
                        x = u'/' + x
                    cparts[idx] = x

                cparts = [x.strip() for x in cparts if x.strip()]

                for x in cparts:
                    for f in self.files:
                        if u'/modules/' in f:
                            continue
                        if u'test/' in f and u'test' not in craw:
                            continue
                        if u'galaxy' in f and u'galaxy' not in body:
                            continue
                        if u'dynamic inv' in body.lower() and u'contrib' not in f:
                            continue
                        if u'inventory' in f and u'inventory' not in body.lower():
                            continue
                        if u'contrib' in f and u'inventory' not in body.lower():
                            continue

                        try:
                            f.endswith(x)
                        except UnicodeDecodeError:
                            continue

                        fname = os.path.basename(f).split(u'.')[0]

                        if f.endswith(x):
                            if fname.lower() in body.lower():
                                matches.append(f)
                                break
                        if f.endswith(x + u'.py'):
                            if fname.lower() in body.lower():
                                matches.append(f)
                                break
                        if f.endswith(x + u'.ps1'):
                            if fname.lower() in body.lower():
                                matches.append(f)
                                break
                        if os.path.dirname(f).endswith(x):
                            if fname.lower() in body.lower():
                                matches.append(f)
                                break

        logging.info(u'%s --> %s' % (craws, sorted(set(matches))))
        self.match_cache[craws.lower()] = matches
        return matches

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

    def get_filemap_users_for_files(self, files):
        '''Get expected notifiees from the filemap'''
        to_notify = []
        to_assign = []

        exclusive = False
        for f in files:

            if f is None:
                continue

            # only one match
            if exclusive:
                continue

            for k, v in six.iteritems(self.FILEMAP):
                if not v[u'inclusive'] and v[u'regex'].match(f):
                    to_notify = v[u'notify']
                    to_assign = v[u'assign']
                    exclusive = True
                    break

                if u'notify' not in v and u'assign' not in v:
                    continue

                if v[u'regex'].match(f):
                    for user in v[u'notify']:
                        if user not in to_notify:
                            to_notify.append(user)
                    for user in v[u'assign']:
                        if user not in to_assign:
                            to_assign.append(user)

        return to_notify, to_assign

    def isnewdir(self, path):
        if path in self.files:
            return False
        else:
            return True

    def commits_by_email(self, email):
        if not isinstance(email, (list, tuple)):
            email = [email]

        if not self.email_commits:
            cmd = u'cd {}; git log --format="%H %ae"'.format(self.gitrepo.checkoutdir)
            (rc, so, se) = run_command(cmd)
            commits = [x.split(None, 1)[::-1] for x in to_text(so).split(u'\n') if x]
            for x in commits:
                if x[0] not in self.email_commits:
                    self.email_commits[x[0]] = []
                self.email_commits[x[0]].append(x[1])

        commits = []
        for x in email:
            commits += self.email_commits.get(x, [])

        return commits
