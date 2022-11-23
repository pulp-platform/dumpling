#!/usr/bin/env python3

#
# Copyright (C) 2018 ETH Zurich, University of Bologna and GreenWaves Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

#
# Authors: Germain Haugou, ETH (germain.haugou@iis.ee.ethz.ch)
#
from pathlib import Path
from typing import Union

from elftools.elf.elffile import ELFFile
import os
import os.path
import struct
import logging


class ElfParser(object):
    """
    A helper class to parse ELF binaries and extract the relevant segments for preloading as well as the start address.
    """

    def __init__(self, verbose=False):
        self.binaries = []
        self.mem = {}
        self.verbose = verbose
        self.areas = []
        logging.info('Created stimuli generator')

    def get_entry(self):
        """
        Return the entry point of the ELF binary (the address where the core should start execution).

        Returns:
            int: The entry point address as an integer.

        """
        with open(self.binaries[0], 'rb') as file:
            elffile = ELFFile(file)
            return elffile.header['e_entry']


    def add_binary(self, binary: Union[str, os.PathLike]):
        """
        Add an additional binary to the ElfParser instance.

        All binaries added will be parsed together when `parse_binaries()` is called.

        Args:
            binary: A path to the binary to be added to the parser instance.

        Returns:

        """
        logging.info('Added binary: %s', binary)
        self.binaries.append(binary)


    def parse_binaries(self, word_width):
        """
        Parses the added binaries and returns a dictionary with addr, data pairs.

        The word_width determines how many bytes are agregated to a single entry in the returned dictionary.
        E.g. calling 'stim_gen.parse_binaries(4)' will generates a dictionary were each key is a 4-byte aligned
        address with corresponding 4 bytes of data. The byte ordering is little endian.

        Args:
            word_width (int): The width of one word in bytes

        Returns:
            Dict[int, int] A dictionary of address data pairs
        """
        self.__parse_binaries(word_width)
        return self.mem


    def __add_mem_word(self, base, size, data, width):

        aligned_base = base & ~(width - 1)

        shift = base - aligned_base
        iter_size = width - shift
        if iter_size > size:
            iter_size = size

        value = self.mem.get(str(aligned_base))
        if value is None:
            value = 0

        value &= ~(((1 << width) - 1) << (shift * 8))
        value |= int.from_bytes(data[0:iter_size], byteorder='little') << (shift * 8)

        self.mem[str(aligned_base)] = value

        return iter_size

    def __add_mem(self, base, size, data, width):

        while size > 0:
            iter_size = self.__add_mem_word(base, size, data, width)

            size -= iter_size
            base += iter_size
            data = data[iter_size:]

    def __gen_stim_slm(self, filename, width):

        logging.info('  Generating to file: ' + filename)

        try:
            os.makedirs(os.path.dirname(filename))
        except:
            pass

        with open(filename, 'w') as file:
            for key in sorted(self.mem.keys()):
                file.write('%X_%0*X\n' % (int(key), width * 2, self.mem.get(key)))

    def __parse_binaries(self, width):

        self.mem = {}

        for binary in self.binaries:

            with open(binary, 'rb') as file:
                elffile = ELFFile(file)

                for segment in elffile.iter_segments():

                    if segment['p_type'] == 'PT_LOAD':

                        data = segment.data()
                        addr = segment['p_paddr']
                        size = len(data)

                        load = True
                        if len(self.areas) != 0:
                            load = False
                            for area in self.areas:
                                if addr >= area[0] and addr + size <= area[1]:
                                    load = True
                                    break

                        if load:

                            logging.info('  Handling section (base: 0x%x, size: 0x%x)' % (addr, size))

                            self.__add_mem(addr, size, data, width)

                            if segment['p_filesz'] < segment['p_memsz']:
                                addr = segment['p_paddr'] + segment['p_filesz']
                                size = segment['p_memsz'] - segment['p_filesz']
                                logging.info('  Init section to 0 (base: 0x%x, size: 0x%x)' % (addr, size))
                                self.__add_mem(addr, size, [0] * size, width)

                        else:

                            logging.info('  Bypassing section (base: 0x%x, size: 0x%x)' % (addr, size))

    def gen_stim_slm_64(self, stim_file):

        self.__parse_binaries(8)

        self.__gen_stim_slm(stim_file, 8)

    def gen_stim_bin(self, stim_file):

        self.__parse_binaries(1)

        try:
            os.makedirs(os.path.dirname(stim_file))
        except:
            pass

        with open(stim_file, 'wb') as file:
            prev_addr = None
            for key in sorted(self.mem.keys()):
                addr = int(key)
                if prev_addr is not None:
                    while prev_addr != addr - 1:
                        file.write(struct.pack('B', 0))
                        prev_addr += 1

                prev_addr = addr
                file.write(struct.pack('B', int(self.mem.get(key))))
