import re
import textwrap
from pathlib import Path
from typing import Mapping, List, TextIO

from dumpling.Common.VectorBuilder import VectorBuilder
from mako.template import Template

class HP93000VectorReader:
    matchers = {
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

    def __init__(self, stimuli_file_path: Path, pins: Mapping[str, Mapping]):
        self.stimuli_file_path = stimuli_file_path
        self.pins = pins
        self.pin_order = None
        self.physical_to_logical_map = {pin['name']: logical_name for logical_name, pin in pins.items()}

    def __enter__(self):
        self._file = self.stimuli_file_path.open('r')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._file.close()

    def vectors(self):
        for line in self._file:
            stm_type = None
            match = None
            for stm_type, matcher in HP93000VectorReader.matchers.items():
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
                yield list({'type': 'loop', 'loop_body': body, 'repeat': int(match.group('count'))})



class HP93000VectorWriter:
    """Use the functions exposed by this class to generate an ascii stimuli file
    for the HP93000 ASIC tester. During initialization, the object is
    initialized with a list of pins to be used. The HP93000VectorWriter object
    creates list of pin:state mapping that is initialized with a default value
    for each pin. To manipulate the state of a pin just use the overloaded
    __setattr__ to change the internal state. With a call to self.vector() the
    current state of all pins is dumped to a single stimuli vector string and
    returned. The matched_loop and loop functions may be used to conveniently
    create the necessary sequencer instructions for matched loop setup.

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

    def _generate_wtb_and_tmf(self):
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

    def write_vectors(self, vectors: List[Mapping[str, None]], compress=False):
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

    def _write_header(self):
        with self.stimuli_file_path.open(mode='w') as stimuli_file:
            if self.port:
                stimuli_file.write("PORT " + self.port + " ;\n")
            stimuli_file.write("FORMAT " + ' '.join([pin['name'] for logical_name, pin in sorted(self.pins.items())]) + " ;\n")



pins = {
        'chip_reset' : {'name': 'pad_reset_n', 'default': '0'},
        'trst': {'name': 'pad_jtag_trst', 'default': '1'},
        'tms': {'name': 'pad_jtag_tms', 'default': '0'},
        'tck': {'name': 'pad_jtag_tck', 'default': '0'},
        'tdi': {'name': 'pad_jtag_tdi', 'default': '0'},
        'tdo': {'name': 'pad_jtag_tdo', 'default': 'X'}
    }