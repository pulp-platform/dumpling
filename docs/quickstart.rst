===========
Quickstart
===========
------------
Installation
------------

Installation of dumpling is straight forward: Clone the repository and install the package using `pip`

.. code-block:: bash

   git clone https://iis-git.ee.ethz.ch/utilities/dumpling
   pip install ./dumpling

If you plan to modify dumpling you might want to install it with the `pip`
editable flag so changes to the source code of dumpling take effect
immediately to all Python environments were you installed *dumpling*

.. code-block:: bash

   pip install -e ./dumpling

This installation scheme will automatically install all the required
dependencies to generate vectors using *dumpling*. However, the simulation
capabilities requires CocoTB to be installed. Since the installation of CocoTB
can sometimes be a bit of a challenge (especially on our IIS CentOS machines)
the simulation capabilites is an optional feature and CocoTB is not a hard
requirement to install *dumpling*. If you plan to use the simulation feature,
install dumpling with the following extra flag:

.. code-block:: bash

   pip install "./dumpling[SIM]"

This will install dumpling with all the necessary dependencies for AVC vector
simulation using CocoTB.

--------------------------------
Generating Vectors Using the CLI
--------------------------------

For a limited number of chips you can use the *dumpling* CLI tool to generate a
selection of commonly used vectors. The common entry point for all of those
scripts is the command ``dumpling``. To simply usage *dumpling* provides shell
completion for the CLI tool. In order to benefit from this feature, the shell
completion needs to be installed for your shell of choice. This can be done
without much effort using the ``install_completions`` subcommand:

.. code-block:: bash

   dumpling install_completions

This command will detect the shell currently in use (officially supported are
bash, zsh, fish and Powershell) and install the shell completion by appending
the required settings to your shell config file (e.g. `.bashrc` in case you are
using `bash`).

Each supported chip is registered as subcommand of the CLI entry point
("dumpling") and provides a chip specific set of commands to generate vectors
for e.g. loading data into memory, booting and ELF binary or activating specific
debugging capabilities of the chip like clock bypassing or signal observation
features. All ``dumpling`` comands are self documenting by providing the
``--help`` or ``-h`` flag to give a quick description of the commands
capabilities and available flags/arguments. E.g. the following invocation will
provide you with a list of all currently supported chips:

.. code-block:: bash

   dumpling -h

One peculiarity to be aware of is the fact, that the output file name and other
options affecting the format of the AVC vector file to be generated is provided
as an argument to the chip subcommand and not as an argument to the actual
vector generating command. Unless you are fine with the default behavior which
is to generate a file called vectors.avc in the current working directory you
have to specify the output location before calling the actual command.

An example is better than a thousand words:

.. code-block:: bash

   dumpling vega -o ../../hp93000/import/halt_core.avc halt_core_verify_pc --pc 0x1c008080 --assert-reset 

Supplying the ``-o`` option after the actual command (in this case
``halt_cor_verify_pc`` does not work, i.e. the following invocation results in an
error:

.. code-block:: bash

   dumpling vega halt_core_verify_pc --pc 0x1c008080 --assert-reset -o ../../hp93000/import/halt_core.avc

Among the ``--output`` option there are other optional arguments for example
modify the *port name* referenced in the AVC file or change the name of the
reference *wavetable*. If these arguements are chosend in accordance to the ASIC
tester setup, the generated vectors can be imported as is as port burst vectors
into your Pattern Master File using the *SmartTest GUI* (this is possible since
*dumpling* besides the \*.avc file also creates the \*.tmf and \*.wtb file).
