'''Parse travis log files.'''
# For the tokens used in log files, see
# https://github.com/travis-ci/travis-build/blob/master/lib/travis/build/templates/header.sh

from __future__ import absolute_import, unicode_literals

import os
import regex
import sys

from collections import OrderedDict

from travispy import ParseError, TravisLogCorrupt


from travispy._log_functions import *
from travispy._log_items import *
from travispy._log_blocks import *


class BlockDict(OrderedDict):

    """OrderedDict of Block."""

    @staticmethod
    def _parse_name(name):
        """Return block name, and number as int or None."""
        assert name
        dotted = name.split('.')
        if len(dotted) == 1:
            return name, None

        assert len(dotted) == 2

        # try to parse the second half as a number
        # e.g. git.10
        try:
            num = int(dotted[1])
            assert num is not 0
        except ValueError:
            num = None

        if num:
            return dotted[0], num
        else:
            # e.g. git.checkout .submodule .etc
            return name, None

    def _get_existing(self, name):
        full_name = name
        name, num = self._parse_name(full_name)
        block = super(BlockDict, self).get(name)
        if block is None:
            raise KeyError('{0} ({1}) not in {2}'.format(full_name, name, self.keys()))

        return block

    def __getitem__(self, item):
        if isinstance(item, int):
            if item < 0:
                item = len(self) + item
            elif item > len(self):
                raise KeyError('{0} is greater than length of {1}'.format(i, len(self)))

            for i, value in enumerate(self.values()):
                if i == item:
                    return value
            raise KeyError('unexpected failure: {0}'.format(item))
        else:
            return self._get_existing(item)

    def get(self, name, start=False, cls=Block):
        full_name = name
        #print('get', full_name)
        name, num = self._parse_name(name)
        if name in self:
            if start:
                assert num and num > 1

            block = self[name]
            if num:
                if start:
                    if num < 2:
                        raise KeyError('{0} is never an existing item'.format(full_name))
                    if num - 1 != len(block):
                        raise KeyError('{0} while len is {1}'.format(full_name, len(block)))
                # foo.<id> should only be used sequentially
                assert len(block) == num - 1

                if block.name != self.last.name:
                    raise ParseError('unexpected block {0} after {1}'.format(
                        block.name, self.last.name))
                assert block == self.last  # this is the same as above
            return block
        else:
            if num:
                assert num == 1
            new_block = cls(name)
            self[name] = new_block
            return new_block

    def append(self, block):
        if block.name in self:
            raise ParseError('{0} already in {1}'.format(block, self))
        self[block.name] = block

    @property
    def last(self):
        """Get the last block."""
        return self[-1]

    def remove_last(self):
        """Remove the last block."""
        last = self.last
        del self[last.name]



