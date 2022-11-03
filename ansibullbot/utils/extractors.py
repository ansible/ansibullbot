import logging
import operator
import os
import re

import yaml

import ansibullbot.constants as C
from ansibullbot._text_compat import to_bytes, to_text


_SECTIONS = [
    'issue type',
    'component name',
    'plugin name',
    'ansible version',
    'ansible configuration',
    'configuration',
    'os / environment',
    'summary',
    'environment',
    'steps to reproduce',
    'expected results',
    'actual results',
    'additional information',
]


def _find_sections(body):
    # find possible sections by the default pattern
    tofind = re.findall(r'(#{3,5}\W*.*)[\r\n]*', body)
    if len(tofind) <= 1:
        return

    # map out the starting index for each section
    match_map = {}
    for tf in tofind:
        match_map[tf] = body.index(tf)

    # sort by index so we can read from one section to the next
    match_map = sorted(match_map.items(), key=operator.itemgetter(1))

    # extract each section from the body up to the next section
    rv = {}
    for idx, (section, position) in enumerate(match_map):
        try:
            tail = match_map[idx + 1][1]
        except IndexError:
            tail = len(body)
        rv[section.lower().strip('# \n\r')] = body[position:tail].replace(section, '').strip('# \n\r')

    return rv


def _extract_template_data(body, issue_class='issue'):
    if not body:
        return {}

    template_data = _find_sections(body)
    if not template_data:
        return {}

    # make a raw component section for later processing
    component_raw = template_data.get('component name', '')

    for delimiter in (',', ' and '):
        if delimiter in template_data.get('component name', ''):
            template_data['component name'] = template_data['component name'].replace(delimiter, '\n')

    # cleanup the sections
    for section, section_data in template_data.items():
        # remove markdown comments from the sections
        section_data = _remove_markdown_comments(section_data)

        # remove non-ascii chars
        section_data = to_text(to_bytes(section_data, 'ascii', errors='ignore'), 'ascii')

        # normalize newlines and return chars
        section_data = section_data.replace('\r', '\n')

        # remove pre-ceding and trailing newlines
        section_data = section_data.strip()

        # remove trailing hashes
        section_data = section_data.rstrip('#')

        # remove pre-ceding and trailing newlines (AGAIN)
        section_data = section_data.strip()

        # clean more on critical sections
        if 'step' not in section and 'result' not in section:
            # https://github.com/ansible/ansible-modules-extras/issues/2262
            if section == 'component name':
                section_data = section_data.lower()

            if section == 'component name' and 'module' in section_data:
                if '/modules/' in section_data or \
                        'module_util' in section_data or \
                        'module_utils/' in section_data or \
                        'validate-modules' in section_data or\
                        'module_common' in section_data:
                    # https://github.com/ansible/ansible/issues/20563
                    # https://github.com/ansible/ansible/issues/18179
                    pass
                else:
                    # some modules have the word "_module" in their name
                    # https://github.com/ansible/ansibullbot/issues/198
                    # https://github.com/ansible/ansible-modules-core/issues/4159
                    # https://github.com/ansible/ansible-modules-core/issues/5328
                    reg = re.compile(r'\S+_module')
                    match = reg.match(section_data)
                    if match:
                        section_data = section_data[match.pos:match.end()]
                    else:
                        # https://github.com/ansible/ansibullbot/issues/385
                        if 'modules' in section_data:
                            section_data = section_data.replace('modules', ' ')
                        else:
                            section_data = section_data.replace('module', ' ')

            # remove useless chars
            exclude = None
            if section == 'component name':
                exclude = ['__']
            section_data = _clean_bad_characters(section_data, exclude=exclude)

            # clean up empty lines
            section_data = '\n'.join([x.strip() for x in section_data.split('\n') if x.strip()])

            # remove pre-ceding special chars
            for bc in ['-', '*']:
                if section_data:
                    if section_data[0] == bc:
                        section_data = section_data[1:]
                    section_data = section_data.strip()

            # keep just the first line for types and components
            if section in ['issue type', 'component name']:
                if section_data:
                    # https://github.com/ansible/ansible-modules-core/issues/3085
                    section_data = [x for x in section_data.split('\n') if 'pick one' not in x][0]

            # https://github.com/ansible/ansible-modules-core/issues/4060
            if section == 'issue type':
                if '/' in section_data:
                    section_data = section_data.split('/')
                    if section == ['issue type']:
                        section_data = section_data[0]
                    else:
                        section_data = section_data[-1]
                    section_data = section_data.strip()

            if section == 'issue type':
                if issue_class == 'issue':
                    if section_data != 'bug report' and 'bug' in section_data.lower():
                        section_data = 'bug report'
                    elif section_data != 'feature idea' and 'feature' in section_data.lower():
                        section_data = 'feature idea'
                elif issue_class == 'pullrequest':
                    if section_data != 'bugfix pull request' and 'bug' in section_data.lower():
                        section_data = 'bugfix pull request'
                    elif section_data != 'feature pull request' and 'feature' in section_data.lower():
                        section_data = 'feature pull request'
                    elif section_data != 'new module pull request' and 'new module' in section_data.lower():
                        section_data = 'new module pull request'
                    elif section_data != 'docs pull request' and 'docs' in section_data.lower():
                        section_data = 'docs pull request'
                    elif section_data != 'test pull request' and 'test' in section_data.lower():
                        section_data = 'test pull request'

        if section_data == 'paste below':
            section_data = ''

        # save
        template_data[section] = section_data

    # quick clean and add raw component to the dict
    component_raw = _remove_markdown_comments(_clean_bad_characters(component_raw, exclude=['__']))
    component_raw = '\n'.join([x.strip() for x in component_raw.split('\n') if x.strip()])
    component_raw = '\n'.join([x for x in component_raw.split('\n') if not x.startswith('#')])
    template_data['component_raw'] = component_raw

    return template_data


