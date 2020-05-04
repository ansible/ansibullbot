#!/usr/bin/env python

import logging
import os

import six

from ansibullbot.utils.webscraper import GithubWebScraper

import ansibullbot.constants as C

ISSUE_TYPES = {u'bug_report': u'Bug Report',
               u'feature_idea': u'Feature Idea',
               u'docs_report': u'Documentation Report'}

TBASE = u'.github/'
ITEMPLATE = TBASE + u'ISSUE_TEMPLATE.md'  # FIXME this file does not exist anymore
PTEMPLATE = TBASE + u'PULL_REQUEST_TEMPLATE.md'


class DescriptionFixer(object):
    def __init__(self, issuewrapper, meta):

        self.issuewrapper = issuewrapper
        self.original = self.issuewrapper.instance.body
        self.meta = meta
        self.missing = []
        self.sections = {}
        self.section_map = {}
        self.section_order = []
        self.new_description = u''
        self.retemplate = True

        self.cachedir = u'~/.ansibullbot/cache'
        self.cachedir = os.path.expanduser(self.cachedir)
        self.gws = GithubWebScraper(cachedir=self.cachedir)

        if self.issuewrapper.github_type == u'pullrequest':
            rfile = PTEMPLATE
        else:
            rfile = ITEMPLATE
        raw = self.gws.get_raw_content(
            u'ansible', u'ansible', u'devel', rfile, usecache=True
        )
        rlines = raw.split(u'\n')
        for rline in rlines:
            if not rline.startswith(u'#####'):
                continue
            section = rline.strip().split(None, 1)[1]
            section = section.lower()
            self.section_order.append(section)
            self.sections[section] = u''

        if self.section_order[0] not in [u'issue type', u'summary']:
            if C.DEFAULT_BREAKPOINTS:
                logging.error(u'breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception(u'out of order section')

        self.process()
        self.create_body()

    def process(self):

        for k, v in self.issuewrapper.template_data.items():
            if k in [u'component raw', u'component_raw']:
                continue

            # use consistent key
            if k == u'environment':
                k = u'os / environment'

            # use consistent key
            if k == u'ansible configuration':
                k = u'configuration'

            # cleanup duble newlines
            if v:
                v = v.replace(u'\n\n', u'\n')

            if k == u'ansible version':
                self.sections[k] = u'```\n' + v + u'\n```'
            else:
                self.sections[k] = v

            if k not in self.section_order:
                self.section_order.append(k)

        # what is missing?
        missing = [x for x in self.section_order]
        missing = [x for x in missing if not self.sections.get(x)]
        missing = [x for x in missing if x != u'additional information']
        self.missing = missing

        # inject section(s) versus recreating the whole body
        if len(missing) < 2:
            self.section_map = {}
            dlines = self.original.split(u'\n')
            for section in self.section_order:
                for idx, x in enumerate(dlines):
                    if x.startswith(u'##### %s' % section.upper()):
                        self.section_map[section] = idx
            if self.section_map:
                self.retemplate = False
                return None

        # set summary
        summary = self.sections.get(u'summary')
        if not summary:
            if self.original:
                if not self.issuewrapper.template_data.keys():
                    self.sections[u'summary'] = self.original
                else:
                    self.sections[u'summary'] = self.issuewrapper.title
            else:
                self.sections[u'summary'] = self.issuewrapper.title

        # set issue type
        if not self.sections.get(u'issue type'):
            labeled = False
            for k, v in six.iteritems(ISSUE_TYPES):
                if k in self.issuewrapper.labels:
                    self.sections[u'issue type'] = v
                    labeled = True
            if not labeled:
                if self.issuewrapper.github_type == u'issue':
                    self.sections[u'issue type'] = u'bug report'
                else:
                    self.sections[u'issue type'] = u'feature pull request'

        # set component name
        if not self.sections.get(u'component name'):
            if not self.meta[u'is_module']:
                if self.issuewrapper.github_type == u'pullrequest':
                    self.sections[u'component name'] = \
                        u'\n'.join(self.issuewrapper.files)
                else:
                    self.sections[u'component name'] = u'core'
            else:
                self.sections[u'component name'] = \
                    self.meta[u'module_match'][u'name'] + u' module'

        # set ansible version
        if not self.sections.get(u'ansible version'):
            vlabels = [x for x in self.issuewrapper.labels
                       if x.startswith(u'affects_')]
            vlabels = sorted(set(vlabels))
            if vlabels:
                version = vlabels[0].split(u'_')[1]
                self.sections[u'ansible version'] = version
            elif self.meta[u'ansible_version']:
                self.sections[u'ansible version'] = self.meta[u'ansible_version']
            else:
                self.sections[u'ansible version'] = u'N/A'

    def create_body(self):

        # cleanup remnant colons
        for k, v in six.iteritems(self.sections):
            if v.startswith(u':\n'):
                self.sections[k] = v[2:]
            elif v.startswith(u': \n'):
                self.sections[k] = v[3:]
            elif v.startswith(u':'):
                self.sections[k] = v[1:]

        if self.retemplate:
            # render to text
            for section in self.section_order:
                data = self.sections.get(section)
                if data is None:
                    data = u''
                self.new_description += u'##### ' + section.upper() + u'\n'
                if section == u'issue type':
                    self.new_description += data.title()
                    self.new_description += u'\n'
                else:
                    self.new_description += data + u'\n'
                self.new_description += u'\n'
        else:
            dlines = self.original.split(u'\n')
            for msection in self.missing:
                midx = self.section_order.index(msection)
                post_section = self.section_order[midx + 1]

                if post_section not in self.section_map:
                    if C.DEFAULT_BREAKPOINTS:
                        logging.error(u'breakpoint!')
                        import epdb; epdb.st()
                    else:
                        raise Exception(u'section not in map')

                post_line = self.section_map[post_section]

                new_section = [u'##### %s' % msection.upper()]
                if msection == u'component name':
                    if not self.meta[u'is_module']:
                        if self.issuewrapper.github_type == u'pullrequest':
                            new_section += self.issuewrapper.files
                        else:
                            new_section.append(u'core')
                    else:
                        new_section.append(
                            self.meta[u'module_match'][u'name'] + u' module'
                        )
                new_section.append(u'')

                for x in reversed(new_section):
                    dlines.insert(post_line, x)

            self.new_description = u'\n'.join(dlines)
