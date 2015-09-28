from __future__ import absolute_import, unicode_literals

import os
import regex
import sys

from collections import OrderedDict

from travispy import ParseError, TravisLogCorrupt

from travispy._log_functions import *
from travispy._log_items import *


class Block(object):

    """Travis log block."""

    def __init__(self, name):
        """Constructor."""
        self.name = name
        self.elements = []
        self.lines = []
        self._finished = None

    @property
    def commands(self):
        return self.elements

    @property
    def last_item(self):
        if not self.elements:
            return None
        return self.elements[-1]

    def append(self, item):
        if isinstance(item, BlankLine) and self.lines:
            self.lines.append('')
        elif not item:
            print('{0}: inserting empty item'.format(self))
            self.elements.append(item)
        else:
            self.elements.append(item)

    def allow_empty(self):
        return False

    def append_line(self, line):
        if self.elements:
            last_command = self.elements[-1]
            #print('append to block', last_command, type(last_command), line, last_command.finished())
            if isinstance(last_command, TimedCommand) and not last_command.finished():
                last_command.append_line(line)
                return

        nocolor_line = remove_ansi_color(line)
        if nocolor_line.startswith('$ '):
            new_command = UntimedCommand()
            new_command.append_line(line)
        elif self.elements:
            last_command = self.elements[-1]
            last_command.append_line(line)
        else:
            new_item = Note()
            new_item.append_line(line)

    def finished(self):
        return self._finished

    def __hash__(self):
        return self.name

    def __eq__(self, other):
        return self.name == other

    def __len__(self):
        if not self.lines and not self.commands:
            return 0

        if self.lines and self.commands:
            if len(self.elements) == 1 and isinstance(self.elements[0], BlankLine):
                pass
            else:
                raise ParseError('block with lines and commands: {0!r}'.format(self))

        #assert bool(self.lines) != bool(self.commands)

        if self.lines:
            return len(self.lines)
        else:
            return len(self.commands)

    def __repr__(self):
        if not self.lines and not self.commands:
            return '<empty block {0}>'.format(self.name)

        if self.lines and self.commands:
            if len(self.elements) == 1 and isinstance(self.elements[0], BlankLine):
                pass
            else:
                return '<mixed block {0} ({1} lines & {2} commands): {3}\n{4}'.format(self.name, len(self.lines), len(self.commands), self.lines, self.commands)

        #assert bool(self.lines) != bool(self.commands)
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


class CommandBlock(Block):

    def append_line(self, line):
        nocolor_line = remove_ansi_color(line)

        assert self.commands

        last_command = self.commands[-1]
        if isinstance(last_command, BlankLine):
            last_command = self.commands[-2]

        if not isinstance(last_command, Command):
            raise ParseError('last command is {0}: {1}'.format(type(last_command), last_command))

        if len(last_command.lines):

            # clean the last command line, and remove the '$ '
            exit_code_pattern = 'The command "{0}" exited with '.format(remove_ansi_color(last_command.lines[0])[2:])
            if nocolor_line.startswith(exit_code_pattern):
                exit_code = nocolor_line[len(exit_code_pattern):-1]
                last_command.exit_code = int(exit_code)
                return
            elif exit_code_pattern.startswith(nocolor_line):
                # TODO: The exit_code_pattern needs to be a multi-line match
                # e.g. happy5214/pywikibot-core/6.10
                current_command = Note('_unsolved_exit_code')
                self.commands.append(current_command)
                return

            exit_code_pattern = 'The command "{0}" failed and exited with '.format(remove_ansi_color(last_command.lines[0])[2:])
            if nocolor_line.startswith(exit_code_pattern):
                exit_code = nocolor_line[len(exit_code_pattern):].split(' during ')[0]
                last_command.exit_code = int(exit_code)
                return

        else:
            last_command.append_line(line)


class SingleCommandBlock(Block):

    def append_line(self, line):
        assert len(self.elements) == 1
        if len(self.elements[0].lines) != 0:
            raise ParseError('cant insert line into {0}: {1}'.format(self, line))
        assert len(self.elements[0].lines) == 0
        self.elements[0].append_line(line)

    def finished(self):
        return len(self.elements[0].lines) == 1


class AutoCommandBlock(Block):

    _single_line_response = False

    def append_line(self, line):
        nocolor_line = remove_ansi_color(line)
        if nocolor_line.startswith('$ '):
            if self.elements and self._single_line_response:
                last_command = self.elements[-1]
                assert len(last_command.lines) == 2
            command = UntimedCommand()
            command.append_line(line)
            self.elements.append(command)
        else:
            if not len(self):
                raise ParseError('Unexpected version line: {0}'.format(line))
            last_command = self.elements[-1]
            if self._single_line_response:
                assert len(last_command.lines) == 1
            last_command.append_line(line)

    def __repr__(self):
        return '<auto commands: {0}>'.format(self.elements)


class AutoVersionCommandBlock(AutoCommandBlock):

    _single_line_response = True

    def append_line(self, line):
        nocolor_line = remove_ansi_color(line)
        if nocolor_line.startswith('$ '):
            assert nocolor_line.endswith('--version')
        super(AutoVersionCommandBlock, self).append_line(line)
        #print('autoversion', line)

    def append(self, item):
        raise RuntimeError('not allowed to add {0} to {1}'.format(item, self))

    # no separator after version /home/jayvdb/tmp/travis-bot/jayvdb/citeproc-test/13.1-failed.txt
    #def finished(self):
    #    print('is finished', self.elements)
    #    if self.elements and len(self.elements[-1]) == 2 and 'gem --version' in self.elements[-1][0]:
    #        return True


