import logging
import operator
import re
from string import Template

import yaml

import ansibullbot.constants as C
from ansibullbot._text_compat import to_bytes, to_text


SECTIONS = ['ISSUE TYPE', 'COMPONENT NAME', 'PLUGIN NAME',
            'ANSIBLE VERSION', 'ANSIBLE CONFIGURATION', 'CONFIGURATION',
            'OS / ENVIRONMENT', 'SUMMARY', 'ENVIRONMENT',
            'STEPS TO REPRODUCE', 'EXPECTED RESULTS',
            'ACTUAL RESULTS', 'ADDITIONAL INFORMATION']

TEMPLATE_HEADER = '#####'


def extract_template_sections(body, header=TEMPLATE_HEADER):
    ''' Get the section names from a .github/*.md file in a repo'''

    sections = {}
    lines = body.split('\n')
    current_section = None
    index = 0
    for line in lines:
        if line.startswith(header):
            section = line.replace(header, '', 1)
            section = section.strip()
            sections[section] = {'required': False, 'index': index}
            index += 1
            current_section = section

        elif line.startswith('<!--') and current_section:
            if 'required: True' in line:
                sections[current_section]['required'] = True

    return sections


def fuzzy_find_sections(body, sections):
    upper_body = body.upper()

    # make a map of locations where each section starts
    match_map = {}
    for section in sections:
        # http://www.tutorialspoint.com/python/string_find.htm
        # str.find(str, beg=0 end=len(string))
        match = upper_body.find(section)
        if match != -1:
            match_map[section] = match

    if not match_map:
        return {}

    # what are the header(s) being used?
    headers = []
    for k, v in match_map.items():
        try:
            before = upper_body[v-1]
            after = upper_body[v + len(k)]
            header = before + '${section}' + after
            headers.append(header)
        except Exception:
            pass

    # pick the most common header and re-search with it
    if len(sorted(set(headers))) > 1:
        choices = sorted(set(headers))
        choice_totals = []
        for choice in choices:
            ctotal = len([x for x in headers if x == choice])
            choice_totals.append((ctotal, choice))
        choice_totals.sort(key=lambda tup: tup[0])
        sheader = choice_totals[-1][1]

        match_map = {}
        t = Template(sheader)
        for section in sections:
            try:
                tofind = t.substitute(section=section)
            except Exception as e:
                raise Exception('substitution failed: %s' % to_text(e))
            match = upper_body.find(tofind)
            if match != -1:
                match_map[section] = match + 1

        # re-do for missing sections with less common header(s)
        for section in sections:
            if section in match_map:
                continue
            for choice in choices:
                t = Template(choice)
                tofind = t.substitute(section=section)
                match = upper_body.find(tofind)
                if match != -1:
                    match_map[section] = match + 1
                    break

    elif len(headers) <= 1:
        if headers and \
                ('#' not in headers[0] and
                 ':' not in headers[0] and
                 '*' not in headers[0]):
            return {}

    # sort mapping by element id and inject itype if needed
    match_map = sorted(match_map.items(), key=operator.itemgetter(1))
    if match_map and 'ISSUE TYPE' not in [x[0] for x in match_map]:
        if match_map[0][1] > 10:
            match_map.insert(0, ('ISSUE TYPE', 0))

    # extract the sections based on their indexes
    tdict = {}
    total_indexes = len(match_map) - 1
    for idx, x in enumerate(match_map):

        if x[1] > 0:
            start_index = x[1] + (len(x[0]))
        else:
            start_index = 0

        # if last index, slice to the end
        if idx >= total_indexes:
            tdict[x[0]] = body[start_index:]
        else:
            # slice to the next section
            stop_index = match_map[idx+1][1]
            tdict[x[0]] = body[start_index:stop_index]

    return tdict