def _clean_bad_characters(raw_text, exclude=None):
    badchars = ['#', ':', ';', ',', '*', '"', "'", '`', '---', '__']

    if exclude is None:
        exclude = []

    # Exclude patterns of word, word,word
    if re.search(r'(\w+,\s?)+\w+', raw_text):
        exclude.extend(',')

    # Exclude contractions like It's
    if re.search(r"\w+'\w", raw_text):
        exclude.extend("'")

    # Don't remove characters passed in as an exclusion
    if exclude:
        if isinstance(exclude, list):
            badchars = [x for x in badchars if x not in exclude]
        elif exclude:
            badchars = [x for x in badchars if x != exclude]

    for bc in badchars:
        raw_text = raw_text.replace(bc, '')

    return raw_text


def _remove_markdown_comments(rawtext):
    # Get rid of the comment blocks from the markdown template
    # <!--- ---> OR <!-- -->
    return re.sub(r'<!(-{2,3})[\s\S]*?\1>', r'', rawtext)


def extract_pr_number_from_comment(rawtext):
    # "resolved_by_pr 5136" --> 5136
    # "resolved_by_pr #5136" --> 5136
    # "resolved_by_pr https://github.com/ansible/ansible/issues/5136" --> 5136
    # "resolved_by_pr #5319." --> 5319
    # "resolved_by_pr: 61430" --> 61430
    matches = [int(x) for x in re.findall(r'\d+', rawtext)]
    if matches:
        return matches[0]
    return None


class ModuleExtractor:

    _AUTHORS = None
    _DOCUMENTATION_RAW = None
    _FILEDATA = None
    _DOCSTRING = None

    def __init__(self, filepath, filedata=None, email_cache=None):
        self.filepath = filepath
        self._FILEDATA = filedata
        self.email_cache = email_cache or {}

    @property
    def filedata(self):
        if self._FILEDATA is None:
            try:
                with open(self.filepath, 'rb') as f:
                    self._FILEDATA = f.read()
            except OSError:
                return b''
        return self._FILEDATA

    @property
    def authors(self):
        if self._AUTHORS is None:
            self._AUTHORS = self.get_module_authors()
        return self._AUTHORS

    @property
    def docs(self):
        if self._DOCSTRING is not None:
            return self._DOCSTRING

        documentation = ''
        inphase = False
        lines = to_text(self.filedata).split('\n')
        for line in lines:
            if 'DOCUMENTATION' in line:
                inphase = True
                continue
            if inphase and (line.strip().endswith(("'''", '"""'))):
                break
            if inphase:
                documentation += line + '\n'

        self._DOCUMENTATION_RAW = documentation

        # some docstrings don't pass yaml validation with PyYAML >= 4.2
        try:
            self._DOCSTRING = yaml.safe_load(self._DOCUMENTATION_RAW)
        except yaml.parser.ParserError:
            logging.warning('%s has non-yaml formatted docstrings' % self.filepath)
        except yaml.scanner.ScannerError:
            logging.warning('%s has non-yaml formatted docstrings' % self.filepath)

        # always cast to a dict for easier handling later
        if self._DOCSTRING is None:
            self._DOCSTRING = {}

        return self._DOCSTRING

    def get_module_authors(self):
        """Grep the authors out of the module docstrings"""
        # 2019-02-15
        if 'author' in self.docs or 'authors' in self.docs:
            _authors = self.docs.get('author') or self.docs.get('authors')
            if _authors is None:
                return []
            if not isinstance(_authors, list):
                _authors = [_authors]
            logins = set()
            for author in _authors:
                _logins = self.extract_github_id(author)
                if _logins:
                    logins = logins.union(_logins)
            return list(logins)

        return []

    def extract_github_id(self, author):
        """Extract a set of github login(s) from a string."""
        # safegaurd against exceptions
        if author is None:
            return []

        authors = set()

        if 'ansible core team' in author.lower():
            authors.add('ansible')
        elif '@' in author:
            # match github ids but not emails
            authors.update(re.findall(r'(?<!\w)@([\w-]+)(?![\w.])', author))
        elif 'github.com/' in author:
            # {'author': 'Henrique Rodrigues (github.com/Sodki)'}
            idx = author.find('github.com/')
            author = author[idx+11:]
            authors.add(author.replace(')', ''))
        elif '(' in author and len(author.split()) == 3:
            # Mathieu Bultel (matbu)
            idx = author.find('(')
            author = author[idx+1:]
            authors.add(author.replace(')', ''))

        # search for emails
        for email in re.findall(r'[<(]([^@]+@[^)>]+)[)>]', author):
            github_id = self.email_cache.get(email)
            if github_id:
                authors.add(github_id)

        return list(authors)


