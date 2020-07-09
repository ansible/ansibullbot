import ast
import logging
import operator
import os
import re
from string import Template

import six
import yaml

import ansibullbot.constants as C
from ansibullbot._text_compat import to_bytes, to_text


SECTIONS = [u'ISSUE TYPE', u'COMPONENT NAME', u'PLUGIN NAME',
            u'ANSIBLE VERSION', u'ANSIBLE CONFIGURATION', u'CONFIGURATION',
            u'OS / ENVIRONMENT', u'SUMMARY', u'ENVIRONMENT',
            u'STEPS TO REPRODUCE', u'EXPECTED RESULTS',
            u'ACTUAL RESULTS', u'ADDITIONAL INFORMATION']

TEMPLATE_HEADER = u'#####'


def extract_template_sections(body, header=TEMPLATE_HEADER):
    ''' Get the section names from a .github/*.md file in a repo'''

    sections = {}
    lines = body.split(u'\n')
    current_section = None
    index = 0
    for line in lines:
        if line.startswith(header):
            section = line.replace(header, u'', 1)
            section = section.strip()
            sections[section] = {u'required': False, u'index': index}
            index += 1
            current_section = section

        elif line.startswith(u'<!--') and current_section:
            if u'required: True' in line:
                sections[current_section][u'required'] = True

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
            header = before + u'${section}' + after
            headers.append(header)
        except Exception as e:
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
                if C.DEFAULT_BREAKPOINTS:
                    logging.error(u'breakpoint!')
                    import epdb; epdb.st()
                else:
                    raise Exception(u'substitution failed: %s' % to_text(e))
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
                (u'#' not in headers[0] and
                 u':' not in headers[0] and
                 u'*' not in headers[0]):
            return {}
        else:
            if C.DEFAULT_BREAKPOINTS:
                logging.error(u'breakpoint!')
                import epdb; epdb.st()

    # sort mapping by element id and inject itype if needed
    match_map = sorted(match_map.items(), key=operator.itemgetter(1))
    if match_map and u'ISSUE TYPE' not in [x[0] for x in match_map]:
        if match_map[0][1] > 10:
            match_map.insert(0, (u'ISSUE TYPE', 0))
    
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
    doubles = re.findall(r'##### [A-Z]+\s+[A-Z]+\r\n', body)
    singles = re.findall(r'##### [A-Z]+\r\n', body)
    for single in singles[:]:
        for x in doubles:
            if x.startswith(single):
                singles.remove(single)
    tofind = sorted(set(doubles + singles))

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


