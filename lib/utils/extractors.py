#!/usr/bin/env python

import operator
import shlex

def extract_template_data(body, issue_number=None):
    SECTIONS = ['ISSUE TYPE', 'COMPONENT NAME', 'PLUGIN NAME', 
                'ANSIBLE VERSION', 'CONFIGURATION', 
                'OS / ENVIRONMENT', 'SUMMARY', 'ENVIRONMENT', 
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

            # https://github.com/ansible/ansible-modules-extras/issues/2262
            if k == 'component name':
                v = v.lower()

            # https://github.com/ansible/ansible-modules-core/issues/4159
            if k == 'component name' and 'module' in v:
                v = v.replace('module', ' ')

            # remove useless chars
            badchars = ['#', ',', ':', ';', '*', "'", '"', '`', '---', '__']
            for bc in badchars:
                v = v.replace(bc, '')

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
                    vlines = [x for x in vlines if not 'pick one' in x]
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

            if k == 'issue type' and v != 'bug report' and 'bug' in v.lower():
                v = 'bug report'
            elif k == 'issue type' and v != 'feature idea' and 'feature' in v.lower():
                v = 'feature idea'

        # save
        tdict[k] = v

    #import epdb; epdb.st()
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


def extract_pr_number_from_comment(rawtext, command='resolved_by_pr'):
    # "resolved_by_pr 5136" --> 5136
    # "resolved_by_pr #5136" --> 5136
    # "resolved_by_pr https://github.com/ansible/ansible/issues/5136" --> 5136
    # "resolved_by_pr https://github.com/ansible/ansible/issues/5136" --> 5136
    index = rawtext.find(command)
    index += len(command)
    data = rawtext[index:]
    data = data.strip()
    words = data.split()    
    
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
    else:
        print('NOT SURE HOW TO PARSE %s' % rawtext)
        import epdb; epdb.st()

    return number
