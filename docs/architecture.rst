.. _architecture:

==================================
Architecture and Programming Model
==================================

------------------------------------------
Generating Vectors using :py:class:`VectorBuilder <dumpling.Common.VectorBuilder.VectorBuilder>`
------------------------------------------

Dumpling uses a very modular architecture based on the classes in the `Common`
package. Most functions in *dumpling* revolve around vectors which internally
are represented as simple dictionaries::

  vector = {'type': <type>, ...}

The Different Kinds of Vectors
""""""""""""""""""""""""""""""

There are three different types of vectors indicated by the 'type' entry:

- Normal Vectors:
   ::

      {'type': 'vec', 'vector': <pin_state_map>, 'repeat':int, 'comment':str}

   The <pin_state_map> is another dictionary which contains a mapping of each
   logical pin name supplied in the pin declaration to pin state character, e.g.
   '0','1','X' etc.::

     {'tck': '0', 'trst': '1', 'tdo': 'X', 'tdi': '0', 'tms': '1'}

   The actual state character (value) used depends on the driver that generated
   the vector but the three character just mentioned are the most commonly used
   ones. The state character is explained in more detail in a following
   :ref:`subsection <state_character>`. The repeat value denotes how often the
   vector should be repeated before the next one is to be applied. A value of 1
   denotes that the vector should be applied exactly once. The optional comment
   string helps to identify the purpose and context of the current vector. Most
   drivers automatically anotate the generated vectors with reasonable default
   comments. How the comments are used depends on the target, consuming the
   vectors. The AVC vector writer (HP93000VectorWriter class) embeds the comment
   into the vector string while the CocotbVectorDriver writes them to the Log
   output during simulation.

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

Repeat indicates how often the loop is supposed to be applied with. A value of 1
causes the loop body to be applied exactly once.

The Pin Declaration
"""""""""""""""""""

The :py:class:`VectorBuilder <dumpling.Common.VectorBuilder.VectorBuilder>`
class is the working horse when it comes to generating vectors. The class is
instantiated by providing a declaration of all the pins that should end up in
the vectors created by this particular instance of :py:class:`VectorBuilder
<dumpling.Common.VectorBuilder.VectorBuilder>`. Each pin is declared with a
**logical name**, and a **physical name**. The **logical name** is used by
protocol driver classes like ``JTAGDriver`` to refer to pins without knowing the
actual **physical name** used in the design. This makes the drivers agnostic to
the naming scheme used for a particular chip. An example of such a **logical
name**, **phyiscal name** relation would be ``tck`` = ``pad_pulp_jtag_tck_i``.
Eeach of the more abstract driver classes (e.g. the ``JTAGDriver``) internally
uses the logical name while the VectorWriter class that generates the AVC file
will later on map them to the actual signal name used in the design. Logical
names should thus be used consistently and drivers must declare the names they
internally use in their documentation so the user knows what pin declaration to
provide to the VectorBuilder instance.

The actual pin declaration is just a dictionary with **logical name** as the
key and another dictionary as the value. Here is an example::

   {
   'chip_reset': {'name': 'pad_reset_n', 'default': '1', 'type':'input'},
   'trst': {'name': 'pad_jtag_trst', 'default': '1', 'type':'input'},
   'tms': {'name': 'pad_jtag_tms', 'default': '0', 'type':'input'},
   'tck': {'name': 'pad_jtag_tck', 'default': '0', 'type':'input'},
   'tdi': {'name': 'pad_jtag_tdi', 'default': '0', 'type':'input'},
   'tdo': {'name': 'pad_jtag_tdo', 'default': 'X', 'type':'output'}
   }

Each pin dictionary (the value mapped to the **logical name**) must contain the following keys:

:"name": The actual name of the pin corresponding to the logical name. This
         value depends on the module under test.
:"default": The default value that should be assigned to the pin if the
            driver doesn't assign a different value.
:"type": The directionality of the signal with valid values: ``'input'``,
         ``'outut'`` and ``'inout'``.


.. _state_character:
The State Character
"""""""""""""""""""