def extract_template_data(body, issue_number=None, issue_class='issue', sections=None, find_extras=True):

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
    for k, v in six.iteritems(tdict):
        ku = k.lower()
        if ku == u'plugin name':
            ku = u'component name'
        ndict[ku] = v
    if ndict != tdict:
        tdict = ndict.copy()

    # make a raw component section for later processing
    component_raw = tdict.get(u'component name', u'')

    # https://github.com/ansible/ansibullbot/issues/359
    if u',' in tdict.get(u'component name', u''):
        tdict[u'component name'] = tdict[u'component name'].replace(u',', u'\n')

    # https://github.com/ansible/ansibullbot/issues/385
    if u' and ' in tdict.get(u'component name', u''):
        tdict[u'component name'] = tdict[u'component name'].replace(u' and ', u'\n')

    # cleanup the sections
    for k, v in six.iteritems(tdict):
        # remove markdown comments from the sections
        v = remove_markdown_comments(v)

        # remove non-ascii chars
        v = to_text(to_bytes(v, 'ascii', errors='ignore'), 'ascii')

        # normalize newlines and return chars
        v = v.replace(u'\r', u'\n')

        # remove pre-ceding and trailing newlines
        v = v.strip()

        # remove trailing hashes
        while v.endswith(u'#'):
            v = v[:-1]

        # remove pre-ceding and trailing newlines (AGAIN)
        v = v.strip()

        # clean more on critical sections
        if u'step' not in k and u'result' not in k:

            # https://github.com/ansible/ansible-modules-extras/issues/2262
            if k == u'component name':
                v = v.lower()

            if k == u'component name' and u'module' in v:
                if u'/modules/' in v or \
                        u'module_util' in v or \
                        u'module_utils/' in v or \
                        u'validate-modules' in v or\
                        u'module_common' in v:
                    # https://github.com/ansible/ansible/issues/20563
                    # https://github.com/ansible/ansible/issues/18179
                    pass
                else:
                    # some modules have the word "_module" in their name
                    # https://github.com/ansible/ansibullbot/issues/198
                    # https://github.com/ansible/ansible-modules-core/issues/4159
                    # https://github.com/ansible/ansible-modules-core/issues/5328
                    reg = re.compile(u'\S+_module')
                    match = reg.match(v)
                    if match:
                        v = v[match.pos:match.end()]
                    else:
                        # https://github.com/ansible/ansibullbot/issues/385
                        if u'modules' in v:
                            v = v.replace(u'modules', u' ')
                        else:
                            v = v.replace(u'module', u' ')

            # remove useless chars
            v = clean_bad_characters(v)

            # clean up empty lines
            vlines = v.split(u'\n')
            vlines = [x for x in vlines if x.strip()]
            vlines = [x.strip() for x in vlines if x.strip()]
            v = u'\n'.join(vlines)

            # remove pre-ceding special chars
            for bc in [u'-', u'*']:
                if v:
                    if v[0] == bc:
                        v = v[1:]
                    v = v.strip()

            # keep just the first line for types and components
            if k in [u'issue type', u'component name']:
                if v:
                    vlines = v.split(u'\n')
                    # https://github.com/ansible/ansible-modules-core/issues/3085
                    vlines = [x for x in vlines if u'pick one' not in x]
                    v = vlines[0]

            # https://github.com/ansible/ansible-modules-core/issues/4060
            if k in [u'issue type']:
                if u'/' in v:
                    v = v.split(u'/')
                    if k == [u'issue type']:
                        v = v[0]
                    else:
                        v = v[-1]
                    v = v.strip()

            if issue_class == u'issue':
                if k == u'issue type' and v != u'bug report' and u'bug' in v.lower():
                    v = u'bug report'
                elif k == u'issue type' and v != u'feature idea' and u'feature' in v.lower():
                    v = u'feature idea'
            elif issue_class == u'pullrequest':
                if k == u'issue type' and v != u'bugfix pull request' and u'bug' in v.lower():
                    v = u'bugfix pull request'
                elif k == u'issue type' and v != u'feature pull request' and u'feature' in v.lower():
                    v = u'feature pull request'
                elif k == u'issue type' and v != u'new module pull request' and u'new module' in v.lower():
                    v = u'new module pull request'
                elif k == u'issue type' and v != u'docs pull request' and u'docs' in v.lower():
                    v = u'docs pull request'
                elif k == u'issue type' and v != u'test pull request' and u'test' in v.lower():
                    v = u'test pull request'

        # save
        tdict[k] = v

    # quick clean and add raw component to the dict
    component_raw = remove_markdown_comments(component_raw)
    component_raw = clean_bad_characters(component_raw, exclude=None)
    component_raw = u'\n'.join([x.strip() for x in component_raw.split(u'\n') if x.strip()])
    component_raw = u'\n'.join([x for x in component_raw.split(u'\n') if not x.startswith(u'#')])
    tdict[u'component_raw'] = component_raw

    return tdict


def clean_bad_characters(raw_text, exclude=None):
    badchars = [u'#', u':', u';', u',', u'*', u'"', u"'", u'`', u'---', u'__']

    if exclude is None:
        exclude = []

    # Exclude patterns of word, word,word
    if re.search(r'(\w+,\s?)+\w+', raw_text):
        exclude.extend(u',')

    # Exclude contractions like It's
    if re.search(r"\w+'\w", raw_text):
        exclude.extend(u"'")

    # Don't remove characters passed in as an exclusion
    if exclude:
        if isinstance(exclude, list):
            badchars = [x for x in badchars if x not in exclude]
        elif exclude:
            badchars = [x for x in badchars if x != exclude]

    for bc in badchars:
        raw_text = raw_text.replace(bc, u'')

    return raw_text


def remove_markdown_comments(rawtext):
    # Get rid of the comment blocks from the markdown template
    # <!--- ---> OR <!-- -->
    cleaned = rawtext
    loopcount = 0
    while cleaned.find(u'<!-') > -1 and loopcount <= 20:
        loopcount += 1
        start = cleaned.find(u'<!-')
        if start > -1:
            end = cleaned.find(u'->', start)
            if end == -1:
                cleaned = cleaned[:start-1]
            else:
                end += 2
                cleaned = cleaned[0:start] + cleaned[end:]
        else:
            break
    return cleaned


def _remove_markdown_comments(rawtext):
    # Get rid of the comment blocks from the markdown template
    # <!--- ---> OR <!-- -->
    cleaned = []
    inphase = None
    for idx, x in enumerate(rawtext):
        if rawtext[idx:(idx+5)] == u'<!---':
            inphase = True
        if inphase and idx <= 5:
            continue
        if inphase and rawtext[(idx-3):idx] == u'-->':
            inphase = False
            continue
        if inphase:
            continue
        cleaned.append(x)
    return u''.join(cleaned)


def extract_pr_number_from_comment(rawtext, command='resolved_by_pr'):
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


