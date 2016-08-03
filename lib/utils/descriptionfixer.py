#!/usr/bin/env python

ISSUE_TYPES = {'bug_report': 'Bug Report',
               'feature_idea': 'Feature Idea',
               'docs_report': 'Documentation Report'}

SECTIONS = ['issue type', 'component name', 'ansible version', 'summary']

class DescriptionFixer(object):
    def __init__(self, issuewrapper, moduleindexer, match):
        self.issuewrapper = issuewrapper
        self.moduleindexer = moduleindexer
        self.match = match
        self.sections = {}
        self.original = None
        self.new_description = ''
        self.process()

    def process(self):
        self.original = self.issuewrapper.instance.body
        self.sections = self.issuewrapper.template_data        

        lines = self.original.lower().split('\n')

        # pre-populate
        for section in SECTIONS:
            if not section in self.sections:
                self.sections[section] = ''

        # set summary
        if not self.sections['summary']:
            self.sections['summary'] = self.original

        # set issue type
        if not self.sections['issue type']:
            for k,v in ISSUE_TYPES.iteritems():
                if k in self.issuewrapper.current_labels:
                    self.sections['issue type'] = v            

        # set component name
        if not self.sections['component name']:
            if self.match:
                self.sections['component name'] = self.match['name'] + ' module'

        # set ansible version
        if not self.sections['ansible version']:
            matches = [x for x in lines if 'ansible' in x and 'version' in x and '.' in x]
            if matches:
                self.sections['ansible version'] = matches[0]
            else:
                for idx,x in enumerate(lines):
                    if 'ansible --version' in x:
                        self.sections['ansible version'] = lines[idx + 1].strip()
                        break
                        #import epdb; epdb.st()

            if not self.sections['ansible version']:
                self.sections['ansible version'] = 'N/A'

        # render to text                
        for section in SECTIONS:
            self.new_description += '##### ' + section.upper() + '\n'
            self.new_description += self.sections[section] + '\n'
            self.new_description += '\n'
        
        #import epdb; epdb.st()



