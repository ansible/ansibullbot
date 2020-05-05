#!/usr/bin/env python

import os.path


# https://github.com/ansible/ansible/pull/46028
# https://github.com/ansible/ansible/pull/68449
# https://github.com/ansible/ansible/pull/69299
# https://github.com/ansible/ansible/pull/69280
# https://github.com/ansible/ansible/pull/69326


def get_test_support_plugins_facts(iw, component_matcher):
    tmeta = {
        u'test_support_plugins': {}
    }

    if not (iw.is_pullrequest() and iw.files):
        return tmeta

    for fn in iw.files:
        if not fn.startswith(u'test/support/'):
            continue

        tmeta[u'test_support_plugins'][fn] = []

        try:
            plugin_path = fn.split('plugins/')[1]
        except IndexError:
            # not a plugin
            continue

        plugin_path_parts = plugin_path.split('/')
        flatten_plugin_path = os.path.join(plugin_path_parts[0], plugin_path_parts[-1])

        for pattern in (plugin_path, flatten_plugin_path):
            collections = component_matcher.search_ecosystem(pattern)
            for collection_data in collections:
                collection_name = collection_data.split(':')[1]
                if collection_name not in tmeta[u'test_support_plugins'][fn]:
                    tmeta[u'test_support_plugins'][fn].append(collection_name)

    return tmeta