class MixedCommandBlock(AutoCommandBlock):

    def append_line(self, line):
        if self.elements:
            if self.elements[-1].finished():
                super(MixedCommandBlock, self).append_line(line)
            else:
                self.elements[-1].append_line(line)


class OldGitBlock(MixedCommandBlock):


    def __len__(self):
        if len(self.elements) == 4 and not self.elements[-1].lines and self.elements[-1].finished():
            # remove the empty '4th' item, so it doesnt conflict with 'git.4'
            self.elements = self.elements[:-1]

        return super(OldGitBlock, self).__len__()

    @property
    def last_item(self):
        if len(self.elements) == 4 and not self.elements[-1].lines and self.elements[-1].finished():
            # remove the empty '4th' item, so it doesnt conflict with 'git.4'
            self.elements = self.elements[:-1]

        return super(OldGitBlock, self).last_item

    def allow_empty(self):
        if len(self.elements) == 3 and '$ git checkout -qf ' in self.elements[2].lines[0]:
            return True
        else:
            return False

    def finished(self):
        return False


class AutoNameBlock(Block):

    def __init__(self):
        name = ''.join(
            '_' + c if c.isupper() else c
            for c in self.__class__.__name__).lower()
        super(AutoNameBlock, self).__init__(name)


class RegexBlock(AutoNameBlock):

    _is_note = False
    _blank_line_end = False
    _single_line = False

    def is_note(self):
        return self._is_note

    def append_line(self, line):
        #print('appending', self, line)
        if self.finished():
            raise ParseError('block {0} is finished'.format(self))

        if remove_ansi_color(line) == '':
            self.elements.append(BlankLine())
        else:
            self.elements[0].append_line(line)

    def finished(self):
        if not self.elements:
            return False
        if self._single_line:
            #print('single line', self)
            return len(self.elements[-1].lines) == 1
        if self._blank_line_end:
            return isinstance(self.elements[-1], BlankLine)
        else:
            return None


class ExactMatchBlock(RegexBlock):

    _except = []

    def is_note(self):
        return True

    def append_line(self, line):
        assert not self.finished()
        expect_line = self._expect[len(self.elements[-1].lines)]
        assert remove_ansi_color(line) == expect_line
        self.elements[-1].lines.append(line)

    def finished(self):
        return len(self.elements[-1].lines) == len(self._expect)


class StalledJobTerminated(ExactMatchBlock):

    _match = '^No output has been received in the last 10 minutes'
    _expect = (
        'No output has been received in the last 10 minutes, this potentially indicates a stalled build or something wrong with the build itself.',
        '',
        'The build has been terminated',
    )


class LogExceededJobTerminated(ExactMatchBlock):

    _match = '^The log length has exceeded the limit of 4 Megabytes'
    _expect = (
        'The log length has exceeded the limit of 4 Megabytes (this usually means that test suite is raising the same exception over and over).',
        '',
        'The build has been terminated.',
    )


class NoTravisYmlWarning(RegexBlock):

    _match = '^WARNING: We were unable to find a .travis.yml file.'
    _is_note = True
    _blank_line_end = True


class Worker(RegexBlock):

    _match = '^Using worker'

    _is_note = True
    _blank_line_end = True


class StandardConfigurationWarning(RegexBlock):

    _match = '^Could not find .travis.yml, using standard configuration.'
    _is_note = True


class PythonNoRequirements(RegexBlock):

    _match = '^Could not locate requirements.txt'
    _is_note = True


#class SystemInformation(RegexBlock):
#
#    _match = '^Build system information'
#
#    _is_note = True
#    _blank_line_end = True


class ContainerNotice(RegexBlock):

    _match = ('^This job is running on container-based '
              'infrastructure')

    _is_note = True
    _blank_line_end = None
    # /home/jayvdb/tmp/travis-bot/jayvdb/citeproc-test/13.1-failed.txt doesnt include a blank line


class EnvironmentSettings(RegexBlock):

    _is_note = True  # captures the first line as a note
    _blank_line_end = True

    def append_line(self, line):
        if remove_ansi_color(line) == '':
            self.elements.append(BlankLine())
            return

        envvar = UntimedCommand()
        envvar.append_line(line)
        self.elements.append(envvar)
        #print('appended', envvar)


class RepositoryEnvironmentSettings(EnvironmentSettings):

    _match = '^Setting environment variables from repository settings'


class TravisYmlEnvironmentSettings(EnvironmentSettings):

    _match = '^Setting environment variables from \.travis\.yml'


class AptBlock(Block):

    def append_line(self, line):
        if 'Installing APT Packages' in line:
            header = Note()
            header.lines.append(line)
            self.elements.append(header)
        elif '$ export DEBIAN_FRONTEND=noninteractive' in line:
            current_command = UntimedCommand()
            current_command.lines.append(line)
            self.elements.append(current_command)
        else:
            super(AptBlock, self).append_line(line)
            #raise ParseError('unexpected additional line for {0}: {1}'.format(self, line))


class BlankLineBlock(Block):

    def append_line(self, line):
        if remove_ansi_color(line) != '':
            raise ParseError('BlankLineBlock not expecting {0}'.format(line))
        self.elements.append(BlankLine())



class JobCancelled(RegexBlock):

    # two leading blank lines?

    _match = '^Done: Job Cancelled'
    _is_note = True
    _single_line = True


class JobStopped(RegexBlock):

    _match = '^Your build has been stopped.'
    _is_note = True


BLOCK_CLASSES = [
    NoTravisYmlWarning,
    Worker,
    StandardConfigurationWarning,
    PythonNoRequirements,
    ContainerNotice,
    RepositoryEnvironmentSettings,
    TravisYmlEnvironmentSettings,
    JobCancelled,
    JobStopped,
    StalledJobTerminated,
    LogExceededJobTerminated,
]


