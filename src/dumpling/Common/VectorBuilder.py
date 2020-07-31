import copy
from typing import Mapping, List





class VectorBuilder:
    """The VectorRecorder class provides a common interface for
    stimuli generating classes like the JTagDriver class to dump stimuli in a
    target independent intermediate representation.

    Upon construction, the class expects a declaration of the pins that will be contained in the generated vectors which
    is a dictionary of pin description of the following form::

       {
       'chip_reset': {'name': 'pad_reset_n', 'default': '1', 'type':'input'},
       'trst': {'name': 'pad_jtag_trst', 'default': '1', 'type':'input'},
       'tms': {'name': 'pad_jtag_tms', 'default': '0', 'type':'input'},
       'tck': {'name': 'pad_jtag_tck', 'default': '0', 'type':'input'},
       'tdi': {'name': 'pad_jtag_tdi', 'default': '0', 'type':'input'},
       'tdo': {'name': 'pad_jtag_tdo', 'default': 'X', 'type':'output'}
       }

    The key of the dictionary is the logical name of the pin (e.g. ``tck``). The logical name of the pin is used by the
    driver to reference a target pin without knowing the actual name used in the design. The value corresponding to the
    logical name is another dictionary containing the following keys:

    :"name": The actual name of the pin corresponding to the logical name. This value depends on the module under test.
    :"default": The default value that should be assigned to the pin if the driver doesn't assign a different value.
    Valid values are '0', '1', 'X' and 'Z'

    Once created with such a pin list the vector writer can then be used by the driver to generate stimuli. The
    VectorRecorder class overrides the __setattr__ and the __getattr__ function so drivers can use the instances of this
    class according to the following example::

        vectors = []
        writer.trst = 0
        writer.chip_reset = 1
        vectors.append(writer.vector()) #Generate 1 vector with
        writer.chip_reset = 0
        writer.tck = 1
        vectors.extend(writer.vector()*10) #Release reset and generate 10 vectors with tck=1

    For each pin declared in the pin_list when creating the writer, an internal state is maintained, that is initialized
    with teh 'default' value. When calling ``self.vector`` a new vector is generated with using the current state of
    each pin (i.e. a pin value has to be assigned only if it changes between one vector and another). Each vector is
    represented int the form of a dictionary. There are three different types of vectors indicated by the 'type' entry:

    - Normal Vectors::

       {'type': 'vec', 'vector': <pin_state_map>, 'repeat':int, 'comment':str}

       The <pin_state_map> is another dictionary which contains a mapping of each logical pin name supplied in the pin
       declaration  to pin state character, e.g. '0','1','X' etc. The actual state character used depends on the driver
       but the three character just mentioned are the most commonly used ones. The repeat value denotes how often the
       vector should be repeated before the next one is supposed to be applied. A value of 1 denotes that the vector
       should be applied exactly once. The comment string helps to identify the purpose and context of the current
       vector. Most drivers automatically anotate the generated vectors with reasonable default comments. How the
       comments are used depends on the target, consuming the vectors. The AVC vector writer (HP93000VectorWriter class)
       embeds the comment into the vector string while the CocotbVectorDriver write the to the Log output during
       simulation.

    - Matched Loops:
        Matched loops represent the corresponding sequencer capability of the ASIC tester, to apply a list of
        condition vectors to the DUT in a loop until none of the vector cause a mismatch. If there is a mismatch
        during condition vector application, the sequencer will apply a second list of 'idle vectors' before trying
        the 'condition vectors' once again. This procedure is repeated until the condition vectors all pass or the
        maximum number of iterations is reached. Matched loops cause all kinds of weird behavior on the ASIC tester
        and might cause it to no longer be able to reconstruct the timing results of a test. Try to avoid them and
        don't nest them. Example::

           {'type': 'match_loop', 'cond_vectors': List[Vector], 'idle_vectors': List[Vector], 'retries':int}

        A retry count of 1 causes the matched loop to be applied exactly once without any repetitions.

    - Loops:
       A normal loop allows to repeat a whole sequence of vectors for a configurable amount of time::
           {'type': 'loop', 'loop_body': List[Vector], 'repeat': int}
       Repeat indicates how often the loop is supposed to be applied with one causing the loop body to be applied
       exactly once.

    Args:
        pins: The pin declaration dictionary.

    """

    def __init__(self, pins: Mapping[str, Mapping]):
        self.__dict__['pins'] = pins
        self.__dict__['pin_state'] = {logical_name: pin_desc['default'] for logical_name, pin_desc in pins.items()}

    def __setattr__(self, name, value):
        """
        Operator overloading that looks up `name` in the internal pin_state dictionary and if found, assigns a new
        state value to the pin.

        Examples::

            my_vector_builder.rst_pin = 0

        Args:
            name: The logical or physical name of a pin from the pin declaration dict or an actual field of the class.
            value(str): The new state character to assign to the given pin

        Returns:

        """
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

    def init(self):
        self.__dict__['pin_state'] = {logical_name: pin_desc['default'] for logical_name, pin_desc in self.pins.items()}

    def vector(self, repeat=1, comment=""):
        """
        Generate a single vector representing the current state of each pin. The pin values can be altered with the
        `__setattr__` method::

           my_vector_builder.clk_i = 1
           my_vector_builder.rst_ni = 0
           a_vector = my_vector_builder.vector(comment="Enabling clock and asserting reset")

        The vector can be annotated with an optional comment and has the option to be attributed with a `repeat` value
        that indicates repeated application of the same vector. The ASIC tester actually stores this repeat value in
        vector memory so applying the same vector for 10'000 cycles with a corresponding `repeat` value only consumes
        the memory of a single vector entry in ASIC tester memory.

        Args:
            repeat(int): The number of times the vector should be repeated. A 1 indicates a single application of the vector.
            comment(str): A string to annotate the vector with.

        Returns:
            Mapping: A single vector (dictionary) representing the current state of all declared pins
        """
        vector = {'type': 'vec', 'vector': copy.deepcopy(self.pin_state), 'repeat': repeat, 'comment': comment}
        return vector

    def matched_loop(self, condition_vectors: List, idle_vectors: List, retries=5):
        """
        Construct a matched loop vector using the given list of condition and idle vectors.

        The HP93000 ASIC tester has the limitation that the sequence of condition vectors as well as the idle vectors
        need to  contain an exact multiple of 8 vectors. Use the `pad_vectors` static method to pad your list of
        condition and idle vectors with an appropriately chosen padding vector.

        Notes:
            Don't nest matched loops. Although the CocotbVectorDriver correctly handles it the resulting AVC file
            cannot be parsed by the ASIC tester.

        Args:
            condition_vectors: A list of condition vectors with len(condition_vectors)%8 = 0
            idle_vectors: A list of idle vectors with len(idle_vectors)%8 = 0
            retries: The number of retries where 1 means a single application of the condition vectors with immediate
                     failure on missmatch.

        Returns:
            Mapping: A single vector (dictionary) representing the matched_loop construct
        """
        return [{'type': 'match_loop', 'cond_vectors': condition_vectors, 'idle_vectors': idle_vectors, 'retries': retries}]

    def loop(self, loop_body, loop_repeat_count):
        """
        Returns a loop vector with the given loop body and the attribute on how often to repeat the loop body.

        Args:
            loop_body(List): The vectors to repeat.
            loop_repeat_count: The number of applications of the loop body. 1 -> apply the body exactly once.

        Returns:
            Mapping: A single vector (dictionary) representing the loop construct
        """
        return [{'type': 'loop', 'loop_body': loop_body, 'repeat': loop_repeat_count}]

    @staticmethod
    def compress_vectors(vectors):
        """
        Compresses the list of vectors by searching for consecutive identical vectors.

        The vectors are merged by summing together the repeat option of the individual vectors.
        Vectors with identical pin values but different comments are not merged together.

        The allows to save vector memory on the ASIC tester and results in smaller AVC files.

        Args:
            vectors (List[Mapping]): The list of vectors to compress

        Returns:
            List[Mapping]: The compressed list of vectors

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
        """
        Append padding vector to the list of input_vectors until its length is a multiple of 8.

        The given padding vector is appended to the end of the sequence until the lenght of the sequence is a
        multiple of 8.

        Args:
            input_vectors(List[Mapping]): The sequence of vectors to pad to a multiple of 8 using the given padding
            vector.
            padding_vector(Mapping): A single vector that should be used for padding. Only 'Normal Vectors' are allowed
            here.
        Returns:
            List[Mapping]: The padded sequence of vectors
        """
        input_vectors += (8 - len(input_vectors) % 8) * [padding_vector]
        return input_vectors

