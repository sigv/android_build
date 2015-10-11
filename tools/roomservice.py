#!/usr/bin/env python3
# roomservice: Android device repository management utility.
# Copyright (C) 2013 Cybojenix <anthonydking@gmail.com>
# Copyright (C) 2013 The OmniROM Project
# Copyright (C) 2015 ParanoidAndroid Project
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json
import os
import sys
from urllib.request import urlopen
from xml.etree import ElementTree as ES

local_manifests_dir = '.repo/local_manifests'
remotes = {
    'pa': { 'rem': 'aospa', 'rev': 'marshmallow', 'org': 'AOSPA' }
}

# Indenting code from https://stackoverflow.com/a/4590052
def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def find_repo_name_from_upstream():
    api_url = 'https://api.github.com/search/repositories?q=user:%s+android_device_+_%s+fork:true' % (remote['org'], device)
    response = json.loads(urlopen(api_url).read().decode('utf-8'))

    if not response.get('total_count'):
        raise ValueError('Could not find any possible upstream location of the device tree for %s.' % device)

    for repo in response.get('items'):
        if repo['name'].startswith('android_device_') and repo['name'].endswith('_' + device):
            print('Found the upstream location of the device tree for %s.' % device)
            return repo['name']

    raise ValueError('Could not find a matching upstream location of the device tree for %s.' % device)

def list_projects():
    manifests = []
    for filename in os.listdir(local_manifests_dir):
        manifests.append(os.path.join(local_manifests_dir, filename))
    manifests.append('.repo/manifest.xml')

    for filename in manifests:
        try:
            manifest = ES.parse(filename).getroot()
        except (IOError, ES.ParseError):
            print('Error while parsing manifest (%s).' % filename)
        else:
            for project in manifest.findall('project'):
                yield project

def find_device_path_from_manifest():
    for project in list_projects():
        project_name = project.get('name')
        if project_name.startswith('android_device_') and project_name.endswith('_' + device):
            return project.get('path')
    return None

def find_device_from_directories():
    search_paths = []
    for subdir in os.listdir('device'):
        path = 'device/%s/%s' % (subdir, device)
        if os.path.isdir(path):
            search_paths.append(path)

    if len(search_paths) > 1:
        print('Found multiple device trees for %s. Checking manifests.' % device)
        return find_device_path_from_manifest()
    elif len(search_paths) == 1:
        return search_paths[0]
    else:
        print('Found no device tree for %s. Checking manifests.' % device)
        return find_device_path_from_manifest()

def append_manifest_project(path, name, remote, revision):
    manifest_path = local_manifests_dir + '/roomservice.xml'

    try:
        manifest = ES.parse(manifest_path).getroot()
    except (IOError, ES.ParseError):
        manifest = ES.Element('manifest')

    found_project = False
    modified_project = False
    for project in manifest.findall('project'):
        if project.get('name') == name:
            found_project = True
            if project.get('path') != path:
                modified_project = True
                project.set('path', path)
            if project.get('remote') != remote:
                modified_project = True
                project.set('remote', remote)
            if project.get('revision') != revision:
                modified_project = True
                project.set('revision', revision)
            break
    if not found_project:
        found_project = True
        modified_project = True
        manifest.append(ES.Element('project', attrib = {
            'path': path,
            'name': name,
            'remote': remote,
            'revision': revision
        }))

    indent(manifest)
    open(manifest_path, 'w').write('\n'.join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!-- You should probably let Roomservice deal with this unless you know what you are doing. -->',
        ES.tostring(manifest).decode()
    ]))

    return modified_project

if __name__ == '__main__':
    if not os.path.isdir(local_manifests_dir):
        os.mkdir(local_manifests_dir)

    if len(sys.argv) <= 1:
        raise ValueError('First argument must be the product.')
    product = sys.argv[1]

    try:
        product_divider_index = product.index('_')
    except ValueError:
        raise ValueError('Error while parsing the product (%s).' % product)

    remote = product[:product_divider_index]
    if remote in remotes:
        remote = remotes[remote]
    else:
        raise ValueError('Could not find the remote (%s).' % remote)

    device = product[product_divider_index + 1:]

    if not find_device_from_directories():
        repo_name = find_repo_name_from_upstream()
        target_directory = repo_name[len('android_'):].replace('_', '/')

        if append_manifest_project(path = target_directory, name = repo_name, remote = remote['rem'], revision = remote['rev']):
            print('Syncing the device tree.')
            if os.system('repo sync --force-broken --quiet --no-clone-bundle %s' % target_directory) != 0:
                raise ValueError('Unexpected exit status from the sync process.')

    device_tree_directory = find_device_from_directories()
    if device_tree_directory is None or not os.path.isdir(device_tree_directory):
        raise ValueError('Device tree could not be found for the device (%s).' % device)

    dependencies_path = device_tree_directory + '/dependencies.json'
    if not os.path.isfile(dependencies_path):
        raise ValueError('No dependencies file could be found for the device (%s).' % device)

    dependencies = json.loads(open(dependencies_path, 'r').read())
    appended_projects = []

    for dependency in dependencies:
        target_directory = dependency.get('path')
        if append_manifest_project(path = target_directory, name = dependency.get('repo'), remote = dependency.get('remote'), revision = dependency.get('revision')):
            appended_projects.append(target_directory)

    if len(appended_projects) > 0:
        print('Syncing the dependencies.')
        if os.system('repo sync --force-broken --quiet --no-clone-bundle %s' % ' '.join(appended_projects)) != 0:
            raise ValueError('Unexpected exit status from the sync process.')
