from __future__ import unicode_literals

import codecs
import os
import regex
import sys


from travispy._log_parser import LogParser
from travispy import TravisLogCorrupt


def main():
    args = sys.argv[1:]
    assert args
    for filename in args:
        print('--{0}--'.format(filename))
        assert os.path.isfile(filename)

        file = codecs.open(filename, 'r', 'utf-8')

        log = LogParser.from_file(file)

        try:
            blocks = log._parse()
            block_names = blocks.keys()
            if len(set(block_names)) != len(block_names):
                raise Exception('repeated block names: {0}'.format(block_names))

            [len(block) for block in blocks]
            #continue

            for key, block in blocks.items():
                print('----{0}----'.format(block.name))
                if block.name not in ['_environment', '_init']:
                    continue
                if block.commands:
                    print('   commands    ')
                    for command in block.commands:
                        print(command.lines)

                if block.lines:
                    print('   lines    ')
                    for line in block.lines:
                        print(line)

        except TravisLogCorrupt:
            print('corrupt')
            pass


if __name__ == '__main__':
    main()
