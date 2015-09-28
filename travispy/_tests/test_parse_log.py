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

    print('     wrote {0} with {1} chars'.format(filename, len(job.log.body)))


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

        # block 1 is normally system_info
        assert block_names[1] == 'git'

        assert 'before_install' in block_names
        assert 'install' in block_names
        assert 'script' in block_names

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
            '_container_notice', 'rvm', '_versions', 'script']

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
        assert '_travis_yml_environment_settings' in block_names