class ModuleExtractor(object):

    _AUTHORS = None
    _AUTHORS_DATA = None
    _AUTHORS_RAW = None
    _DOCUMENTATION_RAW = None
    _FILEDATA = None
    _METADATA = None
    _DOCSTRING = None

    def __init__(self, filepath, filedata=None, email_cache=None):
        self.filepath = filepath
        self._FILEDATA = filedata
        self.email_cache = email_cache

    @property
    def filedata(self):
        if self._FILEDATA is None:
            try:
                with open(self.filepath, 'rb') as f:
                    self._FILEDATA = f.read()
            except (IOError, OSError):
                return b''
        return self._FILEDATA

    @property
    def authors(self):
        if self._AUTHORS is None:
            self._AUTHORS = self.get_module_authors()
        return self._AUTHORS

    @property
    def metadata(self):
        if self._METADATA is None:
            self._METADATA = self.get_module_metadata()
        return self._METADATA

    @property
    def docs(self):
        if self._DOCSTRING is not None:
            return self._DOCSTRING

        documentation = u''
        inphase = False
        lines = to_text(self.filedata).split(u'\n')
        for line in lines:
            if u'DOCUMENTATION' in line:
                inphase = True
                continue
            if inphase and (line.strip().endswith((u"'''", u'"""'))):
                break
            if inphase:
                documentation += line + u'\n'

        self._DOCUMENTATION_RAW = documentation

        # some docstrings don't pass yaml validation with PyYAML >= 4.2
        try:
            self._DOCSTRING = yaml.load(self._DOCUMENTATION_RAW)
        except yaml.parser.ParserError as e:
            logging.warning('%s has non-yaml formatted docstrings' % self.filepath)
        except yaml.scanner.ScannerError as e:
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

        if u'ansible core team' in author.lower():
            authors.add(u'ansible')
        elif u'@' in author:
            # match github ids but not emails
            authors.update(re.findall(r'(?<!\w)@([\w-]+)(?![\w.])', author))
        elif u'github.com/' in author:
            # {'author': 'Henrique Rodrigues (github.com/Sodki)'}
            idx = author.find(u'github.com/')
            author = author[idx+11:]
            authors.add(author.replace(u')', u''))
        elif u'(' in author and len(author.split()) == 3:
            # Mathieu Bultel (matbu)
            idx = author.find(u'(')
            author = author[idx+1:]
            authors.add(author.replace(u')', u''))

        # search for emails
        for email in re.findall(r'[<(]([^@]+@[^)>]+)[)>]', author):
            github_id = self.email_cache.get(email)
            if github_id:
                authors.add(github_id)

        return list(authors)

    def get_module_metadata(self):

        if self.filepath is not None:
            # no directories please
            if os.path.isdir(self.filepath):
                return {}
            # no pycs please
            if self.filepath.endswith('.pyc') or self.filepath.endswith('.pyo'):
                return {}
            # no meta in __init__.py files
            if os.path.basename(self.filepath) == u'__init__.py':
                return {}
            # no point in parsing markdown
            if self.filepath.endswith('.md'):
                return {}
            # no point in parsing ps1 or ps2
            if self.filepath.endswith('.ps'):
                return {}
            if self.filepath.endswith('.ps1'):
                return {}
            if self.filepath.endswith('.ps2'):
                return {}
            if self.filepath.endswith('.rst'):
                return {}

        meta = {}
        rawmeta = b''
        inphase = False
        lines = self.filedata.split(b'\n')
        for line in lines:
            if line.startswith(b'ANSIBLE_METADATA') or b'ANSIBLE_METADATA' in line:
                rawmeta += line
                inphase = True
                continue
            if inphase and line.startswith(b'DOCUMENTATION'):
                break
            if inphase and line.startswith(b'from'):
                break
            if inphase and re.match(r'^[A-Za-z]', to_text(line)):
                break
            if inphase:
                rawmeta += line

        rawmeta = rawmeta.replace(b'ANSIBLE_METADATA =', b'', 1)
        rawmeta = rawmeta.strip()

        try:
            meta = ast.literal_eval(to_text(rawmeta))
        except Exception as e:
            logging.warning(e)

        return meta


