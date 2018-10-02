#!/usr/bin/env python

import ast
import logging
import operator
import re
#import shlex
import yaml
#from jinja2 import Template
from string import Template

import six

import ansibullbot.constants as C
from ansibullbot._text_compat import to_bytes, to_text
from ansibullbot.parsers.botmetadata import BotYAMLLoader


SECTIONS = [u'ISSUE TYPE', u'COMPONENT NAME', u'PLUGIN NAME',
            u'ANSIBLE VERSION', u'ANSIBLE CONFIGURATION', u'CONFIGURATION',
            u'OS / ENVIRONMENT', u'SUMMARY', u'ENVIRONMENT',
            u'STEPS TO REPRODUCE', u'EXPECTED RESULTS',
            u'ACTUAL RESULTS', u'ADDITIONAL INFORMATION']


def extract_template_sections(body, header=u'#####'):
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


def extract_template_data(body, issue_number=None, issue_class='issue', sections=SECTIONS):

    # this is the final result to return
    tdict = {}

    if not body:
        return tdict

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
        for section in SECTIONS:
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
        for section in SECTIONS:
            if section in match_map:
                continue
            for choice in choices:
                t = Template(choice)
                tofind = t.substitute(section=section)
                match = upper_body.find(tofind)
                if match != -1:
                    match_map[section] = match + 1
                    break

        if not match_map:
            return {}

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

    # sort mapping by element id
    match_map = sorted(match_map.items(), key=operator.itemgetter(1))

    if match_map and u'ISSUE TYPE' not in [x[0] for x in match_map]:
        if match_map[0][1] > 10:
            match_map.insert(0, (u'ISSUE TYPE', 0))

    # extract the sections based on their indexes
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
    # "resolved_by_pr https://github.com/ansible/ansible/issues/5136" --> 5136
    # "resolved_by_pr #5319." --> 5319
    index = rawtext.find(command)
    index += len(command)
    data = rawtext[index:]
    data = data.strip()
    words = data.split()

    # remove non-digit chars
    if words:
        newword = u''
        for char in words[0]:
            if char.isdigit():
                newword += to_text(char)
        if newword:
            words[0] = newword

    if not words:
        return None
    number = words[0]

    if number.isdigit():
        number = int(number)
    elif number.startswith(u'#'):
        number = number[1:]
        number = int(number)
    elif number.startswith(u'http'):
        urlparts = number.split(u'/')
        number = urlparts[-1]
        number = int(number)
    elif rawtext.find(u'#'):
        number = rawtext[rawtext.find(u'#'):]
        number = number.replace(u'#', u'')
        while number:
            if not number[-1].isdigit():
                number = number[:-1]
            else:
                break
        try:
            number = int(number)
        except Exception:
            number = None
    else:
        logging.error(u'NOT SURE HOW TO PARSE %s' % rawtext)
        if C.DEFAULT_BREAKPOINTS:
            logging.error(u'breakpoint!')
            import epdb; epdb.st()
        else:
            raise Exception(u'parsing error')

    return number


class ModuleExtractor(object):

    _AUTHORS = None
    _AUTHORS_DATA = None
    _AUTHORS_RAW = None
    _DOCUMENTATION_RAW = None
    _FILEDATA = None
    _METADATA = None

    def __init__(self, filepath, email_cache=None):
        self.filepath = filepath
        self.email_cache = email_cache

    @property
    def filedata(self):
        if self._FILEDATA is None:
            with open(self.filepath, 'rb') as f:
                self._FILEDATA = f.read()
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

    def get_module_authors(self):
        """Grep the authors out of the module docstrings"""

        documentation = u''
        inphase = False

        lines = to_text(self.filedata).split(u'\n')
        for line in lines:
            if u'DOCUMENTATION' in line:
                inphase = True
                continue
            if inphase and (line.strip().endswith((u"'''", u'"""'))):
                #phase = None
                break
            if inphase:
                documentation += line + u'\n'

        if not documentation:
            logging.debug(u'no documentation found in {}'.format(self.filepath))
            return []

        # clean out any other yaml besides author to save time
        inphase = False
        author_lines = u''
        self._DOCUMENTATION_RAW = documentation
        doc_lines = documentation.split(u'\n')
        for idx, x in enumerate(doc_lines):
            if x.startswith(u'author'):
                #print("START ON %s" % x)
                inphase = True
                #continue
            if inphase and not x.strip().startswith((u'-', u'author')):
                #print("BREAK ON %s" % x)
                inphase = False
                break
            if inphase:
                author_lines += x + u'\n'

        if not author_lines:
            logging.debug(u'no author lines found in {}'.format(self.filepath))
            return []

        self._AUTHORS_RAW = author_lines
        ydata = {}
        try:
            ydata = yaml.load(author_lines, BotYAMLLoader)
            self._AUTHORS_DATA = ydata
        except Exception as e:
            print(e)
            return []

        # quit early if the yaml was not valid
        if not ydata:
            return []

        # sometimes the field is 'author', sometimes it is 'authors'
        if u'authors' in ydata:
            ydata[u'author'] = ydata[u'authors']

        # quit if the key was not found
        if u'author' not in ydata:
            return []

        if type(ydata[u'author']) != list:
            ydata[u'author'] = [ydata[u'author']]

        authors = []
        for author in ydata[u'author']:
            github_ids = self.extract_github_id(author)
            if github_ids:
                authors.extend(github_ids)

        return authors

    def extract_github_id(self, author):
        authors = set()

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
        meta = {}
        rawmeta = b''

        inphase = False
        lines = self.filedata.split(b'\n')
        for line in lines:
            if line.startswith(b'ANSIBLE_METADATA'):
                inphase = True
                #continue
            if line.startswith(b'DOCUMENTATION'):
                break
            if inphase:
                rawmeta += line

        rawmeta = rawmeta.replace(b'ANSIBLE_METADATA =', b'', 1)
        rawmeta = rawmeta.strip()
        try:
            meta = ast.literal_eval(rawmeta)
            tmp_meta = {}
            for k, v in meta.items():
                if isinstance(k, six.binary_type):
                    k = to_text(k)
                if isinstance(v, six.binary_type):
                    v = to_text(v)
                if isinstance(v, list):
                    tmp_list = []
                    for i in v:
                        if isinstance(i, six.binary_type):
                            i = to_text(i)
                        tmp_list.append(i)
                    v = tmp_list
                    del tmp_list
                tmp_meta[k] = v
            meta = tmp_meta
            del tmp_meta
        except (SyntaxError, ValueError):  # Py3: ValueError
            pass

        return meta