At the the very core, a vector is nothing more than a mapping of a *state
character* (an ASCII character like '0', '1' or 'X') to a specific *pin* for a
given period of time (e.g. a single clock period). The state character is
translated to a waveform using the *wavetable* you definer in your ASIC tester
setup e.g. a rising edge followed by a falling edge in the case of a clock
signal or a sampling edge shortly before the next rising edge of the related
clock signal in case of output signals. *dumpling* is agnostic on what state
character is used to generate the vectors, any ASCI character may be used.
However, drivers mostly stick to the convention of using the characters '0' and
'1' to refer to application or sampling of a logic low or logic high level. The
(capital) 'X' character is used for outputs to indicate a don't care state.


.. note::

   In order to add support for bidirectional pin usage within a single vector
   file in the simulator, this convetion might be extended in the future to add
   additional state characters like the 'Z', 'L' and 'H' character.

How to use :py:class:`VectorBuilder <dumpling.Common.VectorBuilder.VectorBuilder>`
""""""""""""""""""""""""""""

Now knowing the basics about the representation of vectors in *dumpling* we can
now have a closer look how :py:class:`VectorBuilder <dumpling.Common.VectorBuilder.VectorBuilder>` simplifies creating them::

  pins =    {
   'chip_reset': {'name': 'pad_reset_n', 'default': '1', 'type':'input'},
   'trst': {'name': 'pad_jtag_trst', 'default': '1', 'type':'input'},
   'tms': {'name': 'pad_jtag_tms', 'default': '0', 'type':'input'},
   'tck': {'name': 'pad_jtag_tck', 'default': '0', 'type':'input'},
   'tdi': {'name': 'pad_jtag_tdi', 'default': '0', 'type':'input'},
   'tdo': {'name': 'pad_jtag_tdo', 'default': 'X', 'type':'output'}
   }

  builder = VectorBuilder(pins)
  vectors = []
  builder.chip_reset = 0
  builder.tck = 1
  builder.tdo = 'X'
  vectors.append(builder.vector(comment="Assert chip reset and turn on JTACG TCK"))
  builder.tck = 0
  vectors += [builder.vector())]*10
  builder.chip_reset = 1
  builder.tdo = 0
  vectors.append(builder.vector(comment="Deasserting chip reset"))

The :py:class:`VectorBuilder <dumpling.Common.VectorBuilder.VectorBuilder>`
instance keeps an internal state for each declared pin (the state is initialized
with the ``default`` value provided in the pin declaration). The state can be
changed with some syntactic sugar by just assigning the desired state character
(the integer 1 or 0 can be used as alias for '0' and '1') to the **logical
name** or **physical name** of the pin. The assignment will only alter the
internal state of the pin in the :py:class:`VectorBuilder
<dumpling.Common.VectorBuilder.VectorBuilder>` instance but won't affect or
produce any vectors yet. In order to actually generate vectors, the
:py:meth:`vector() <dumpling.Common.VectorBuilder.VectorBuilder.vector>` must be
called which generates a single vector that represents the current state of each
declared pin. This scheme allows to only assign a new value to the pins that
actually change between generating vectors. The optional ``comment`` parameter
can be usedanotate a vector with a comment. The comment will also end up in the
generate AVC file and helps a lot when debugging vectors on the ASIC tester
which is why the drivers in **dumpling** make extensive use of this feature when
generating vectors.

--------------------
Generating AVC Files
--------------------

In order to convert our list of vectors to AVC files importable by *SmartTest*,
we leverage the :py:class:`HP93000VectorWriter
<dumpling.Common.HP93000.HP93000VectorWriter>` class. This besided the pin
declaration dictionary which was already used for the :py:class:`VectorBuilder
<dumpling.Common.VectorBuilder.VectorBuilder>` instance, the class expects a
target filename argument as well as number of optional additional parameter to
influence the header and '*.tmf' and '*.wtb' file content. Once created, the
class instance can then be used to append vectors to the newly created AVC file.
The class implements the ContextManager interface to automatically close the AVC
file. Here is an example on how to use it::

  with HP93000VectorWriter('my_vectors.avc', pins) as writer:
     writer.write_vectors(vectors)

This scheme allows to generate and write vectors to disk in an interleaved
manner instead of first generating thousands of vectors in memory before finally
writing all of them to disk.

