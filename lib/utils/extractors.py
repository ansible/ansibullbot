#!/usr/bin/env python

import operator
import shlex

def extract_template_data(body, issue_number=None):
    SECTIONS = ['ISSUE TYPE', 'COMPONENT NAME', 'PLUGIN NAME', 
                'ANSIBLE VERSION', 'CONFIGURATION', 
                'OS / ENVIRONMENT', 'SUMMARY', 
                'STEPS TO REPRODUCE', 'EXPECTED RESULTS',
                'ACTUAL RESULTS']

    ISSUE_TYPES = ['Bug Report', 'Feature Idea', 
                   'Feature Request', 'Documentation Report']

    tdict = {} #this is the final result to return

    upper_body = body.upper()

    # make a map of locations where each section starts
    match_map = {}
    for section in SECTIONS:
        # http://www.tutorialspoint.com/python/string_find.htm
        # str.find(str, beg=0 end=len(string))        
        match = upper_body.find(section)                 
        if match != -1:
            match_map[section] = match
    if not match_map:
        return {}

    # sort mapping by element id
    match_map = sorted(match_map.items(), key=operator.itemgetter(1))
    #import pprint; pprint.pprint(match_map)

    # extract the sections based on their indexes
    total_indexes = len(match_map) - 1
    for idx,x in enumerate(match_map):
        start_index = x[1] + (len(x[0]))
        # if last index, slice to the end
        if idx >= total_indexes:
            tdict[x[0]] = body[start_index:]
        else:        
            # slice to the next section
            stop_index = match_map[idx+1][1]
            tdict[x[0]] = body[start_index:stop_index]

    # lowercase the keys
    for k,v in tdict.iteritems():
        ku = k.lower()
        if ku == 'plugin name':
            ku = 'component name'
        tdict.pop(k, None)
        tdict[ku] = v

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

        # clean more on critical sections
        if k != 'summary' and not 'step' in k and not 'result' in k:

            # remove useless chars
            badchars = ['#', ':', '*', "'", '"', '`', '---', '__']
            for bc in badchars:
                v = v.replace(bc, '')

            # clean up empty lines
            vlines = v.split('\n')
            vlines = [x for x in vlines if x.strip()]
            vlines = [x.strip() for x in vlines if x.strip()]
            v = '\n'.join(vlines)

            # remove pre-ceding special chars
            for bc in ['-', '*']:
                if not v:
                    continue
                if v[0] == bc:
                    v = v[1:]
                v = v.strip()

            # keep just the first line for types and components
            if k in ['issue type', 'component name']:
                if not v:
                    continue
                vlines = v.split('\n')
                # https://github.com/ansible/ansible-modules-core/issues/3085
                vlines = [x for x in vlines if not 'pick one' in x]
                v = vlines[0]

            # https://github.com/ansible/ansible-modules-core/issues/4060
            if k in ['issue type', 'component name']:
                if '/' in v:
                    v = v.split('/')[0]
                    v = v.strip()

            # https://github.com/ansible/ansible-modules-core/issues/4201
            if k == 'component name' and ' ' in v:
                v = shlex.split(v)[0]

            #if k == 'component name' and issue_number == 4138:
            #    import epdb; epdb.st()

            if k == 'issue type' and v != 'bug report' and 'bug' in v.lower():
                v = 'bug report'
            elif k == 'issue type' and v != 'feature idea' and 'feature' in v.lower():
                v = 'feature idea'

        # save
        tdict[k] = v

    #import epdb; epdb.st()
    return tdict


