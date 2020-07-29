import copy
from typing import Mapping, List





class VectorBuilder:
    """The VectorRecorder class provides a common interface for
    stimuli generating classes like the JTagDriver class to dump stimuli in a
    target independent way.

    Upon construction, the class expects a pin_list which is a dictionary
    of pin description of the following form::
       {
       'chip_reset': {'name': 'pad_reset_n', 'default': '1', 'type':'input'},
       'trst': {'name': 'pad_jtag_trst', 'default': '1', 'type':'input'},
       'tms': {'name': 'pad_jtag_tms', 'default': '0', 'type':'input'},
       'tck': {'name': 'pad_jtag_tck', 'default': '0', 'type':'input'},
       'tdi': {'name': 'pad_jtag_tdi', 'default': '0', 'type':'input'},
       'tdo': {'name': 'pad_jtag_tdo', 'default': 'X', 'type':'output'}
       }

    The key of the dictionary is the logical name of the pin (e.g. ``tck``).
    The logical name of the pin is used by the driver to reference a target pin
    without knowing the actual name used in the design. The value corresponding
    to the logical name is another dictionary containing the following keys:

    :"name": The actual name of the pin corresponding to the logical name. This
    value depends on the module under test. :"default": The default value that
    should be assigned to the pin if the driver doesn't assign a different
    value. Valid values are '0', '1', 'X' and 'Z'

    Once created with such a pin list the vector writer can then be used by the
    driver to generate stimuli. The VectorRecorder class overrides the
    __setattr__ and the __getattr__ function so drivers can use the instances
    of this class according to the following example::

        vectors = []
        writer.trst = 0
        writer.chip_reset = 1
        vectors.append(writer.vector()) #Generate 1 vector with
        writer.chip_reset = 0
        writer.tck = 1
        vectors.extend(writer.vector()*10) #Release reset and generate 10 vectors with tck=1

    For each pin declared in the pin_list when creating the writer, an internal
    state is maintained, that is initialized with teh 'default' value. When
    calling ``self.vector`` a new vector is generated with using the current
    state of each pin (i.e. a pin value has to be assigned only if it changes
    between one vector and another). The type of the vector returned by
    ``self.vector`` is however dependent on the actual VectorWriter
    implementation.

    The class additionally provides the matched_loop and loop constructs to
    generate conditional vector loops. They expect lists of vectors and return
    new lists of vectors. With this scheme, larger lists of stimuli can be
    generated iteratively and combined to loops and matched loops.

    In order to commit a generated list of vectors to the VectorWriter, call
    the ``commit_vectors`` (or ``commit_vector`` in case of a single vector)
    function.

    Args:
        pins:

    """

    def __init__(self, pins: Mapping[str, Mapping]):
        self.__dict__['pins'] = pins
        self.__dict__['pin_state'] = {logical_name: pin_desc['default'] for logical_name, pin_desc in pins.items()}

    def __setattr__(self, name, value):
        if name in self.pin_state:
            self.pin_state[name] = value
        elif name in self.pins.keys():
            self.__setattr__(self.pins[name]['name'], value)
        else:
            self.__dict__[name] = value

    def __getattr__(self, item):
        if item in self.pins:
            return self.pin_state[item]
        else:
            raise AttributeError()

    def vector(self, repeat=1, comment=""):
        vector = {'type': 'vec', 'vector': copy.deepcopy(self.pin_state), 'repeat': repeat, 'comment': comment}
        return vector

    def matched_loop(self, condition_vectors, idle_vectors, retries=5):
        return [{'type': 'match_loop', 'cond_vectors': condition_vectors, 'idle_vectors': idle_vectors, 'retries': retries}]

    def loop(self, loop_body, loop_repeat_count):
        return [{'type': 'loop', 'loop_body': loop_body, 'repeat': loop_repeat_count}]

    @staticmethod
    def compress_vectors(vectors):
        """
        Compresses the list of vectors by searching for consecutive identical vectors.

        The vectors are merged by summing together the repeat option of the individual vectors.
        Vectors with identical pin values but different comments are not merged together.

        Args:
            vectors (List[Mapping]): The list of vectors to compress

        Returns:
            List[Mapping]: The processed list of vectors after compression

        """
        prev_vector = None
        filtered_vectors = []
        for vec in vectors:
            if prev_vector and vec['type'] == 'vec' and vec['vector'] == prev_vector['vector'] and vec['comment'] == prev_vector['comment']:
                prev_vector['repeat'] += vec['repeat']
            elif prev_vector:
                filtered_vectors.append(prev_vector)
                prev_vector = vec
            else:
                prev_vector = vec
        return filtered_vectors

    @staticmethod
    def pad_vectors(input_vectors: List, padding_vector):
        """Append padding vector to the list of input_vectors until its lenght is a multiple of 8"""
        input_vectors += (8 - len(input_vectors) % 8) * [padding_vector]
        return input_vectors

