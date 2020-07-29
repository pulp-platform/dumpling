import textwrap
from pathlib import Path
from typing import Mapping, List

from dumpling.Common.VectorBuilder import VectorBuilder
from mako.template import Template


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