def _extract_template_data(body):
    """Extract templated data from an issue body"""


    # **Issue Type: Bug Report**\r\n\r\n**Ansible Version: Ansible 1.7.2**
    # **Issue Type**: Feature Idea

    SECTIONS = ['ISSUE TYPE', 'COMPONENT NAME', 
                'ANSIBLE VERSION', 'CONFIGURATION', 
                'OS / ENVIRONMENT', 'SUMMARY', 
                'STEPS TO REPRODUCE', 'EXPECTED RESULTS',
                'ACTUAL RESULTS']

    ISSUE_TYPES = ['Bug Report', 'Feature Idea', 'Feature Request', 'Documentation Report']

    # This is what we will return
    tdict = {}

    body = remove_markdown_comments(body)

    try:
        lines = body.split('\n')
    except Exception as e:
        lines = []

    lines = [x.strip() for x in lines]

    # Fix the **FOO:**bar lines
    newlines = []
    for idx,x in enumerate(lines):
        msections = [y for y in SECTIONS if y in x.upper()]
        if len(msections) == 1:
            if x.startswith('**') and ':**' in x or '**:' in x:
                xlines = x.split('**')
                xlines = [y.strip() for y in xlines if y.strip()]
                xlines = [y for y in xlines if y != ':']
                xlines = [y.strip() for y in xlines if y.strip()]
                newlines += xlines
            else:
                newlines.append(x)
        else:
            newlines.append(x)
    #if newlines != lines:
    #    import epdb; epdb.st()
    lines = newlines

    # add newlines after sections (and fix different headers)...
    newlines = []
    for idl,line in enumerate(lines):
        cleaned = line.strip()

        matching_sections = [x for x in SECTIONS if x in cleaned.upper()]
        if not matching_sections:
            newlines.append(cleaned)
            continue

        cleaned = cleaned.upper()
        cparts = cleaned.split()

        # https://github.com/ansible/ansible-modules-extras/issues/2443
        # https://github.com/ansible/ansible-modules-core/issues/3047
        if len(matching_sections) == 1 \
            and len(cparts) == 2 \
            and not cleaned.startswith('#'):
            cleaned = cleaned.replace('*', '')
            cleaned = '##### ' + cleaned
            #print(cleaned)
            #import epdb; epdb.st()

        # force the correct number of hashmarks
        if cleaned.startswith('#') and len([x for x in SECTIONS if x in cleaned.upper()]) > 0:
            parts = cleaned.split()
            parts = [x.strip() for x in parts if x.strip()]
            parts[0] = '#####'
            cleaned = ' '.join(parts)
            if cleaned.endswith(':'):
                cleaned = ''.join([x for x in cleaned[:-1]])

        # https://github.com/ansible/ansible-modules-core/issues/911
        cleaned = cleaned.replace('**:', ':')

        hassection = False
        for section in SECTIONS:
            if section in cleaned:
                hassection = True

        #if not line.startswith('#') and not line.startswith('**') and not hassection:
        if not hassection:
            newlines.append(line)
            continue

        # uppercase that junk        
        # https://github.com/ansible/ansible-modules-core/issues/335
        cleaned = cleaned.title()

        xlines = []
        for section in SECTIONS:
            if cleaned.upper().startswith('##### ' + section) and not cleaned.endswith(section):
                xlines.append('##### ' + section)
                cleaned = cleaned.upper().replace('##### ' + section, '')
            elif cleaned.upper().startswith('**') and cleaned.upper().endswith('**') and section in cleaned.upper():
                # https://github.com/ansible/ansible-modules-core/issues/143
                cleaned = cleaned.replace('**', '')
                xlines.append('##### ' + section)
                cleaned = cleaned.upper().replace(section, '')
            elif cleaned.upper().startswith(section) and not cleaned.upper().endswith(section):
                # https://github.com/ansible/ansible-modules-core/issues/178
                xlines.append('##### ' + section)
                cleaned = cleaned.upper()
                cleaned = cleaned.replace(section, '')
        xlines.append(cleaned)
        newlines += xlines
    lines = [x.strip() for x in newlines]

    section = None
    for idl,line in enumerate(lines):
        cleaned = line.strip()
        if (line.startswith('##### ') or cleaned in SECTIONS) \
            or (line.startswith('**') and line.replace('**', '') in SECTIONS):

            section = line.replace('#', '').lower().strip()
            section = section.replace(':', '')
            tdict[section] = []
            continue

        if section:
            if section not in tdict:
                tdict[section] = []
            tdict[section].append(line)

    # Replace 'plugin' with 'component'
    if not 'component name' in tdict and 'plugin name' in tdict:
        tdict['component name'] = tdict['plugin name']

    for key in ['issue type', 'component name', 'ansible version']:
        if not key in tdict:
            continue

        # smart quotes suck ...
        # https://github.com/ansible/ansible-modules-extras/issues/521
        tdict[key] = [x.encode('ascii',errors='ignore') for x in tdict[key]]

        # some people like horizontal lines ...
        # https://github.com/ansible/ansible-modules-core/issues/2762
        tdict[key] = [x for x in tdict[key] if x != '---']

        tdict[key] = [x.replace(':', '') for x in tdict[key]]
        tdict[key] = [x.replace(',', '') for x in tdict[key]]
        tdict[key] = [x.replace('*', '') for x in tdict[key]]
        tdict[key] = [x.replace('- ', '') for x in tdict[key]]
        tdict[key] = [x.replace('`', '') for x in tdict[key]]
        tdict[key] = [x.replace('"', '') for x in tdict[key]]
        tdict[key] = [x.replace("'", '') for x in tdict[key]]
        tdict[key] = [x.replace("(", '') for x in tdict[key]]
        tdict[key] = [x.replace(")", '') for x in tdict[key]]
        tdict[key] = [x.replace("[", '') for x in tdict[key]]
        tdict[key] = [x.replace("]", '') for x in tdict[key]]

        if key in ['issue type', 'component name']:
            # https://github.com/ansible/ansible-modules-extras/issues/1831
            tdict[key] = [x for x in tdict[key] if not 'pick' in x.lower()]

        if key == 'component name':
            tdict[key] = [x.replace('_module', '') for x in tdict[key] if x.strip()]
            tdict[key] = [x.replace('module ', '') for x in tdict[key] if x.strip()]
            tdict[key] = [x.replace(' module ', '') for x in tdict[key] if x.strip()]
            tdict[key] = [x.replace(' module', '') for x in tdict[key] if x.strip()]
            tdict[key] = [x.replace(' plugin', '') for x in tdict[key] if x.strip()]

        tdict[key] = [x.strip() for x in tdict[key] if x.strip()]
        tdict[key] = [x.lower() for x in tdict[key]]

        if key == 'component name':
            # https://github.com/ansible/ansible-modules-extras/issues/2166
            tdict[key] = [x.replace(' ', '/') for x in tdict[key] if x.strip()]

        if key == 'issue type':
            # issue types are only supposed to be two words, so drop the extra words
            for idx, x in enumerate(tdict[key]):
                parts = x.split()
                if len(parts) > 2:
                    tdict[key][idx] = ' '.join(parts[0:2])

            # https://github.com/ansible/ansible-modules-core/issues/633
            if tdict[key] == 'feature request':
                tdict[key] = 'feature idea'


        tdict[key] = [x.strip() for x in tdict[key] if x.strip()]

        if len(tdict[key]) == 0:
            tdict[key] = None
        elif len(tdict[key]) == 1:
            tdict[key] = tdict[key][0]
        elif len(tdict[key]) > 1 and key in ['component name', 'issue type']:
            tdict[key] = tdict[key][0]
        elif len(tdict[key]) > 1:
            tdict[key] = '\n'.join(tdict[key])

    if 'issue type' in tdict:
        if tdict['issue type'] in ['feature request', 'feature enhancement']:
            # https://github.com/ansible/ansible-modules-core/issues/633
            # https://github.com/ansible/ansible-modules-extras/issues/1345
            tdict['issue type'] = 'feature idea'
        if tdict['issue type'] in ['bug']:
            # https://github.com/ansible/ansible-modules-extras/issues/1292
            tdict['issue type'] = 'bug report'
        elif 'bug' in tdict['issue type']:
            # https://github.com/ansible/ansible-modules-extras/issues/1510
            tdict['issue type'] = 'bug report'

    return tdict


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


