#!/usr/bin/env python

import logging
import operator
import re
#import shlex
#from jinja2 import Template
from string import Template

import ansibullbot.constants as C


SECTIONS = ['ISSUE TYPE', 'COMPONENT NAME', 'PLUGIN NAME',
            'ANSIBLE VERSION', 'ANSIBLE CONFIGURATION', 'CONFIGURATION',
            'OS / ENVIRONMENT', 'SUMMARY', 'ENVIRONMENT',
            'STEPS TO REPRODUCE', 'EXPECTED RESULTS',
            'ACTUAL RESULTS', 'ADDITIONAL INFORMATION']


def extract_template_sections(body, header='#####'):
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
    for k,v in match_map.items():
        try:
            before = upper_body[v-1]
            after = upper_body[v + len(k)]
            header = before + '${section}' + after
            headers.append(header)
        except:
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
                    logging.error('breakpoint!')
                    import epdb; epdb.st()
                else:
                    raise Exception('substitution failed: %s' % str(e))
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
                    #import epdb; epdb.st()
                    break

        if not match_map:
            return {}

    elif len(headers) <= 1:
        if headers and \
                ('#' not in headers[0] and
                 ':' not in headers[0] and
                 '*' not in headers[0]):
            return {}
        else:
            #logging.error('breakpoint!')
            #import epdb; epdb.st()
            pass

    # sort mapping by element id
    match_map = sorted(match_map.items(), key=operator.itemgetter(1))

    if match_map and 'ISSUE TYPE' not in [x[0] for x in match_map]:
        if match_map[0][1] > 10:
            match_map.insert(0, ('ISSUE TYPE', 0))

    # extract the sections based on their indexes
    total_indexes = len(match_map) - 1
    for idx,x in enumerate(match_map):

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
    for k,v in tdict.iteritems():
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
    for k,v in tdict.iteritems():
        # remove markdown comments from the sections
        v = remove_markdown_comments(v)

        #if issue_number == 4238 and k == 'component name':
        #    import epdb; epdb.st()

        # remove non-ascii chars
        v = v.encode('ascii',errors='ignore')

        # normalize newlines and return chars
        v = v.replace('\r', '\n')

        # remove pre-ceding and trailing newlines
        v = v.strip()

        # remove trailing hashes
        while v.endswith('#'):
            v = v[:-1]

        # remove pre-ceding and trailing newlines (AGAIN)
        v = v.strip()

        # import epdb; epdb.st()
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
                    reg = re.compile('\S+_module')
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
            v = clean_bad_characters(v)

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

        # save
        tdict[k] = v

    # quick clean and add raw component to the dict
    component_raw = remove_markdown_comments(component_raw)
    component_raw = clean_bad_characters(component_raw)
    component_raw = '\n'.join([x.strip() for x in component_raw.split('\n') if x.strip()])
    component_raw = '\n'.join([x for x in component_raw.split('\n') if not x.startswith('#')])
    tdict['component_raw'] = component_raw

    return tdict

def clean_bad_characters(raw_text, exclude=[]):
    badchars = ['#', ':', ';', ',', '*', '"', "'", '`', '---', '__']

    # Exclude patterns of word, word,word
    if re.search(r'(\w+,\s?)+\w+', raw_text):
        exclude.extend(',')

    # Exclude contractions like It's
    if re.search(r"\w+'\w", raw_text):
        exclude.extend("'")

    # Don't remove characters passed in as an exclusion
    badchars = [x for x in badchars if x not in exclude]

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


def _remove_markdown_comments(rawtext):
    # Get rid of the comment blocks from the markdown template
    # <!--- ---> OR <!-- -->
    cleaned = []
    inphase = None
    for idx,x in enumerate(rawtext):
        if rawtext[idx:(idx+5)] == '<!---':
            inphase = True
        if inphase and idx <= 5:
            continue
        if inphase and rawtext[(idx-3):idx] == '-->':
            inphase = False
            continue
        if inphase:
            continue
        cleaned.append(x)
    return ''.join(cleaned)


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
        newword = ''
        for char in words[0]:
            if char.isdigit():
                newword += str(char)
        if newword:
            words[0] = newword

    if not words:
        return None
    number = words[0]

    if number.isdigit():
        number = int(number)
    elif number.startswith('#'):
        number = number[1:]
        number = int(number)
    elif number.startswith('http'):
        urlparts = number.split('/')
        number = urlparts[-1]
        number = int(number)
    elif rawtext.find('#'):
        number = rawtext[rawtext.find('#'):]
        number = number.replace('#', '')
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
        logging.error('NOT SURE HOW TO PARSE %s' % rawtext)
        if C.DEFAULT_BREAKPOINTS:
            logging.error('breakpoint!')
            import epdb; epdb.st()
        else:
            raise Exception('parsing error')

    return number