def get_template_data(iw):
    """Extract templated data from an issue body"""

    if iw.is_issue():
        tfile = u'.github/ISSUE_TEMPLATE/bug_report.md'
    else:
        tfile = u'.github/PULL_REQUEST_TEMPLATE.md'

    # use the fileindexer whenever possible to conserve ratelimits
    if iw.gitrepo:
        tf_content = iw.gitrepo.get_file_content(tfile)
    else:
        try:
            tf = iw.repo.get_file_contents(tfile)
            tf_content = tf.decoded_content
        except Exception:
            logging.warning(u'repo does not have {}'.format(tfile))
            tf_content = u''

    # pull out the section names from the tempalte
    tf_sections = extract_template_sections(tf_content, header=TEMPLATE_HEADER)

    # what is required?
    iw._required_template_sections = \
        [x.lower() for x in tf_sections.keys()
            if tf_sections[x][u'required']]

    # extract ...
    template_data = \
        extract_template_data(
            iw.instance.body,
            issue_number=iw.number,
            issue_class=iw.github_type,
            sections=tf_sections.keys()
        )

    # try comments if the description was insufficient
    if len(template_data.keys()) <= 2:
        s_comments = iw.history.get_user_comments(iw.submitter)
        for s_comment in s_comments:

            _template_data = extract_template_data(
                s_comment,
                issue_number=iw.number,
                issue_class=iw.github_type,
                sections=tf_sections.keys()
            )

            if _template_data:
                for k, v in _template_data.items():
                    if not v:
                        continue
                    if v and (k not in template_data or not template_data.get(k)):
                        template_data[k] = v

    if u'ANSIBLE VERSION' in tf_sections and u'ansible version' not in template_data:

        # FIXME - abstract this into a historywrapper method
        vlabels = [x for x in iw.history.history if x[u'event'] == u'labeled']
        vlabels = [x for x in vlabels if x[u'actor'] not in C.DEFAULT_BOT_NAMES]
        vlabels = [x[u'label'] for x in vlabels if x[u'label'].startswith(u'affects_')]
        vlabels = [x for x in vlabels if x.startswith(u'affects_')]

        versions = [x.split(u'_')[1] for x in vlabels]
        versions = [float(x) for x in versions]
        if versions:
            version = versions[-1]
            template_data[u'ansible version'] = to_text(version)

    if u'COMPONENT NAME' in tf_sections and u'component name' not in template_data:
        if iw.is_pullrequest():
            fns = iw.files
            if fns:
                template_data[u'component name'] = u'\n'.join(fns)
                template_data[u'component_raw'] = u'\n'.join(fns)
        else:
            clabels = [x for x in iw.labels if x.startswith(u'c:')]
            if clabels:
                fns = []
                for clabel in clabels:
                    clabel = clabel.replace(u'c:', u'')
                    fns.append(u'lib/ansible/' + clabel)
                template_data[u'component name'] = u'\n'.join(fns)
                template_data[u'component_raw'] = u'\n'.join(fns)

            elif u'documentation' in template_data.get(u'issue type', u'').lower():
                template_data[u'component name'] = u'docs'
                template_data[u'component_raw'] = u'docs'

    if u'ISSUE TYPE' in tf_sections and u'issue type' not in template_data:

        # FIXME - turn this into a real classifier based on work done in
        # jctanner/pr-triage repo.

        itype = None

        while not itype:

            for label in iw.labels:
                if label.startswith(u'bug'):
                    itype = u'bug'
                    break
                elif label.startswith(u'feature'):
                    itype = u'feature'
                    break
                elif label.startswith(u'doc'):
                    itype = u'docs'
                    break
            if itype:
                break

            if iw.is_pullrequest():
                fns = iw.files
                for fn in fns:
                    if fn.startswith(u'doc'):
                        itype = u'docs'
                        break
            if itype:
                break

            msgs = [iw.title, iw.body]
            if iw.is_pullrequest():
                msgs += [x[u'message'] for x in iw.history.history if x[u'event'] == u'committed']

            msgs = [x for x in msgs if x]
            msgs = [x.lower() for x in msgs]

            for msg in msgs:
                if u'fix' in msg:
                    itype = u'bug'
                    break
                if u'addresses' in msg:
                    itype = u'bug'
                    break
                if u'broke' in msg:
                    itype = u'bug'
                    break
                if u'add' in msg:
                    itype = u'feature'
                    break
                if u'should' in msg:
                    itype = u'feature'
                    break
                if u'please' in msg:
                    itype = u'feature'
                    break
                if u'feature' in msg:
                    itype = u'feature'
                    break

            # quit now
            break

        if itype and itype == u'bug' and iw.is_issue():
            template_data[u'issue type'] = u'bug report'
        elif itype and itype == u'bug' and not iw.is_issue():
            template_data[u'issue type'] = u'bugfix pullrequest'
        elif itype and itype == u'feature' and iw.is_issue():
            template_data[u'issue type'] = u'feature idea'
        elif itype and itype == u'feature' and not iw.is_issue():
            template_data[u'issue type'] = u'feature pullrequest'
        elif itype and itype == u'docs' and iw.is_issue():
            template_data[u'issue type'] = u'documentation report'
        elif itype and itype == u'docs' and not iw.is_issue():
            template_data[u'issue type'] = u'documenation pullrequest'

    return template_data
