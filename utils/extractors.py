#!/usr/bin/env python

def extract_template_data(body):
    """Extract templated data from an issue body"""


    # **Issue Type: Bug Report**\r\n\r\n**Ansible Version: Ansible 1.7.2**
    # **Issue Type**: Feature Idea

    SECTIONS = ['ISSUE TYPE', 'COMPONENT NAME', 
                'ANSIBLE VERSION', 'CONFIGURATION', 
                'OS / ENVIRONMENT', 'SUMMARY', 
                'STEPS TO REPRODUCE', 'EXPECTED RESULTS',
                'ACTUAL RESULTS']

    ISSUE_TYPES = ['Bug Report', 'Feature Idea', 'Documentation Report']

    # This is what we will return
    tdict = {}

    body = remove_markdown_comments(body)

    try:
        lines = body.split('\n')
    except Exception as e:
        lines = []

    # add newlines after sections (and fix different headers)...
    newlines = []
    for idl,line in enumerate(lines):
        cleaned = line.strip()

        # https://github.com/ansible/ansible-modules-core/issues/911
        cleaned = cleaned.replace('**:', ':')
        # https://github.com/ansible/ansible-modules-core/issues/633
        if 'feature request' in cleaned.lower():
            cleaned = cleaned.replace('Feature Request', 'Feature Idea')

        hassection = False
        for section in SECTIONS:
            if section in cleaned.title():
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
            if cleaned.startswith('##### ' + section) and not cleaned.endswith(section):
                xlines.append('##### ' + section)
                cleaned = cleaned.replace('##### ' + section, '')
            elif cleaned.startswith('**') and cleaned.endswith('**') and section in cleaned:
                # https://github.com/ansible/ansible-modules-core/issues/143
                cleaned = cleaned.replace('**', '')
                xlines.append('##### ' + section)
                cleaned = cleaned.replace(section, '')
            elif cleaned.startswith(section) and not cleaned.endswith(section):
                # https://github.com/ansible/ansible-modules-core/issues/178
                xlines.append('##### ' + section)
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

    if not 'summary' in tdict:
        if body:
            tdict['summary'] = body
        else:
            tdict['summary'] = ''

    # Fix component names ...
    if not 'component name' in tdict and 'plugin name' in tdict:
        tdict['component name'] = tdict['plugin name']
    if not 'component name' in tdict:
        tdict['component name'] = []
    else:
        newcomps = []
        for x in tdict['component name']:
            x = x.strip()
            if x:
                newcomps.append(x)
        tdict['component name'] = newcomps

    ####################
    # Fix issue types
    ####################

    if not 'issue type' in tdict:
        tdict['issue type'] = []
    elif not tdict['issue type']:
        tdict['issue type'] = []
    tdict['issue type'] = \
        [x.strip() for x in tdict['issue type']]
    tdict['issue type'] = \
        [x for x in tdict['issue type'] if not '<!' in x]
    tdict['issue type'] = \
        [x.lower() for x in tdict['issue type']]

    # narrow down to lines that contain known types
    candidates = []
    for idx,x in enumerate(tdict['issue type']):
        known = False
        for it in ISSUE_TYPES:
            if it in x:
                known = True
        if known:
            candidates.append(x)

    for key in ['issue type', 'component name', 'ansible version']:
        if not key in tdict:
            continue

        tdict[key] = [x.replace(':', '') for x in tdict[key]]
        tdict[key] = [x.replace('*', '') for x in tdict[key]]
        tdict[key] = [x.replace('- ', '') for x in tdict[key]]
        tdict[key] = [x.replace('`', '') for x in tdict[key]]
        tdict[key] = [x.replace('"', '') for x in tdict[key]]
        tdict[key] = [x.replace("'", '') for x in tdict[key]]
        tdict[key] = [x.replace("(", '') for x in tdict[key]]
        tdict[key] = [x.replace(")", '') for x in tdict[key]]
        tdict[key] = [x.replace("[", '') for x in tdict[key]]
        tdict[key] = [x.replace("]", '') for x in tdict[key]]

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

        tdict[key] = [x.strip() for x in tdict[key] if x.strip()]

        if len(tdict[key]) == 0:
            tdict[key] = None
        elif len(tdict[key]) == 1:
            tdict[key] = tdict[key][0]
        elif len(tdict[key]) > 1 and key == 'component name':
            tdict[key] = tdict[key][0]
        elif len(tdict[key]) > 1:
            tdict[key] = '\n'.join(tdict[key])

    return tdict


def remove_markdown_comments(rawtext):
    # Get rid of the comment blocks from the markdown template
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


