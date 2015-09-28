from __future__ import absolute_import, unicode_literals

import regex


def remove_unprintable(s):
    return regex.sub('[^[:print:]\x1b\n]', '', s)


def remove_ansi_color(s):
    return regex.sub('\x1b[^mK]*[mK]', '', s)
