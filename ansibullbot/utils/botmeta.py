def botmeta_list(inlist):
    '''use the bot's expansion of space separated lists feature'''
    if not isinstance(inlist, list):
        return inlist
    # can't join words with spaces in them
    if [x for x in inlist if ' ' in x]:
        return inlist
    else:
        return ' '.join(sorted([x.strip() for x in inlist if x.strip()]))
