#!/usr/bin/env python
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible. If not, see <http://www.gnu.org/licenses/>.
#
# The following code is a derivative work of the code from the Ansible project,
# which is licensed GPLv3. This code therefore is also licensed under the terms
# of the GNU Public License, version 3.

import sys
import tempfile
import os

from six import string_types
from six.moves import configparser

PROG_NAME = 'ansibullbot'
BOOL_TRUE = frozenset(["true", "t", "y", "1", "yes", "on"])


def mk_boolean(value):
    ret = value
    if not isinstance(value, bool):
        if value is None:
            ret = False
        ret = (str(value).lower() in BOOL_TRUE)
    return ret


def to_text(value, errors=None, nonstring=None):
    return str(value)


def unquote(value):
    return value.replace('"', '').replace("'", '')


def shell_expand(path, expand_relative_paths=False):
    '''
    shell_expand is needed as os.path.expanduser does not work
    when path is None, which is the default for ANSIBLE_PRIVATE_KEY_FILE
    '''
    if path:
        path = os.path.expanduser(os.path.expandvars(path))
        if expand_relative_paths and not path.startswith('/'):
            # paths are always 'relative' to the config?
            if 'CONFIG_FILE' in globals():
                CFGDIR = os.path.dirname(CONFIG_FILE)
                path = os.path.join(CFGDIR, path)
            path = os.path.abspath(path)
    return path


def get_config(p, section, key, env_var, default,
               value_type=None, expand_relative_paths=False):
    ''' return a configuration variable with casting

    :arg p: A ConfigParser object to look for the configuration in
    :arg section: A section of the ini config to examine.
    :arg key: The config key to get this config from
    :arg env_var: An Environment variable to check for the config var.  If
        this is set to None then no environment variable will be used.
    :arg default: A default value to assign to the config var.
    :kwarg value_type: The type of the value.  This can be any of:
        :boolean: sets the value to a True or False value
        :integer: Sets the value to an integer or raises a ValueType error
        :float: Sets the value to a float or raises a ValueType error
        :list: Treats the value as a comma separated list.  Split the value
            and return it as a python list.
        :none: Sets the value to None
        :path: Expands any environment variables and tilde's in the value.
        :tmp_path: Create a unique temporary directory inside of the directory
            specified by value and return its path.
        :pathlist: Treat the value as a typical PATH string.  (On POSIX, this
            means colon separated strings.)  Split the value and then expand
            each part for environment variables and tildes.
    :kwarg expand_relative_paths: for pathlist and path types, if this is set
        to True then also change any relative paths into absolute paths.  The
        default is False.
    '''
    value = _get_config(p, section, key, env_var, default)
    if value_type == 'boolean':
        value = mk_boolean(value)

    elif value:
        if value_type == 'integer' or value_type == 'int':
            value = int(value)

        elif value_type == 'float':
            value = float(value)

        elif value_type == 'list':
            if isinstance(value, string_types):
                value = [x.strip() for x in value.split(',')]

        elif value_type == 'none':
            if value == "None":
                value = None

        elif value_type == 'path':
            value = shell_expand(
                value,
                expand_relative_paths=expand_relative_paths
            )

        elif value_type == 'tmppath':
            value = shell_expand(value)
            if not os.path.exists(value):
                os.makedirs(value)
            prefix = '%s-local-%s' % (PROG_NAME, os.getpid())
            value = tempfile.mkdtemp(prefix=prefix, dir=value)

        elif value_type == 'pathlist':
            if isinstance(value, string_types):
                value = [
                    shell_expand(
                        x,
                        expand_relative_paths=expand_relative_paths
                    ) for x in value.split(os.pathsep)]

        elif isinstance(value, string_types):
            value = unquote(value)

    return to_text(value, errors='surrogate_or_strict', nonstring='passthru')


def _get_config(p, section, key, env_var, default):
    ''' helper function for get_config '''
    value = default

    if p is not None:
        try:
            value = p.get(section, key, raw=True)
        except:
            pass

    if env_var is not None:
        env_value = os.environ.get(env_var, None)
        if env_value is not None:
            value = env_value

    return to_text(value, errors='surrogate_or_strict', nonstring='passthru')


def load_config_file():
    ''' Load Config File order(first found is used):
        ENV,CWD,HOME, /etc/ansible '''

    p = configparser.ConfigParser()

    path0 = os.getenv("%s_CONFIG" % PROG_NAME.upper(), None)
    if path0 is not None:
        path0 = os.path.expanduser(path0)
        if os.path.isdir(path0):
            path0 += "/%s.cfg" % PROG_NAME
    try:
        path1 = os.getcwd() + "/%s.cfg" % PROG_NAME
    except OSError:
        path1 = None
    path2 = os.path.expanduser("~/.%s.cfg" % PROG_NAME)
    path3 = "/etc/%s/%s.cfg" % (PROG_NAME, PROG_NAME)

    for path in [path0, path1, path2, path3]:
        if path is not None and os.path.exists(path):
            try:
                p.read(path)
            except configparser.Error as e:
                print("Error reading config file: \n{0}".format(e))
                sys.exit(1)
            return p, path
    return None, ''


p, CONFIG_FILE = load_config_file()

# check all of these extensions when looking for yaml files for things like
# group variables -- really anything we can load
YAML_FILENAME_EXTENSIONS = ["", ".yml", ".yaml", ".json"]

# sections in config file
DEFAULTS = 'defaults'

DEFAULT_DEBUG = get_config(
    p,
    DEFAULTS,
    'debug',
    '%s_DEBUG' % PROG_NAME.upper(),
    False,
    value_type='string'
)

DEFAULT_GITHUB_USERNAME = get_config(
    p,
    DEFAULTS,
    'github_username',
    '%s_GITHUB_USERNAME' % PROG_NAME.upper(),
    False,
    value_type='string'
)

DEFAULT_GITHUB_PASSWORD = get_config(
    p,
    DEFAULTS,
    'github_password',
    '%s_GITHUB_PASSWORD' % PROG_NAME.upper(),
    False,
    value_type='string'
)

DEFAULT_GITHUB_TOKEN = get_config(
    p,
    DEFAULTS,
    'github_token',
    '%s_GITHUB_TOKEN' % PROG_NAME.upper(),
    False,
    value_type='string'
)

DEFAULT_SHIPPABLE_TOKEN = get_config(
    p,
    DEFAULTS,
    'shippable_token',
    '%s_SHIPPABLE_TOKEN' % PROG_NAME.upper(),
    False,
    value_type='string'
)

DEFAULT_NEEDS_INFO_WARN = get_config(
    p,
    'needs_info',
    'warn',
    '%s_NEEDS_INFO_WARN' % PROG_NAME.upper(),
    30,
    value_type='int'
)

DEFAULT_NEEDS_INFO_EXPIRE = get_config(
    p,
    'needs_info',
    'expire',
    '%s_NEEDS_INFO_EXPIRE' % PROG_NAME.upper(),
    60,
    value_type='int'
)

# How many days till a re-triage is forced
DEFAULT_STALE_WINDOW = get_config(
    p,
    DEFAULTS,
    'stale_window',
    '%s_STALE_WINDOW' % PROG_NAME.upper(),
    7,
    value_type='int'
)
