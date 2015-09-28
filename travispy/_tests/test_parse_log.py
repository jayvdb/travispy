from __future__ import absolute_import, unicode_literals

import codecs
import glob
import os

from travispy import TravisPy
from travispy.entities import Log
from travispy._log_parser import *
from travispy.errors import ParseError

import pytest

from travispy._tests.test_travispy import GITHUB_ACCESS_TOKEN


test_data_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'test_data')


def split_extended_slug(slug):
    """Return user, project, build and job."""
    if not slug:
        return None, None, 0, 0

    parts = slug.rsplit('/')

    if len(parts) == 1:
        return parts[0], None, 0, 0
    elif len(parts) == 2:
        return parts[0], parts[1], 0, 0

    build_id, sep, job_id = parts[2].partition('.')
    build_id = int(build_id)
    if job_id:
        job_id = int(job_id)

    return parts[0], parts[1], build_id, job_id


def get_job(t, extended_slug):
    user, project, build_id, job_id = split_extended_slug(extended_slug)
    assert job_id

    repo = t.repo(user + '/' + project)

    builds = t.builds(slug=repo.slug, after_number=build_id + 1)
    build = builds[0]
    assert int(build.number) == build_id

    build = t.build(build.id)

    for build_job in build.jobs:
        build_id, build_job_number = build_job.number.split('.')
        if int(build_job_number) == job_id:
            return build_job
    raise RuntimeError('unable to get job for {0}'.format(extended_slug))


def get_filename(extended_slug):
    """Get filename for extended slug."""
    user, project, build_id, job_id = split_extended_slug(extended_slug)

    if None in (user, project, build_id, job_id):  # todo; remove this
        return

    filename_glob = os.path.join(
        test_data_dir,
        user, project,
        '{0}.{1}-*'.format(build_id, job_id))
    filenames = glob.glob(filename_glob)
    if filenames:
        return filenames[0]
    else:
        return None


def save_job_log(job):
    user, project = job.repository.slug.split('/')
    filename = os.path.join(
        test_data_dir,
        user, project,
        '{0}-{1}.txt'.format(job.number, job.state))

    assert not os.path.exists(filename)
    with open(filename, 'wb') as f:
        f.write(job.log.body)

    print('     wrote {0} ({1}) with {2} chars'.format(filename, job.id, len(job.log.body)))


