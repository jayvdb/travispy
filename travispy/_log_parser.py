'''Parse travis log files.'''
# For the tokens used in log files, see
# https://github.com/travis-ci/travis-build/blob/master/lib/travis/build/templates/header.sh

from __future__ import absolute_import, unicode_literals

import os
import regex
import sys

from travispy import ParseError, TravisLogCorrupt


def remove_unprintable(s):
    return regex.sub('[^[:print:]\x1b\n]', '', s)


def remove_ansi_color(s):
    return regex.sub('\x1b[^mK]*[mK]', '', s)


class Command(object):

    """Executed command."""

    def __init__(self, identifier):
        """Constructor."""
        self.identifier = identifier
        self.start = self.end = self.duration = None
        self.lines = []

    def __repr__(self):
        return self.lines[0] if self.lines else '<empty command>'


class Block(object):

    """Travis log block."""

    def __init__(self, name):
        """Constructor."""
        self.name = name
        self.lines = []
        self.commands = []

    def __eq__(self, other):
        return self.name == other

    def __len__(self):
        if not self.lines and not self.commands:
            return 0

        if self.lines and self.commands:
            raise ParseError('block with lines and commands: {0!r}'.format(self))

        assert bool(self.lines) != bool(self.commands)

        if self.lines:
            return len(self.lines)
        else:
            return len(self.commands)

    def __repr__(self):
        if not self.lines and not self.commands:
            return '<empty block {0}>'.format(self.name)

        if self.lines and self.commands:
              # TODO: raise exception
            return '<mixed block {0} ({1} lines & {2} commands): {3}\n{4}'.format(self.name, len(self.lines), len(self.commands), self.lines, self.commands)

        assert bool(self.lines) != bool(self.commands)
        if self.commands:
            lines = self.commands[0].lines
        else:
            lines = self.lines

        max_lines = min(len(lines), 3)

        show_lines = [remove_ansi_color(line)
                      for line in lines[:max_lines]]

        if len(lines) <= max_lines:
            return '<block {0} ({1} lines): {2}>'.format(self.name, len(lines), show_lines)
        else:
            return '<block {0} ({1} lines): {2}..>'.format(self.name, len(lines), show_lines)


