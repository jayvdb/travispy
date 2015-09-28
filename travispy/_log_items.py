from __future__ import absolute_import, unicode_literals

import os
import regex
import sys

from travispy import ParseError, TravisLogCorrupt


class Item(object):

    """Top class."""

    def __init__(self):
        """Constructor."""
        super(Item, self).__init__()
        self._lines = []

    def append_line(self, line):
        self._lines.append(line)

    @property
    def lines(self):
        return self._lines

    def __repr__(self):
        return '{0}'.format(self._lines)


class Note(Item):

    """A note."""

    def __init__(self, identifier=None):
        """Constructor."""
        super(Note, self).__init__()
        self.identifier = identifier


class Command(Item):

    """Executed command."""

    def __init__(self):
        """Constructor."""
        super(Command, self).__init__()
        self.exit_code = None

    def __repr__(self):
        return '<unnamed command>: {0}'.format(self._lines[0]) if self._lines else '<empty unnamed command >'

    @property
    def lines(self):
        return self._lines


class UntimedCommand(Command):

    def __init__(self, identifier=None):
        """Constructor."""
        super(UntimedCommand, self).__init__()
        self.identifier = identifier

    def finished(self):
        return False


class TimedCommand(Command):

    """Executed command."""

    def __init__(self, identifier, allow_empty=False):
        """Constructor."""
        super(TimedCommand, self).__init__()
        self.identifier = identifier
        self.start = self.end = self.duration = None
        self.exit_code = None
        self.allow_empty = allow_empty

    def set_parameters(self, parameters):
        if not self.allow_empty:
            if not self._lines:
                raise ParseError('{0} is empty at end of parse'.format(self))

        parameters = dict(parameter.split('=')
                          for parameter in parameters.split(','))
        for key, value in parameters.items():
            setattr(self, key, value)

    def finished(self):
        return self.start is not None

    def __repr__(self):
        return '<{0}>: {1}'.format(self.identifier, self._lines[0]) if self._lines else '<empty command {0}>'.format(self.identifier)


class ContinuedTimedCommand(TimedCommand):

    def __init__(self, continues, allow_empty=False):
        super(ContinuedTimedCommand, self).__init__(continues.identifier, allow_empty)
        self._continues = continues


class BlankLine(Item):

    pass

