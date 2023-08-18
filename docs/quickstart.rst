===========
Quickstart
===========
------------
Installation
------------

Installation of dumpling is straight forward: Clone the repository and install the package using `pip`.

.. code-block:: bash

   pip install git+https://github.com/pulp-platform/dumpling.git

If you plan to modify dumpling you might want to install it with the `pip`
editable flag so changes to the source code of dumpling take effect
immediately to all Python environments were you installed *dumpling*

.. code-block:: bash

   git clone https://github.com/pulp-platform/dumpling.git
   pip install -e ./dumpling

This installation scheme will automatically install all the required
dependencies to generate vectors using *dumpling*. However, the simulation
capabilities requires CocoTB to be installed. Since the installation of CocoTB
can sometimes be a bit of a challenge (especially on our IIS CentOS machines)
the simulation capability is an optional feature and CocoTB is not a hard
requirement to install *dumpling*. If you plan to use the simulation feature,
install dumpling with the following extra flag:

.. code-block:: bash

   pip install git+https://github.com/pulp-platform/dumpling.git[SIM]

This will install dumpling with all the necessary dependencies for AVC vector
simulation using CocoTB.

--------------------------------
Generating Vectors Using the CLI
--------------------------------

For a selected number of chips you can use the *dumpling* CLI tool to generate a
some commonly required vectors. The entry point for all of those scripts is the
command ``dumpling``.

Each supported chip is registered as subcommand of the CLI entry point
("dumpling") and provides a chip specific set of commands to generate vectors
for e.g. loading data into memory, ELF binary execution or activation of
debugging capabilities like clock bypassing or signal observation features. All
``dumpling`` comands are self documenting by providing the ``--help`` or ``-h``
flag to give a quick description of the command's capabilities and available
flags/arguments. E.g. the following invocation will provide you with a list of
all currently supported chips (subcommands):

.. code-block:: bash

   dumpling -h

One peculiarity to be aware of is the fact, that the output file name and other
options affecting the format of the AVC vector file to be generated is provided
as an argument to the chip subcommand. The subcommand that actually generates
the vector e.g. ``execute_elf`` to boot a binary must be specified after the
output file and format specifications.

An example is better than a thousand words. The following invocation correctly
creates a new vector file called halt_core.avc that reads and compares the
core's programm counter with 0x1c008080 while asserting the global chip_reset
line.

.. code-block:: bash

   dumpling vega --output ../../hp93000/import/halt_core.avc halt_core_verify_pc --pc 0x1c008080 --assert-reset 

Supplying the ``--output`` option after the actual command (in this case
``halt_cor_verify_pc`` does not work, i.e. the following invocation results in
an error:

.. code-block:: bash

   dumpling vega halt_core_verify_pc --pc 0x1c008080 --assert-reset -o ../../hp93000/import/halt_core.avc

Among the ``--output`` option there are other optional arguments that affect the
output of the AVC vector translation. You can for example modify the *port name*
referenced in the AVC file or change the name of the *wavetable*. If these
arguements are chosen in accordance with the ASIC tester setup, the generated
vector file can be imported without additional trick as Port Bursts into your
Pattern Master File using the *SmartTest GUI* (this is possible since *dumpling*
in addition to the \*.avc file also creates the \*.tmf and \*.wtb file).