def find_sections(body):
    # find possible sections by the default pattern
    tofind = sorted(set(re.findall(r'##### [\/A-Z\s]+\r\n', body)))

    if len(tofind) <= 1:
        return None

    # map out the starting index for each section
    match_map = {}
    for tf in tofind:
        match_map[tf] = body.index(tf)

    # sort by index so we can read from one section to the next
    match_map = sorted(match_map.items(), key=lambda x: x[1])

    # extract each section from the body up to the next section
    tdict = {}
    for idm, mm in enumerate(match_map):
        try:
            tail = match_map[idm+1][1]
        except IndexError:
            tail = len(body)
        content = body[mm[1]:tail]
        content = content.replace(mm[0], '')
        key = mm[0].replace('#', '').strip()
        tdict[key] = content

    return tdict


def extract_template_data(body, issue_class='issue', sections=None):
    if sections is None:
        sections = SECTIONS

    # pointless to parse a null body
    if not body:
        return {}

    # simple find or fuzzy find the sections within the body
    tdict = find_sections(body) or fuzzy_find_sections(body, sections)
    if not tdict:
        return {}

    # lowercase the keys
    ndict = {}
    for k, v in tdict.items():
        ku = k.lower()
        if ku == 'plugin name':
            ku = 'component name'
        ndict[ku] = v
    if ndict != tdict:
        tdict = ndict.copy()

    # make a raw component section for later processing
    component_raw = tdict.get('component name', '')

    # https://github.com/ansible/ansibullbot/issues/359
    if ',' in tdict.get('component name', ''):
        tdict['component name'] = tdict['component name'].replace(',', '\n')

    # https://github.com/ansible/ansibullbot/issues/385
    if ' and ' in tdict.get('component name', ''):
        tdict['component name'] = tdict['component name'].replace(' and ', '\n')

    # cleanup the sections
    for k, v in tdict.items():
        # remove markdown comments from the sections
        v = remove_markdown_comments(v)

        # remove non-ascii chars
        v = to_text(to_bytes(v, 'ascii', errors='ignore'), 'ascii')

        # normalize newlines and return chars
        v = v.replace('\r', '\n')

        # remove pre-ceding and trailing newlines
        v = v.strip()

        # remove trailing hashes
        while v.endswith('#'):
            v = v[:-1]

        # remove pre-ceding and trailing newlines (AGAIN)
        v = v.strip()

        # clean more on critical sections
        if 'step' not in k and 'result' not in k:

            # https://github.com/ansible/ansible-modules-extras/issues/2262
            if k == 'component name':
                v = v.lower()

            if k == 'component name' and 'module' in v:
                if '/modules/' in v or \
                        'module_util' in v or \
                        'module_utils/' in v or \
                        'validate-modules' in v or\
                        'module_common' in v:
                    # https://github.com/ansible/ansible/issues/20563
                    # https://github.com/ansible/ansible/issues/18179
                    pass
                else:
                    # some modules have the word "_module" in their name
                    # https://github.com/ansible/ansibullbot/issues/198
                    # https://github.com/ansible/ansible-modules-core/issues/4159
                    # https://github.com/ansible/ansible-modules-core/issues/5328
                    reg = re.compile(r'\S+_module')
                    match = reg.match(v)
                    if match:
                        v = v[match.pos:match.end()]
                    else:
                        # https://github.com/ansible/ansibullbot/issues/385
                        if 'modules' in v:
                            v = v.replace('modules', ' ')
                        else:
                            v = v.replace('module', ' ')

            # remove useless chars
            exclude = None
            if k == 'component name':
                exclude = ['__']
            v = clean_bad_characters(v, exclude=exclude)

            # clean up empty lines
            vlines = v.split('\n')
            vlines = [x for x in vlines if x.strip()]
            vlines = [x.strip() for x in vlines if x.strip()]
            v = '\n'.join(vlines)

            # remove pre-ceding special chars
            for bc in ['-', '*']:
                if v:
                    if v[0] == bc:
                        v = v[1:]
                    v = v.strip()

            # keep just the first line for types and components
            if k in ['issue type', 'component name']:
                if v:
                    vlines = v.split('\n')
                    # https://github.com/ansible/ansible-modules-core/issues/3085
                    vlines = [x for x in vlines if 'pick one' not in x]
                    v = vlines[0]

            # https://github.com/ansible/ansible-modules-core/issues/4060
            if k in ['issue type']:
                if '/' in v:
                    v = v.split('/')
                    if k == ['issue type']:
                        v = v[0]
                    else:
                        v = v[-1]
                    v = v.strip()

            if issue_class == 'issue':
                if k == 'issue type' and v != 'bug report' and 'bug' in v.lower():
                    v = 'bug report'
                elif k == 'issue type' and v != 'feature idea' and 'feature' in v.lower():
                    v = 'feature idea'
            elif issue_class == 'pullrequest':
                if k == 'issue type' and v != 'bugfix pull request' and 'bug' in v.lower():
                    v = 'bugfix pull request'
                elif k == 'issue type' and v != 'feature pull request' and 'feature' in v.lower():
                    v = 'feature pull request'
                elif k == 'issue type' and v != 'new module pull request' and 'new module' in v.lower():
                    v = 'new module pull request'
                elif k == 'issue type' and v != 'docs pull request' and 'docs' in v.lower():
                    v = 'docs pull request'
                elif k == 'issue type' and v != 'test pull request' and 'test' in v.lower():
                    v = 'test pull request'

        if v == 'paste below':
            v = ''

        # save
        tdict[k] = v

    # quick clean and add raw component to the dict
    component_raw = remove_markdown_comments(component_raw)
    component_raw = clean_bad_characters(component_raw, exclude=['__'])
    component_raw = '\n'.join([x.strip() for x in component_raw.split('\n') if x.strip()])
    component_raw = '\n'.join([x for x in component_raw.split('\n') if not x.startswith('#')])
    tdict['component_raw'] = component_raw

    return tdict