class LogParser(object):

    '''Parse a log file.'''

    def __init__(self, *args, **kwargs):
        super(LogParser, self).__init__()

    @classmethod
    def from_file(cls, file):
        obj = cls(session=None)
        obj._body = file.read()
        return obj

    @property
    def body(self):
        return self._body

    def colorized(self):
        return remove_unprintable(self.body)

    def clean(self):
        return remove_ansi_color(self.colorized())

    def _parse(self):
        if not self.body:
            return []

        no_system_info = False

        if 'travis_fold:start:system_info' not in self.body[:400]:
            if len(self.body) < 400:
                lines = self.body.strip().splitlines()
                # remove blank lines
                lines = [line for line in lines if line]
                if lines[0].startswith('Using worker: '):
                    lines = lines[1:]
                if len(lines) == 1 and lines[0] == 'Done: Job Cancelled':
                    return []
            else:
                if 'travis_fold:start:system_info' in self.body:
                    # See https://github.com/travis-ci/travis-ci/issues/4848
                    raise TravisLogCorrupt
                elif 'travis_fold:start:git' in self.body[:400]:
                    no_system_info = True
                else:
                    raise ParseError('header not found')

        blocks = []

        lines = self.body.splitlines()

        current_block = Block('_header')
        current_command = None
        timer_id = None
        default_yml = False

        for line in lines:
            nocolor_line = remove_ansi_color(line)
            if nocolor_line.startswith('travis_time:start:'):
                timer_id = nocolor_line[len('travis_time:start:'):]
                assert timer_id

                if current_block is None:
                    if blocks[-1].name.partition('.')[0] in ['before_script', 'install']:
                        current_block = Block('script')
                        blocks.append(current_block)
                    elif no_system_info and len(blocks) == 2 and blocks[1].name == 'git' and len(blocks[1].commands) == 2 and len(blocks[1].lines) == 1 and '$ git checkout -qf ' in blocks[1].lines[0]:
                        # block 0 is _worker
                        current_command = Command(timer_id)
                        blocks[1].commands.append(current_command)
                        current_command.lines = [blocks[1].lines[0]]
                        blocks[1].lines = []
                        continue
                    else:
                        print(blocks)
                        raise ParseError('unexpected start: {0}'.format(line))

                current_command = Command(timer_id)
                current_block.commands.append(current_command)
            elif nocolor_line.startswith('travis_time:end:'):
                assert current_command
                data = nocolor_line[len('travis_time:end:'):]
                end_timer_id, parameters = data.split(':', 1)

                assert current_command.identifier == end_timer_id

                if no_system_info and len(blocks) == 2 and blocks[1].name == 'git' and len(blocks[1]) == 4 and not current_command.lines:
                    blocks[1].commands = blocks[1].commands[:-1]
                    continue
                else:
                    assert current_command.lines

                parameters = dict(parameter.split('=')
                                  for parameter in parameters.split(','))
                for key, value in parameters.items():
                    setattr(current_command, key, value)
                current_command = None
            elif nocolor_line.startswith('travis_fold:start:'):
                assert not current_block or current_block.name[0] == '_'

                block_name = nocolor_line[len('travis_fold:start:'):]

                block_group, _, block_group_cnt = block_name.partition('.')

                try:
                    # git.10
                    block_group_cnt = int(block_group_cnt)
                except ValueError:
                    # git.checkout .submodule .etc
                    block_group = block_name
                    block_group_cnt = None

                if block_group_cnt:
                    if block_group_cnt != 1:
                        current_block = blocks[-1]
                        if current_block.name != block_group:
                            raise ParseError('unexpected block {0} after {1}'.format(block_name, current_block.name))
                        if len(current_block) != (block_group_cnt - 1):
                            print(current_block, block_name)
                        assert len(current_block) == (block_group_cnt - 1)
                        continue

                assert block_name not in blocks

                current_block = Block(block_group)
                blocks.append(current_block)
            elif nocolor_line.startswith('travis_fold:end:'):
                block_name = nocolor_line[len('travis_fold:end:'):]
                block_group, _, block_group_cnt = block_name.partition('.')

                try:
                    # git.10
                    block_group_cnt = int(block_group_cnt)
                except ValueError:
                    # git.checkout .submodule .etc
                    block_group = block_name
                    block_group_cnt = None

                assert block_group == blocks[-1]
                current_block = None
            else:
                if 'travis_' in line:
                    raise ParseError(
                        'unexpected travis_ in {0} while parsing {1}'.format(
                            line, current_block))
                if nocolor_line.startswith('This job is running on container-'
                                           'based infrastructure'):
                    current_block = Block('_container_notice')
                    blocks.append(current_block)
                elif line.startswith('Using worker: '):
                    assert not blocks
                    current_block = Block('_worker_note')
                    blocks.append(current_block)
                elif nocolor_line.startswith('Setting environment variables '
                                             'from repository settings'):
                    current_block = Block('_environment')
                    blocks.append(current_block)
                elif nocolor_line.startswith('Setting environment variables '
                                             'from .travis.yml'):
                    current_block = Block('_environment')
                    blocks.append(current_block)
                elif nocolor_line.endswith(
                        'Override the install: key in your .travis.yml '
                        'to install dependencies.'):
                    current_block = Block('_install')
                    blocks.append(current_block)
                elif nocolor_line.startswith('Could not find .travis.yml'):
                    default_yml = True
                elif default_yml and not current_block and blocks[-1].name in ['rvm']:
                    current_block = Block('_versions')
                    blocks.append(current_block)
                elif current_command is None and current_block == 'git.checkout':
                    if nocolor_line.startswith('$ cd ') or nocolor_line.startswith('$ git checkout -qf '):
                        current_command = Command('_untimed_command')
                elif current_command is None and current_block in ['git.checkout', 'git.submodule'] and nocolor_line.startswith('The command "git ') and '" failed and exited with 1' in nocolor_line:
                    current_command = current_block.commands[-1]

                if current_block == '_environment' and not line:
                    current_block = Block('_init')
                    blocks.append(current_block)
                    continue

                if current_block == '_init' and not current_command and nocolor_line.startswith('$ '):
                    current_command = Command('_untimed_command')
                    current_block.commands.append(current_command)
                elif current_block == '_versions' and nocolor_line.startswith('$ '):
                    if nocolor_line.endswith(' --version'):
                        current_command = Command('_untimed_command')
                        current_block.commands.append(current_command)
                    else:
                        current_block = Block('script')
                        blocks.append(current_block)

                if current_command is not None:
                    current_command.lines.append(line)
                elif current_block is not None and nocolor_line:
                    current_block.lines.append(line)
                elif no_system_info and len(blocks) == 2 and blocks[1].name == 'git' and nocolor_line.startswith('$ cd '):
                    # block 0 should be _worker
                    # todo; check it is 'cd <repo slug>'
                    fake_command = Command('fake git.2')
                    fake_command.lines.append(line)
                    blocks[1].commands.append(fake_command)
                elif nocolor_line:  # ignore blank lines
                    previous_block_name = None if not blocks else blocks[-1].name
                    print('hmm', len(blocks))
                    raise ParseError('unexpected line after {0}: {1!r}'.format(previous_block_name, line))

        return blocks
