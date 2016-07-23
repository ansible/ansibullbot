#!/usr/bin/env python

def extract_template_data(body):
    """Extract templated data from an issue body"""

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

def get_template_data(self):
    """Extract templated data from an issue body"""

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

    body = self.instance.body
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

    import epdb; epdb.st()
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


