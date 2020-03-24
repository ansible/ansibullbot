#!/usr/bin/env python

import itertools
import logging
import os

from string import Template

import yaml

import six

import ansibullbot.constants as C
from ansibullbot._text_compat import to_text


__metaclass__ = type  # Turn all classes into new-style by default


# https://github.com/ansible/ansibullbot/issues/1155#issuecomment-457731630
class NoAliasDumper(yaml.Dumper):
    def ignore_aliases(self, data):
        return True


class BotMetadataParser:

    @staticmethod
    def parse_yaml(data):

        def clean_list_items(inlist):
            if isinstance(inlist, list):
                inlist = to_text(inlist)
            if u'&' in inlist:
                if C.DEFAULT_BREAKPOINTS:
                    logging.error(u'breakpoint!')
                    import epdb; epdb.st()
            inlist = inlist.replace(u"[", u'')
            inlist = inlist.replace(u"]", u'')
            inlist = inlist.replace(u"'", u'')
            inlist = inlist.replace(u",", u'')
            inlist = inlist.split()
            return inlist

        def join_if_list(list_or_str):
            if not isinstance(list_or_str, list):
                return list_or_str

            return u' '.join(list_or_str)

        def fix_lists(data):
            string_macros = {
                k: join_if_list(v)
                for k, v in data[u'macros'].items()
            }
            for k, v in data[u'files'].items():
                if v is None:
                    continue

                for k2, v2 in v.items():
                    if isinstance(v2, six.text_type) and u'$' in v2:
                        tmpl = Template(v2)
                        newv2 = tmpl.substitute(**string_macros)
                        newv2 = clean_list_items(newv2)
                        data[u'files'][k][k2] = newv2
                        v2 = newv2

                    if isinstance(v2, six.text_type):
                        data[u'files'][k][k2] = v2.split()

            return data

        def fix_keys(data):
            replace = []
            for k in data[u'files'].keys():
                if u'$' in k:
                    replace.append(k)
            for x in replace:
                tmpl = Template(x)
                newkey = tmpl.substitute(**data[u'macros'])
                data[u'files'][newkey] = data[u'files'][x]
                data[u'files'].pop(x, None)

            paths = list(data[u'files'].keys())
            for p in paths:
                normpath = os.path.normpath(p)
                if p != normpath:
                    metadata = data[u'files'].pop(p)
                    data[u'files'][normpath] = metadata
            return data

        def extend_labels(data):
            for k, v in data[u'files'].items():
                # labels from path(s)
                if v is None:
                    continue
                labels = v.get(u'labels', [])
                if isinstance(labels, six.text_type):
                    labels = labels.split()
                    labels = [x.strip() for x in labels if x.strip()]
                path_labels = [x.strip() for x in k.split(u'/') if x.strip()]
                for x in path_labels:
                    x = x.replace(u'.py', u'')
                    x = x.replace(u'.ps1', u'')
                    if x not in labels:
                        labels.append(x)
                data[u'files'][k][u'labels'] = sorted(set(labels))

            return data

        def fix_teams(data):
            for k, v in data[u'macros'].items():
                if v is None:
                    continue
                if not k.startswith(u'team_') or isinstance(v, list):
                    continue
                names = v.split()
                data[u'macros'][k] = names
            return data

        def _propagate(files, top, child, field, multivalued=True):
            '''Copy key named 'field' from top to child
            - with multivalued, child inherits from all ancestors
            - else child inherits from the nearest ancestor and only if field is
              not already set at child level
            '''
            top_entries = files[top].get(field, [])
            if top_entries:
                if field not in files[child]:
                    files[child][field] = []

                # track the origin of the data
                field_keys = u'%s_keys' % field
                if field_keys not in files[child]:
                    files[child][field_keys] = []

                if multivalued:
                    files[child][field_keys].append(top)
                    for entry in top_entries:
                        if entry not in files[child][field]:
                            files[child][field].append(entry)
                elif not files[child][field] or (files[child][field_keys] and len(files[child][field_keys][0]) < len(top)):
                    # use parent keyword only if:
                    # 1. either keyword is not set
                    # 2. or keyword has been already inherited from a less specific path
                    files[child][field_keys] = [top]
                    files[child][field] = top_entries[:]

        def propagate_keys(data):
            files = data[u'files']
            '''maintainers and ignored keys defined at a directory level are copied to subpath'''

            iterfiles = {}
            filenames = sorted(list(files.keys()))
            parent = None
            for idp,parent in enumerate(filenames):

                if parent not in iterfiles:
                    iterfiles[parent] = []

                started = False
                for fn in filenames[idp:]:
                    if parent == fn:
                        continue
                    if fn.startswith(parent):
                        started = True
                        iterfiles[parent].append(fn)
                    elif started:
                        break

            for file1, files2 in iterfiles.items():
                for file2 in files2:
                    # Python 2.7 doesn't provide os.path.commonpath
                    common = os.path.commonprefix([file1, file2])
                    top = min(file1, file2)
                    child = max(file1, file2)

                    top_components = top.split(u'/')
                    child_components = child.split(u'/')

                    _propagate(files, top, child, u'maintainers')
                    _propagate(files, top, child, u'ignored')
                    _propagate(files, top, child, u'labels')
                    _propagate(files, top, child, u'support', multivalued=False)
                    _propagate(files, top, child, u'supported_by', multivalued=False)

        #################################
        #   PARSE
        #################################

        # https://github.com/ansible/ansibullbot/issues/1155#issuecomment-457731630
        logging.info('load yaml')
        ydata_orig = yaml.load(data, BotYAMLLoader)
        ydata = yaml.load(yaml.dump(ydata_orig, Dumper=NoAliasDumper), BotYAMLLoader)

        # fix the team macros
        logging.info('fix teams')
        ydata = fix_teams(ydata)

        # fix the macro'ized file keys
        logging.info('fix keys')
        ydata = fix_keys(ydata)

        logging.info('iterate files')
        for k, v in ydata[u'files'].items():
            if v is None:
                # convert empty val in dict
                ydata[u'files'][k] = {}
                continue

            if isinstance(v, six.binary_type):
                v = to_text(v)

            if isinstance(v, six.text_type):
                # convert string vals to a maintainers key in a dict
                ydata[u'files'][k] = {
                    u'maintainers': v
                }

            ydata[u'files'][k][u'maintainers_keys'] = [k]

        # replace macros in files section
        logging.info('fix lists')
        ydata = fix_lists(ydata)

        # extend labels by filepath
        logging.info('extend labels')
        ydata = extend_labels(ydata)

        logging.info('propogate keys')
        propagate_keys(ydata)

        return ydata


def construct_yaml_str(self, node):
    # Override the default string handling function
    # to always return unicode objects

    # Taken from https://stackoverflow.com/a/2967461/595220
    return self.construct_scalar(node)


def default_to_unicode_strings(cls):
    cls.add_constructor(u'tag:yaml.org,2002:str', construct_yaml_str)
    return cls


@default_to_unicode_strings
class BotYAMLLoader(yaml.Loader):
    pass


@default_to_unicode_strings
class BotSafeYAMLLoader(yaml.SafeLoader):
    pass
