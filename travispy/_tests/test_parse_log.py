from travispy import TravisPy
from travispy._log_parser import *
from travispy.errors import ParseError

import pytest

from travispy._tests.test_travispy import GITHUB_ACCESS_TOKEN


class Test:

    def setup_method(self, method):
        if GITHUB_ACCESS_TOKEN:
            self._travis = TravisPy.github_auth(GITHUB_ACCESS_TOKEN)
        else:
            self._travis = TravisPy()

    def test_empty_archived_log(self):
        job = self._travis.job(81891594)
        log = job.log

        assert log.body == ''
        assert log._parse() == {}

    def test_cancelled_1_log(self):
        job = self._travis.job(81233866)
        log = job.log

        assert log.body != ''
        assert log._parse() == {}

    def test_corrupt_log(self):
        job = self._travis.job(81896198)
        log = job.log

        assert log.body != ''

        with pytest.raises(ParseError) as exception_info:
            log._parse()

    def test_old_log_structure(self):
        job = self._travis.job(32052931)

        config = job.config

        assert 'before_install' in config
        assert 'install' in config
        assert 'script' in config

        log = job.log

        assert log.body != ''

        blocks = log._parse()
        block_names = list(name for name in blocks.keys() if not name.startswith('_unexpected_blank_lines'))

        # block 1 is normally system_info
        assert block_names[1] == 'git'

        assert 'before_install' in block_names
        assert 'install' in block_names
        assert 'script' in block_names

    def test_install_then_auto_script(self):
        job = self._travis.job(78700066)

        config = job.config

        assert 'before_install' in config
        assert 'install' in config
        assert 'script' in config

        log = job.log

        assert log.body != ''

        blocks = log._parse()
        block_names = list(name for name in blocks.keys() if not name.startswith('_unexpected_blank_lines'))

        assert block_names[0:3] == [
            '_worker', 'system_info', 'git.checkout']
        assert 'before_install' in block_names
        assert 'install' in block_names
        assert 'script' in block_names

    def test_default_yml(self):
        job = self._travis.job(81487027)

        config = job.config

        assert config['.result'] == 'not_found'

        log = job.log

        assert log.body != ''

        blocks = log._parse()
        block_names = list(name for name in blocks.keys() if not name.startswith('_unexpected_blank_lines'))

        assert 'script' in block_names

        assert block_names == [
            '_no_travis_yml_warning', '_worker', '_standard_configuration_warning',
            'system_info', 'git.checkout',
            '_container_notice', 'rvm', '_versions', 'script']

    def test_submodule_checkout_failed(self):
        job = self._travis.job(81524549)
        log = job.log

        assert log.body != ''

        blocks = log._parse()
        block_names = list(name for name in blocks.keys() if not name.startswith('_unexpected_blank_lines'))

        assert block_names == [
            '_no_travis_yml_warning', '_worker', '_standard_configuration_warning',
            'system_info', 'git.checkout', 'git.submodule', '_job_stopped']

    def test_travis_yml_envvars(self):
        job = self._travis.job(48245860)
        log = job.log

        assert log.body != ''

        blocks = log._parse()
        block_names = list(name for name in blocks.keys() if not name.startswith('_unexpected_blank_lines'))
       
        assert block_names[0:4] == ['_worker', 'system_info', 'git.checkout', 'git.submodule']
        assert '_travis_yml_environment_settings' in block_names