def clean_bad_characters(raw_text, exclude=None):
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


def remove_markdown_comments(rawtext):
    # Get rid of the comment blocks from the markdown template
    # <!--- ---> OR <!-- -->
    cleaned = rawtext
    loopcount = 0
    while cleaned.find('<!-') > -1 and loopcount <= 20:
        loopcount += 1
        start = cleaned.find('<!-')
        if start > -1:
            end = cleaned.find('->', start)
            if end == -1:
                cleaned = cleaned[:start-1]
            else:
                end += 2
                cleaned = cleaned[0:start] + cleaned[end:]
        else:
            break
    return cleaned


def extract_pr_number_from_comment(rawtext):
    # "resolved_by_pr 5136" --> 5136
    # "resolved_by_pr #5136" --> 5136
    # "resolved_by_pr https://github.com/ansible/ansible/issues/5136" --> 5136
    # "resolved_by_pr #5319." --> 5319
    # "resolved_by_pr: 61430" --> 61430

    matches = re.findall(r'\d+', rawtext)
    matches = [int(x) for x in matches]
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

        else:
            return []

    def extract_github_id(self, author):
        """Extract a set of github login(s) from a string."""

        # safegaurd against exceptions
        if author is None:
            return []

        authors = set()

        if author is None:
            return authors

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

    # if iw.is_issue():
    #     tfile = '.github/ISSUE_TEMPLATE/bug_report.md'
    # else:
    #     tfile = '.github/PULL_REQUEST_TEMPLATE.md'

    # # use the fileindexer whenever possible to conserve ratelimits
    # if iw.gitrepo:
    #     tf_content = iw.gitrepo.get_file_content(tfile)
    # else:
    #     try:
    #         tf = iw.repo.get_file_contents(tfile)
    #         tf_content = tf.decoded_content
    #     except Exception:
    #         logging.warning(f'repo does not have {tfile}')
    #         tf_content = ''

    # # pull out the section names from the tempalte
    # tf_sections = extract_template_sections(tf_content, header=TEMPLATE_HEADER)
    tf_sections = SECTIONS

    # extract ...
    template_data = \
        extract_template_data(
            iw.instance.body,
            issue_class=iw.github_type,
            sections=tf_sections
        )

    # try comments if the description was insufficient
    if len(template_data.keys()) <= 2:
        s_comments = iw.history.get_user_comments(iw.submitter)
        for s_comment in s_comments:

            _template_data = extract_template_data(
                s_comment,
                issue_class=iw.github_type,
                sections=tf_sections
            )

            if _template_data:
                for k, v in _template_data.items():
                    if not v:
                        continue
                    if v and (k not in template_data or not template_data.get(k)):
                        template_data[k] = v

    if 'ANSIBLE VERSION' in tf_sections and 'ansible version' not in template_data:

        # FIXME - abstract this into a historywrapper method
        vlabels = [x for x in iw.history.history if x['event'] == 'labeled']
        vlabels = [x for x in vlabels if x['actor'] not in C.DEFAULT_BOT_NAMES]
        vlabels = [x['label'] for x in vlabels if x['label'].startswith('affects_')]
        vlabels = [x for x in vlabels if x.startswith('affects_')]

        versions = [x.split('_')[1] for x in vlabels]
        versions = [float(x) for x in versions]
        if versions:
            version = versions[-1]
            template_data['ansible version'] = to_text(version)

    if 'COMPONENT NAME' in tf_sections and 'component name' not in template_data:
        if iw.is_pullrequest():
            fns = iw.files
            if fns:
                template_data['component name'] = '\n'.join(fns)
                template_data['component_raw'] = '\n'.join(fns)
        else:
            clabels = [x for x in iw.labels if x.startswith('c:')]
            if clabels:
                fns = []
                for clabel in clabels:
                    clabel = clabel.replace('c:', '')
                    fns.append('lib/ansible/' + clabel)
                template_data['component name'] = '\n'.join(fns)
                template_data['component_raw'] = '\n'.join(fns)

            elif 'documentation' in template_data.get('issue type', '').lower():
                template_data['component name'] = 'docs'
                template_data['component_raw'] = 'docs'

    if 'ISSUE TYPE' in tf_sections and 'issue type' not in template_data:

        # FIXME - turn this into a real classifier based on work done in
        # jctanner/pr-triage repo.

        itype = None

        while not itype:

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
            if itype:
                break

            if iw.is_pullrequest():
                fns = iw.files
                for fn in fns:
                    if fn.startswith('doc'):
                        itype = 'docs'
                        break
            if itype:
                break

            msgs = [iw.title, iw.body]
            if iw.is_pullrequest():
                msgs += [x['message'] for x in iw.history.history if x['event'] == 'committed']

            msgs = [x for x in msgs if x]
            msgs = [x.lower() for x in msgs]

            for msg in msgs:
                if 'fix' in msg:
                    itype = 'bug'
                    break
                if 'addresses' in msg:
                    itype = 'bug'
                    break
                if 'broke' in msg:
                    itype = 'bug'
                    break
                if 'add' in msg:
                    itype = 'feature'
                    break
                if 'should' in msg:
                    itype = 'feature'
                    break
                if 'please' in msg:
                    itype = 'feature'
                    break
                if 'feature' in msg:
                    itype = 'feature'
                    break

            # quit now
            break

        if itype and itype == 'bug' and iw.is_issue():
            template_data['issue type'] = 'bug report'
        elif itype and itype == 'bug' and not iw.is_issue():
            template_data['issue type'] = 'bugfix pullrequest'
        elif itype and itype == 'feature' and iw.is_issue():
            template_data['issue type'] = 'feature idea'
        elif itype and itype == 'feature' and not iw.is_issue():
            template_data['issue type'] = 'feature pullrequest'
        elif itype and itype == 'docs' and iw.is_issue():
            template_data['issue type'] = 'documentation report'
        elif itype and itype == 'docs' and not iw.is_issue():
            template_data['issue type'] = 'documenation pullrequest'

    return template_data
