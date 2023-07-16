# Manuel Eggimann <meggimann@iis.ee.ethz.ch>
#
# Copyright (C) 2020-2022 ETH Zürich
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
import re
import textwrap
from pathlib import Path
from typing import Mapping, List, Iterator

from dumpling.Common.VectorBuilder import VectorBuilder, Vector
from mako.template import Template

from Common.VectorBuilder import PinDecl


class AVCPinDecl(PinDecl):
    avc_name: str


class HP93000VectorReader:
    """
    The HP93000VectorReader allows parsing of AVC files back to the intermediate representation of vectors in the
    form of dictionaries.

    In order to not exhaust the whole system memory when parsing huge AVC files, the Class provides the
    `self.vectors()` generator function that iteratively reads and parses the underlying AVC file while iterating.
    Additionally, the `HP93000VectorReader` implements the the context manager interface to automatically close the
    underlying file once all vectors have been consumed.

    Examples::

         with HP93000VectorReader('my_vectors.avc', my_pin_declarations) as reader:
             for vector in reader.vectors():
                ..do something usefull with the vector...

    Args:
        stimuli_file_path(Path): The path to the AVC file to parse
        pins(Mapping[str, Mapping]): The pin declaration that allows the parser to perform the inverse logical to
            physical pin name mapping (i.e. the same pin declaration that was used to generate the vectors with
            `VectorBuilder`
    """

    _matchers = {
    'empty_line' : re.compile(r'^\s*$'),
    'format_stmt' : re.compile(r'FORMAT\s+(?P<ports>(\w+(?:\s+|;))+)'),
    'port_stmt' : re.compile(r'PORT\s+\w*\s*;'),
    'normal_vec' : re.compile(r'R(?P<repeat>\d+)\s+(?P<dvc_name>\w*)\s+(?P<pin_state>\w+)\s+(?:\[%]\s*(?P<comment>.*);)?'),
    'match_loop_begin' : re.compile(r'SQPG\s+MACT\s+(?P<retries>\d+)\s*;'),
    'match_loop_idle_begin' : re.compile(r'SQPG\s+MRPT\s+(?P<idle_vectors>\d+)\s*;'),
    'match_loop_end' : re.compile(r'SQPG\s+PADDING\s*;'),
    'loop_begin' : re.compile(r'SQPG\s+LBGN\s+(?P<count>\d+)\s*;'),
    'loop_end' : re.compile(r'SQPG\s+LEND\s*;')
    }

    def __init__(self, stimuli_file_path: Path, pins: Mapping[str, AVCPinDecl]):
        self.stimuli_file_path = stimuli_file_path
        self.pins = pins
        self.pin_order = None
        self.physical_to_logical_map = {pin.get('avc_name', pin['name']): logical_name for logical_name, pin in pins.items()}

    def __enter__(self):
        self._file = self.stimuli_file_path.open('r')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._file.close()

    def vectors(self) -> Iterator[Vector]:
        """
        A generator function that yields a single parsed vector at a time.

        Yields:
            Mapping: A single vector

        Raises:
            StopIteration: Once all vectors have been consumed
        """
        for line in self._file:
            stm_type = None
            match = None
            for stm_type, matcher in HP93000VectorReader._matchers.items():
                match = matcher.match(line)
                if match:
                    break
            if not match:
                raise ValueError("Could not parse line: {}".format(line))

            if stm_type == 'empty_line':
                pass
            elif stm_type == 'format_stmt':
                self.pin_order = str.split(match.group('ports'))
            elif stm_type == 'port_stmt':
                pass #Ignore this statement
            elif stm_type == 'normal_vec':
                if self.pin_order: #Make sure we already read the format statement
                    pin_state = {self.physical_to_logical_map[self.pin_order[i]]: value for i, value in enumerate(match.group('pin_state'))}
                    yield {'type': 'vec', 'vector': pin_state, 'repeat': int(match.group('repeat')), 'comment': match.group('comment')}
                else:
                    raise ValueError("Encountered vector statement before reading format statement")
            elif stm_type == 'match_loop_begin':
                condition_vectors = list(self.vectors())
                idle_vectors = list(self.vectors())
                yield {'type': 'match_loop', 'cond_vectors': condition_vectors, 'idle_vectors': idle_vectors, 'retries': int(match.group('retries'))}
            elif stm_type == 'match_loop_idle_begin':
                return
            elif stm_type == 'match_loop_end':
                return
            elif stm_type == 'loop_begin':
                body = list(self.vectors())
                yield {'type': 'loop', 'loop_body': body, 'repeat': int(match.group('count'))}
            elif stm_type == 'loop_end':
                return



