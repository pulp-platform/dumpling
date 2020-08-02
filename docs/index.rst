===========
Dumpling
===========

 **Dumpling** is a tool to generate and simulate vectors for the HP93000 ASIC
 tester. It is both a library to build upon for vector generation and JTAG
 bitbanging in general as well as a command line tool to generate vectors for a
 set of supported PULP chips. The original goal of dumpling was to stream line
 the procedure to generate ASCI Vector files for the HP93000 tester (AVC files).
 Before dumplings emergence vectors that would boot a given ELF binary or
 configure the DUT using specifig JTAG taps would have to be created by creating
 vectors dumps from an RTL simulation or handcrafting of the vectors. While one
 could argue that vectors recorded from RTL simulation are the better approach
 since they stem from the actual functional model of the device under test there
 are a number of significant downfalls of the traditional VCD dump method:

 - The output signals are always recorded by RTL simulation. Most of the time we
   (especially during reset) we do not care about the actual value of the output
   signals. We only want to check outputs at very specific point during the
   simulation (e.g. when we verify the content of some JTAG register or perform
   a memory readout). If we cannot perfectly control the clock and phase
   relation of the stimuli clock (e.g. JTAG TCK) and the systems clock the DUT
   on the tester might show slightly different responses e.g. shifted by one
   cycle than the RTL simulation. Without knowing when we actually care about
   the outputs and when its just garbage to ignore it is hard to interpret the
   mismatches reported by the ASIC tester.
 - The recorded vectors contain zero context about what they actually do. This
   is especially important during debugging when there are mismatches. If we do
   not know the role/meaning of a single vector in a 10'000 vector long AVC file
   that mismatches we will have a very hard time figuring out what actually
   causes the mismatch.

 Dumpling is different. Instead of performing RTL simulation to generate the
 vectors it bitbangs the actual protocol (at the moment of writing this
 documentation only JTAG is supported) in a modular way. The generated vectors
 are extensively annotated with comments that provide context of what the
 current vector is supposed to do with the DUT. Furthermore by not using RTL
 simulation the generation of vectors e.g. to perform a complete ELF binary boot
 procedure and end of computation check is orders of magnitude faster than
 running the full blown testbench on the RTL of a huge multi-core PULP chip.

 With its modular architecture, dumpling is easy to extend with additional
 protocols, JTAG taps or CLI scripts for chip specific vector generation. Since
 vectors are internally represented with a very simple intermediate
 representation, new output formats other than the HP93000's AVC format can
 easily be added. In addition to the vector generation capabilities **dumpling**
 also provides the means to verify the vectors in RTL simulation using the power
 of CocoTB_, a python interface for rapid RTL testbench development with support
 for pretty much every RTL simulator (including the open source Verilator) there
 is. This allows to simulate arbitrary AVC files (not just the ones created with
 **dumpling**) in RTL with only a couple lines of Python and Makefile code and
 is an invaluable tool to hunt down mismatches on found on silicon.
 
.. note::

   Dumpling is still in its very early stage of development and the interfaces
   might still change in the future.


Contents
========

.. toctree::
   :maxdepth: 2

   Quickstart <quickstart>
   Architecture and Programming Model <architecture>
   Drivers <drivers>
   Generating Custom Vectors <custom_vectors>
   Vector Simulation <simulation>
   Extending Dumpling
   Authors <authors>
   Changelog <changelog>
   Module Reference <api/modules>


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. _toctree: http://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html
.. _reStructuredText: http://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html
.. _references: http://www.sphinx-doc.org/en/stable/markup/inline.html
.. _Python domain syntax: http://sphinx-doc.org/domains.html#the-python-domain
.. _Sphinx: http://www.sphinx-doc.org/
.. _Python: http://docs.python.org/
.. _Numpy: http://docs.scipy.org/doc/numpy
.. _SciPy: http://docs.scipy.org/doc/scipy/reference/
.. _matplotlib: https://matplotlib.org/contents.html#
.. _Pandas: http://pandas.pydata.org/pandas-docs/stable
.. _Scikit-Learn: http://scikit-learn.org/stable
.. _autodoc: http://www.sphinx-doc.org/en/stable/ext/autodoc.html
.. _Google style: https://github.com/google/styleguide/blob/gh-pages/pyguide.md#38-comments-and-docstrings
.. _NumPy style: https://numpydoc.readthedocs.io/en/latest/format.html
.. _classical style: http://www.sphinx-doc.org/en/stable/domains.html#info-field-lists
.. _CocoTB: https://docs.cocotb.org/en/stable/
