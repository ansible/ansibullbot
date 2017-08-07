# -*- coding: utf-8 -*-

from setuptools import setup, find_packages


with open('README.md') as f:
    readme = f.read()

with open('LICENSE') as f:
    license = f.read()

setup(
    name='ansibullbot',
    version='0.1.0',
    description='github triage bot',
    long_description=readme,
    author='James Tanner',
    author_email='tanner.jc@gmail.com',
    url='https://github.com/ansible/ansibullbot',
    license=license,
    packages=find_packages(exclude=('test')),
    setup_requires=['nose>=1.3'],
)