def find_new_block(line):
    """Return a new block."""
    nocolor_line = remove_ansi_color(line)

    for block_cls in BLOCK_CLASSES:
        if regex.search(block_cls._match, nocolor_line):
            obj = block_cls()
            if obj.is_note():
                note = Note()
                note.append_line(line)
                obj.append(note)

            # print('Auto new block', obj)

            return obj

    return None


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
            return {}

        no_system_info = False

        if 'travis_fold:start:system_info' not in self.body[:400]:
            if len(self.body) < 400:
                lines = self.body.strip().splitlines()
                # remove blank lines
                lines = [line for line in lines if line]
                if lines[0].startswith('Using worker: '):
                    lines = lines[1:]
                if len(lines) == 1 and lines[0] == 'Done: Job Cancelled':
                    return {}
            else:
                if 'travis_fold:start:system_info' in self.body:
                    # See https://github.com/travis-ci/travis-ci/issues/4848
                    raise TravisLogCorrupt
                elif 'travis_fold:start:git' in self.body[:400]:
                    no_system_info = True
                else:
                    raise ParseError('header not found')

        blocks = BlockDict()

        lines = self.body.splitlines()

        current_block = None
        current_command = None
        successful = False

        for line_no, line in enumerate(lines):
            nocolor_line = remove_ansi_color(line)

            #print('line', current_block, current_command, nocolor_line)

            if nocolor_line.startswith('travis_time:start:'):
                timer_id = nocolor_line[len('travis_time:start:'):]
                assert timer_id

                current_block = blocks.last

                #print('adding start', current_block, current_block.finished(), timer_id)

                if current_block in ['_versions', '_versions-continued']:
                    blocks.append(Block('script'))
                    
                elif current_block and current_block.finished():
                    if (current_block.name.endswith('_environment_variables') or
                            current_block.name == '_container_notice' or
                            current_block.name.startswith('git')):
                        blocks.append(SingleCommandBlock('_activate'))

                    elif current_block.name in '_activate':
                        blocks.append(CommandBlock('_versions-timed'))
                    elif current_block.name in ['before_script', 'install'] or current_block.name in ['before_script-continued', 'install-continued']:
                        blocks.append(Block('script'))
                    else:
                        raise ParseError('unexpected line after {0}: {1}'.format(current_block, line))

                current_block = blocks.last

                #print('start', current_block)

                if current_block is None:
                    print(blocks)
                    raise ParseError('unexpected start: {0}'.format(line))

                allow_empty = current_block.allow_empty()

                current_command = TimedCommand(timer_id, allow_empty)
                current_block.append(current_command)

                #print('start timed inserted', current_block)

            elif nocolor_line.startswith('travis_time:end:'):
                data = nocolor_line[len('travis_time:end:'):]
                end_timer_id, parameters = data.split(':', 1)

                current_command = blocks.last.last_item

                if not isinstance(current_command, TimedCommand):
                    if isinstance(blocks.last, JobCancelled):
                        last_timed_command = blocks[-2].last_item
                        assert isinstance(last_timed_command, TimedCommand)
                        current_command = ContinuedTimedCommand(last_timed_command, allow_empty=True)
                    else:
                        raise ParseError('Last item is a {0} and not a TimedCommand: {1}'.format(type(current_command), current_command))

                #print('end', current_block, current_command, end_timer_id)
                if current_command.identifier != end_timer_id:
                    raise ParseError('{0} is not {1}'.format(current_command, end_timer_id))

                #if not current_command.lines:
                #    print('end with no lines', end_timer_id, current_block, current_command)
                #    sys.exit()

                current_command.set_parameters(parameters)
                current_command = None
            elif nocolor_line.startswith('travis_fold:start:'):
                block_name = nocolor_line[len('travis_fold:start:'):]

                last_block = blocks.last

                cls = None
                if no_system_info and block_name == 'git.1':
                    cls = OldGitBlock
                elif block_name == 'apt':
                    cls = AptBlock
                else:
                    cls = Block

                current_block = blocks.get(block_name, start=True, cls=cls)

                if last_block and current_block != last_block and last_block.finished() == False:
                    raise ParseError('start of {0} during {1} unexpected after {2} ({3})'.format(block_name, current_block, last_block, last_block.finished()))

                if no_system_info and block_name == 'git.3':
                    assert len(blocks) == 2  # block 0 should be _worker
                    assert len(current_block) > 1  # TODO: better assert

                    current_command = UntimedCommand('_untimed_git_checkout')
                    current_block.commands.append(current_command)

                current_block._finished = None

            elif nocolor_line.startswith('travis_fold:end:'):
                block_name = nocolor_line[len('travis_fold:end:'):]
                current_block = blocks[block_name]

                if not current_block == blocks.last:
                    if blocks.last.name == current_block.name + '-continued':
                        blocks.last._finished = True
                    elif isinstance(blocks.last, JobCancelled):  # not used
                        current_block = blocks[-2]
                        last_timed_command = blocks[-2].last_item
                        assert isinstance(last_timed_command, TimedCommand)
                    else:
                        raise ParseError('{0} != {1}'.format(current_block, blocks.last))

                current_block._finished = True
                current_block = None
                current_command = None
            else:
                if 'travis_' in line:
                    raise ParseError(
                        'unexpected travis_ in {0} while parsing {1}'.format(
                            line, current_block))

                new_block = find_new_block(line)
                if new_block is not None:
                    #print('found new block', new_block)
                    #if blocks:
                    #    print('last block was', blocks.last)
                    blocks.append(new_block)
                    # Single line item?
                    if new_block.finished():
                        current_block = None

                    current_block = new_block
                    if current_block.elements:
                        current_command = current_block.elements[-1]
                        continue
                    else:
                        current_command = None

                #print(line)

                if blocks and blocks.last.name in ['rvm'] and blocks.last.finished():
                    current_block = Block('_versions')
                    blocks.append(current_block)
                elif current_command is None and current_block in ['git.checkout', 'git.submodule'] and nocolor_line.startswith('The command "git ') and '" failed and exited with ' in nocolor_line:
                    # TODO: match the command in the quotes
                    current_command = current_block.commands[-1]

                if not current_command and current_block and current_block.commands and nocolor_line.startswith('The command "'):
                    last_command = current_block.commands[-1]
                    if last_command.lines:
                        exit_code_pattern = 'The command "{0}" exited with '.format(remove_ansi_color(last_command.lines[0])[2:])
                        if nocolor_line.startswith(exit_code_pattern):
                            exit_code = nocolor_line[len(exit_code_pattern):-1]
                            last_command.exit_code = int(exit_code)
                            continue
                        elif exit_code_pattern.startswith(nocolor_line):
                            # TODO: The exit_code_pattern needs to be a multi-line match
                            # e.g. happy5214/pywikibot-core/6.10
                            current_command = Note('_unsolved_exit_code')
                            current_block.commands.append(current_command)

                        exit_code_pattern = 'The command "{0}" failed and exited with '.format(remove_ansi_color(last_command.lines[0])[2:])
                        if nocolor_line.startswith(exit_code_pattern):
                            exit_code = nocolor_line[len(exit_code_pattern):].split(' during ')[0]
                            last_command.exit_code = int(exit_code)
                            continue

                if current_block == '_activate' and current_block.finished():
                    print('after _activate')
                    blocks.append(AutoVersionCommandBlock('_versions'))
                    current_block = blocks.last

                if current_block == '_job_cancelled' and current_block.finished():
                    if isinstance(blocks[-2].elements[-1], TimedCommand):
                        current_block = blocks[-2].__class__(blocks[-2].name + '-continued')
                        current_command = ContinuedTimedCommand(blocks[-2].elements[-1], allow_empty=True)
                        current_block.append(current_command)
                    else:
                        current_block = Block('_stuff_after_job_cancelled-' + str(line_no))
                    blocks.append(current_block)

                current_block = blocks.last

                if current_block is not None:
                    if current_block.finished():
                        print('current block is finished', current_block)
                        if nocolor_line == '':
                            blocks.append(BlankLineBlock('_unexpected_blank_lines-' + str(line_no)))
                            continue
                    if 'Done' in line:
                        print('adding {0} to block'.format(line))
                    try:
                        current_block.append_line(line)
                    except Exception:
                        # nasty hack to deal with
                        # /home/jayvdb/tmp/travis-bot/jayvdb/pywikibot-core/1210.11-canceled.txt
                        if nocolor_line == '':
                            current_block = BlankLineBlock('_unexpected_blank_lines-' + str(line_no))
                            blocks.append(current_block)
                        else:
                            print('failed on line {0}: {1}'.format(line_no, line))
                            raise
                elif nocolor_line:  # ignore blank lines
                    previous_block_name = None if not blocks else blocks[-1].name
                    raise ParseError('unexpected line after {0}: {1!r}'.format(previous_block_name, line))

            if blocks.last == '_done':
                done_block = blocks.last
                previous_block = blocks[-2]
                assert previous_block.name == 'script'
                last_command = previous_block.commands[-1]

                if last_command.exit_code is None:
                    raise ParseError('Build exit with {0}, but last command doesnt have an exit code'.format(exit_code))
                elif done_block.exit_code > 0 and last_command.exit_code == 0:
                    print('Build exit with {0}, but last command exit code was {1}'.format(exit_code, last_command.exit_code))
                elif last_command.exit_code != done_block.exit_code:
                    raise ParseError('Build exit with {0}, but last command exit code was {1}'.format(exit_code, last_command.exit_code))
                continue

        return blocks