class Test:

    def setup_method(self, method):
        if GITHUB_ACCESS_TOKEN:
            self._travis = TravisPy.github_auth(GITHUB_ACCESS_TOKEN)
        else:
            self._travis = TravisPy()

    def _get_job_log(self, extended_slug=None, job_id=None):
        """Get a job log."""
        filename = get_filename(extended_slug)
        if filename:
            file = codecs.open(filename, 'r', 'utf-8')
            log = Log.from_file(file)
            if not job_id:
                job = get_job(self._travis, extended_slug)
                print('set job_id={0}'.format(job.id))
        else:
            job = self._travis.job(job_id)
            save_job_log(job)
            log = job.log

        return log

    def test_empty_archived_log(self):
        log = self._get_job_log('jayvdb/pywikibot-core/1240.15', job_id=81891594)

        assert log.body == ''
        assert log._parse() == {}

    def test_cancelled_1_log(self):
        log = self._get_job_log('jayvdb/pywikibot-core/1229.7', job_id=81233866)

        assert log.body != ''
        assert log._parse() == {}

    def test_cancelled_2_log(self):
        log = self._get_job_log('jayvdb/pywikibot-core/1210.9', job_id=81215691)

        assert log.body != ''
        assert log._parse() != {}

    def test_corrupt_log(self):
        log = self._get_job_log('jayvdb/pywikibot-core/1242.10', job_id=81896198)

        assert log.body != ''

        with pytest.raises(ParseError) as exception_info:
            log._parse()

    def test_old_log_structure(self):
        log = self._get_job_log('legoktm/pywikibot-core/3.1', job_id=32052931)

        assert log.body != ''

        blocks = log._parse()
        block_names = list(name for name in blocks.keys() if not name.startswith('_unexpected_blank_lines'))

        assert block_names[0] == '_worker'
        assert '_worker' in blocks
        block = blocks['_worker']

        assert len(block.elements) == 2
        assert isinstance(block.elements[0], Note)
        assert len(block.elements[0].lines) == 1
        assert block.elements[0].lines[0] == 'Using worker: worker-linux-7-2.bb.travis-ci.org:travis-linux-13'
        assert isinstance(block.elements[1], BlankLine)

        assert 'before_install' in block_names
        assert 'install' in block_names
        assert 'script' in block_names

        assert block_names[1] == 'git'
        assert 'git' in blocks
        block = blocks['git']

        assert len(block.elements) == 5

        assert isinstance(block.elements[0], TimedCommand)
        command = block.elements[0]
        assert command.identifier == '1128f657'
        assert command.executed == 'git clone --depth=50 --branch=patch-1 git://github.com/legoktm/pywikibot-core.git legoktm/pywikibot-core'

        assert isinstance(block.elements[4], TimedCommand)
        command = block.elements[4]
        assert command.identifier == '10de8135'
        assert command.executed == 'git submodule update'
        assert command.start == 1407532617445904815
        assert command.finish == 1407532619646888411
        assert command.duration == 2200983596

        assert block_names[2] == '_travis_yml_environment_variables'
        assert '_travis_yml_environment_variables' in blocks
        block = blocks['_travis_yml_environment_variables']

        assert isinstance(block, TravisYmlEnvironmentVariables)
        assert len(block.elements) == 4
        assert isinstance(block.elements[0], Note)
        assert len(block.elements[0].lines) == 1
        assert 'Setting environment variables from .travis.yml' in block.elements[0].lines[0]
        assert isinstance(block.elements[1], UntimedCommand)
        assert len(block.elements[1].lines) == 1
        assert block.elements[1].executed == 'export LANGUAGE=en'
        assert len(block.elements[1].lines) == 1
        assert isinstance(block.elements[2], UntimedCommand)
        assert block.elements[2].executed == 'export FAMILY=wikipedia'
        assert isinstance(block.elements[3], BlankLine)

        assert block_names[3] == '_activate'
        assert '_activate' in blocks
        block = blocks['_activate']

        assert isinstance(block.elements[0], Command)
        assert len(block.elements[0].lines) == 1
        assert block.elements[0].executed == 'source ~/virtualenv/python2.7/bin/activate'
        assert block.elements[0].exit_code is None

        assert block_names[4] == '_versions-timed'
        assert '_versions-timed' in blocks
        block = blocks['_versions-timed']

        assert isinstance(block, CommandBlock)
        assert len(block.elements) == 2
        assert isinstance(block.elements[0], TimedCommand)
        assert len(block.elements[0].lines) == 2
        assert block.elements[0].executed == 'python --version'
        assert block.elements[0].lines[1] == 'Python 2.7.8'
        assert block.elements[0].exit_code is None

        assert isinstance(block.elements[1], TimedCommand)
        assert len(block.elements[1].lines) == 2
        assert block.elements[1].executed == 'pip --version'
        assert block.elements[1].lines[1] == 'pip 1.5.4 from /home/travis/virtualenv/python2.7.8/lib/python2.7/site-packages (python 2.7)'

        assert block_names[5] == 'before_install'
        assert 'before_install' in blocks
        block = blocks['before_install']

        assert len(block.elements) == 2

        assert isinstance(block.elements[0], Command)
        assert len(block.elements[0].lines) == 1
        assert block.elements[0].executed == 'sudo apt-get update -qq'
        assert block.elements[0].exit_code is None
        assert block.elements[1].executed == 'sudo apt-get install -y python-imaging-tk liblua5.1-dev'

        assert block_names[6] == 'install'
        assert 'install' in blocks
        block = blocks['install']

        assert len(block.elements) == 22

        assert isinstance(block.elements[0], Command)
        assert len(block.elements[0].lines) == 1
        assert block.elements[0].executed == "if [[ $TRAVIS_PYTHON_VERSION == '2.6' ]]; then pip install ordereddict; fi"
        assert block.elements[21].executed == 'cd ../..'

        assert block.elements[0].exit_code is None

        assert block_names[7] == 'script'
        assert 'script' in blocks
        block = blocks['script']

        assert len(block.elements) == 1
        assert isinstance(block.elements[0], Command)
        assert len(block.elements[0].lines) == 94
        assert block.elements[0].executed == """if [ -n "$USER_PASSWORD" ]; then python setup.py test; else PYWIKIBOT2_NO_USER_CONFIG=1 nosetests -a '!site,!net' -v ; fi"""
        assert 'Ran 85 tests in 34.679s' in block.elements[0].lines
        assert 'OK (SKIP=2)' in block.elements[0].lines

        # This is not correct
        assert block.elements[0].lines[-5:] == ['Ran 85 tests in 34.679s', '', 'OK (SKIP=2)', '\x1b[0K', '']

        assert block.elements[0].exit_code == 0

        assert block_names[8] == '_done'
        assert '_done' in blocks
        block = blocks['_done']

        assert isinstance(block, Done)
        assert block.exit_code == 0
        assert len(block.elements) == 1
        assert isinstance(block.elements[0], Note)
        assert block.elements[0].lines[0] == 'Done. Your build exited with 0.'

        assert len(block_names) == 9

    def test_install_then_auto_script(self):
        log = self._get_job_log('jayvdb/pywikibot-i18n/5.1', job_id=78700066)

        assert log.body != ''

        blocks = log._parse()
        block_names = list(name for name in blocks.keys() if not name.startswith('_unexpected_blank_lines'))

        assert block_names[0:3] == [
            '_worker', 'system_info', 'git.checkout']
        assert 'before_install' in block_names
        assert 'install' in block_names
        assert 'script' in block_names

    def test_default_yml(self):
        log = self._get_job_log('jayvdb/citeproc-test/13.1', job_id=81487027)

        assert log.body != ''

        blocks = log._parse()
        block_names = list(name for name in blocks.keys() if not name.startswith('_unexpected_blank_lines'))

        assert 'script' in block_names

        assert block_names == [
            '_no_travis_yml_warning', '_worker', '_standard_configuration_warning',
            'system_info', 'git.checkout',
            '_container_notice', 'rvm', '_versions', 'script', '_done']

    def test_submodule_checkout_failed(self):
        log = self._get_job_log('jayvdb/citeproc-py/20.1', job_id=81524549)

        assert log.body != ''

        blocks = log._parse()
        block_names = list(name for name in blocks.keys() if not name.startswith('_unexpected_blank_lines'))

        assert block_names == [
            '_no_travis_yml_warning', '_worker', '_standard_configuration_warning',
            'system_info', 'git.checkout', 'git.submodule', '_job_stopped']

    def test_travis_yml_envvars(self):
        log = self._get_job_log('hks73/pywikibot-core/2.7', job_id=48245860)

        assert log.body != ''

        blocks = log._parse()
        block_names = list(name for name in blocks.keys() if not name.startswith('_unexpected_blank_lines'))

        assert block_names[0:4] == ['_worker', 'system_info', 'git.checkout', 'git.submodule']
        assert '_travis_yml_environment_variables' in block_names



