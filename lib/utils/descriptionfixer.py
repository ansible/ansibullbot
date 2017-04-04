#!/usr/bin/env python

import os
from lib.utils.webscraper import GithubWebScraper

ISSUE_TYPES = {'bug_report': 'Bug Report',
               'feature_idea': 'Feature Idea',
               'docs_report': 'Documentation Report'}

TBASE = '.github/'
ITEMPLATE = TBASE + 'ISSUE_TEMPLATE.md'
PTEMPLATE = TBASE + 'PULL_REQUEST_TEMPLATE.md'


class DescriptionFixer(object):
    def __init__(self, issuewrapper, meta):

        self.issuewrapper = issuewrapper
        self.original = self.issuewrapper.instance.body
        self.meta = meta
        self.missing = []
        self.sections = {}
        self.section_map = {}
        self.section_order = []
        self.new_description = ''
        self.retemplate = True

        self.cachedir = '~/.ansibullbot/cache'
        self.cachedir = os.path.expanduser(self.cachedir)
        self.gws = GithubWebScraper(cachedir=self.cachedir)

        if self.issuewrapper.github_type == 'pullrequest':
            rfile = PTEMPLATE
        else:
            rfile = ITEMPLATE
        raw = self.gws.get_raw_content(
            'ansible', 'ansible', 'devel', rfile, usecache=True
        )
        rlines = raw.split('\n')
        for rline in rlines:
            if not rline.startswith('#####'):
                continue
            section = rline.strip().split(None, 1)[1]
            section = section.lower()
            self.section_order.append(section)
            self.sections[section] = ''

        if self.section_order[0] not in ['issue type', 'summary']:
            import epdb; epdb.st()

        self.process()
        self.create_body()

    def process(self):

        for k,v in self.issuewrapper.template_data.items():
            if k in ['component raw', 'component_raw']:
                continue

            # use consistent key
            if k == 'environment':
                k = 'os / environment'

            # cleanup duble newlines
            if v:
                v = v.replace('\n\n', '\n')

            if k == 'ansible version':
                self.sections[k] = '```\n' + v + '\n```'
            else:
                self.sections[k] = v

            if k not in self.section_order:
                self.section_order.append(k)

        # what is missing?
        missing = [x for x in self.section_order]
        missing = [x for x in missing if not self.sections.get(x)]
        missing = [x for x in missing if x != 'additional information']
        self.missing = missing

        # inject section(s) versus recreating the whole body
        if len(missing) < 2:
            self.section_map = {}
            dlines = self.original.split('\n')
            for section in self.section_order:
                for idx,x in enumerate(dlines):
                    if x.startswith('##### %s' % section.upper()):
                        self.section_map[section] = idx
            if self.section_map:
                self.retemplate = False
                return None

        # set summary
        summary = self.sections.get('summary')
        if not summary:
            if self.original:
                if not self.issuewrapper.template_data.keys():
                    self.sections['summary'] = self.original
                else:
                    self.sections['summary'] = self.issuewrapper.title
                    #import epdb; epdb.st()
            else:
                self.sections['summary'] = self.issuewrapper.title

        # set issue type
        if not self.sections.get('issue type'):
            labeled = False
            for k,v in ISSUE_TYPES.iteritems():
                if k in self.issuewrapper.labels:
                    self.sections['issue type'] = v
                    labeled = True
            if not labeled:
                if self.issuewrapper.github_type == 'issue':
                    self.sections['issue type'] = 'bug report'
                else:
                    self.sections['issue type'] = 'feature pull request'

        # set component name
        if not self.sections.get('component name'):
            if not self.meta['is_module']:
                if self.issuewrapper.github_type == 'pullrequest':
                    self.sections['component name'] = \
                        '\n'.join(self.issuewrapper.files)
                else:
                    #import epdb; epdb.st()
                    self.sections['component name'] = 'core'
            else:
                self.sections['component name'] = \
                    self.meta['module_match']['name'] + ' module'

        # set ansible version
        if not self.sections.get('ansible version'):
            vlabels = [x for x in self.issuewrapper.labels
                       if x.startswith('affects_')]
            vlabels = sorted(set(vlabels))
            if vlabels:
                version = vlabels[0].split('_')[1]
                self.sections['ansible version'] = version
            elif self.meta['ansible_version']:
                self.sections['ansible version'] = self.meta['ansible_version']
            else:
                self.sections['ansible version'] = 'N/A'

    def create_body(self):

        if self.retemplate:
            # render to text
            for section in self.section_order:
                data = self.sections.get(section)
                if data is None:
                    data = ''
                self.new_description += '##### ' + section.upper() + '\n'
                if section == 'issue type':
                    self.new_description += data.title()
                    self.new_description += '\n'
                else:
                    self.new_description += data + '\n'
                self.new_description += '\n'
        else:
            dlines = self.original.split('\n')
            for msection in self.missing:
                midx = self.section_order.index(msection)
                post_section = self.section_order[midx + 1]

                if post_section not in self.section_map:
                    import epdb; epdb.st()

                post_line = self.section_map[post_section]

                new_section = ['##### %s' % msection.upper()]
                if msection == 'component name':
                    if not self.meta['is_module']:
                        if self.issuewrapper.github_type == 'pullrequest':
                            new_section += self.issuewrapper.files
                        else:
                            new_section.append('core')
                    else:
                        new_section.append(
                            self.meta['module_match']['name'] + ' module'
                        )
                new_section.append('')

                #import epdb; epdb.st()
                for x in reversed(new_section):
                    dlines.insert(post_line, x)

            #import epdb; epdb.st()
            self.new_description = '\n'.join(dlines)