class HP93000VectorWriter:
    """
    This class allows to generate AVC files from Vectors in intermediate (dictionary) representation as generated by
    the `VectorBuilder` class.

    During initialization, the object is initialized with a pins declaration dictionary (see documentation of the
    `VectorBuilder` class) and output AVC file path. Optionally, a port, device_cycle_name and wavetable name can be
    supplied. In addition to creating the avc output file, a wave table file (*.wtb) and a timing format file (*.tmf) is
    generated upon construction of the `HP93000VectorWriter` instance. These files will have the same base name ( e.g.
    vectors.tmf and vectors.wtb if `stimuli_file_path`=='output.avc'. This allows to directly import the generated
    vectors for a specific test port given that the `port` argument was chosen according to the port name used in the
    tester setup.

    The class implements the context manager interface that automatically closes the underlying avc file. This allows to
    write vectors to AVC file in batches::

       with HP93000VectorWriter('output_vectors.avc', dut_pins) as writer:
         vectors = ...generate some vectors...
         writer.write_vectors(vectors)
         vectors = ...generate some more vectors...
         writer.write_vectors(vectors) #Append them to the AVC file

    Args:
        stimuli_file_path(Path): The path of the output AVC file
        pins(Mapping[str, Mapping]): The pin declaration dictionary (see `VectorBuilder` docstring)
        port(str): If not None, PORT declaration is added to the header of the AVC file to make it importable as a
           port specific vector file.
        wtb_name: The name of the wavetable to be associated with the AVC pattern file.
    """

    def __init__(self, stimuli_file_path: Path, pins: Mapping[str, Mapping], port: str=None, device_cycle_name: str="dvc_1", wtb_name: str="Standard ATI"):
        self.pins = pins
        self.stimuli_file_path = stimuli_file_path
        self.stimuli_file = None
        self.port = port
        self.device_cycle_name = device_cycle_name
        self.wtb_name = wtb_name
        self._generate_wtb_and_tmf()
        self._write_header()

    def __enter__(self):
        self.stimuli_file = self.stimuli_file_path.open('a+')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stimuli_file.close()

    def _generate_wtb_and_tmf(self) -> None:
        #Generate the WTB and TMF file in the same target directory as the stimuli file with the same stem
        wtb_path = self.stimuli_file_path.with_suffix('.wtb')
        tmf_path = self.stimuli_file_path.with_suffix('.tmf')
        #Write the default wtb
        wtb_path.write_text(self.wtb_name)
        #Write the default tmf
        wtb_template = Template(textwrap.dedent("""\
        PINS ${port_name}
        DDC ${device_cycle_name}
        0 0
        1 1
        X 2
        L 3
        H 4
        Z 5"""))
        tmf_path.write_text(wtb_template.render(port_name=self.port, device_cycle_name=self.device_cycle_name))

    def write_vectors(self, vectors: List[Vector], compress: bool = False) -> None:
        """
        Append the given vectors to the vector file in AVC format.

        This method translates the intermediate vector representation generated by `VectorBuilder` or
        `HP93000VectorReader` to the AVC format that can be imported into the ASIC tester.

        The function allows to optionally apply run length compression on the vectors by merging subsequent identical
        vectors to a single entry with increased 'repeat' attribute. This allows to safe vector memory but might make
        the vectors harder to interpret during debugging.

        Args:
            vectors(List): A list of vectors to translate and append to the AVC file.
            compress(bool): If true, apply compression to the vector before writing them to the AVC file.

        Returns:

        """
        if compress:
            vectors = VectorBuilder.compress_vectors(vectors)
        for vector in vectors:
            if vector['type'] == 'vec':
                pin_state_string = ''.join([str(vector['vector'][pin]) for pin in sorted(self.pins.keys())])
                vector_line = "R{} {} {} ".format(vector['repeat'], self.device_cycle_name, pin_state_string)
                if vector['comment'] and vector['comment'] != "":
                    vector_line += "[%] " + vector['comment'] + " "
                vector_line += ";\n"
                self.stimuli_file.write(vector_line)
            elif vector['type'] == 'match_loop':
                self.stimuli_file.write("SQPG MACT {} ;\n".format(vector['retries']))
                self.write_vectors(vector['cond_vectors'])
                self.stimuli_file.write("SQPG MRPT {} ;\n".format(len(vector['idle_vectors'])))
                self.write_vectors(vector['idle_vectors'])
                self.stimuli_file.write("SQPG PADDING ;\n")
            elif vector['type'] == 'loop':
                self.stimuli_file.write("SQPG LBGN {} ;\n".format(vector['repeat']))
                self.write_vectors(vector['loop_body'])
                self.stimuli_file.write("SQPG LEND ;\n")
            else:
                raise ValueError("Got vector with unknown type {}".format(vector['type']))

    def _write_header(self) -> None:
        with self.stimuli_file_path.open(mode='w') as stimuli_file:
            if self.port:
                stimuli_file.write("PORT " + self.port + " ;\n")
            stimuli_file.write("FORMAT " + ' '.join([pin['name'] for logical_name, pin in sorted(self.pins.items())]) + " ;\n")