def get_template_data(iw):
    """Extract templated data from an issue body"""
    sections = set()
    template_dir_name = '.github/ISSUE_TEMPLATE/'
    for template_file_name in ('bug_report.yml', 'feature_request.yml', 'documentation_report.yml'):
        parsed_content = yaml.safe_load(
            iw.gitrepo.get_file_content(os.path.join(template_dir_name, template_file_name))
        )
        for el in parsed_content.get('body', []):
            section = el.get('attributes', {}).get('label', '').lower()
            if section:
                sections.add(section)

    tf_sections = list(sections.union(_SECTIONS))

    template_data = _extract_template_data(
        iw.instance.body,
        issue_class=iw.github_type,
    )

    # try comments if the description was insufficient
    if len(template_data.keys()) <= 2:
        s_comments = iw.history.get_user_comments(iw.submitter)
        for s_comment in s_comments:
            _template_data = _extract_template_data(
                s_comment,
                issue_class=iw.github_type,
            )

            if _template_data:
                for k, v in _template_data.items():
                    if not v:
                        continue
                    if k not in template_data or not template_data.get(k):
                        template_data[k] = v

    if 'ANSIBLE VERSION' in tf_sections and 'ansible version' not in template_data:
        versions = [
            float(x['label'].split('_')[1])
            for x in iw.history.history
            if x['event'] == 'labeled'
            and x['actor'] not in C.DEFAULT_BOT_NAMES
            and x['label'].startswith('affects_')
        ]

        if versions:
            template_data['ansible version'] = to_text(versions[-1])

    if 'COMPONENT NAME' in tf_sections and 'component name' not in template_data:
        if iw.is_pullrequest():
            if iw.files:
                template_data['component name'] = template_data['component_raw'] = '\n'.join(iw.files)
        else:
            clabels = ['lib/ansible/' + x.replace('c:', '') for x in iw.labels if x.startswith('c:')]
            if clabels:
                template_data['component name'] = template_data['component_raw'] = '\n'.join(clabels)
            elif 'documentation' in template_data.get('issue type', '').lower():
                template_data['component name'] = template_data['component_raw'] = 'docs'

    if 'ISSUE TYPE' in tf_sections and 'issue type' not in template_data:
        itype = None
        for label in iw.labels:
            if label.startswith('bug'):
                itype = 'bug'
                break
            if label.startswith('feature'):
                itype = 'feature'
                break
            if label.startswith('doc'):
                itype = 'docs'
                break

        if not itype and iw.is_pullrequest():
            for fn in iw.files:
                if fn.startswith('doc'):
                    itype = 'docs'
                    break

        if itype == 'bug':
            template_data['issue type'] = 'bug report' if iw.is_issue() else 'bugfix pullrequest'
        elif itype == 'feature':
            template_data['issue type'] = 'feature idea' if iw.is_issue() else 'feature pullrequest'
        elif itype == 'docs':
            template_data['issue type'] = 'documentation report' if iw.is_issue() else 'documenation pullrequest'

    return template_data
