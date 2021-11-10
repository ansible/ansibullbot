def get_filament_facts(issuewrapper, meta):
    # https://github.com/ansible/ansible/pull/26921

    iw = issuewrapper
    isfilament = False

    if iw.is_pullrequest():
        if iw.files:
            for fn in iw.files:
                if fn.endswith('filament.py') or fn.endswith('lightbulb.py'):
                    isfilament = True
                    break

    meta['is_filament'] = isfilament
    return meta
