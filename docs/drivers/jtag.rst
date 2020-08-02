----
JTAG
----

Logical Pins
"""""""""""""""""""""
The JTAG Driver uses the following logical pins:

"tck"
   The JTAG clock pin

"tms"
   The Test Mode select pin

"trst"
   The test logic reset pin

"tdi"
   Test data input input

"tdo"
   Test data output

Description
"""""""""""
The JTAG driver infrastructure is split into several different entities in order
to make it easier to add support for new JTAG Taps and to make the TAP drivers
agnostic to the length of the JTAG chain in a particular chip (how many other
TAPs are connected to the same chain). The most basic interaction is provided by
the :py:class:`JTAGDriver <dumpling.Drivers.JTAG.JTAGDriver>` class. Like all
drivers it is instantiated by providing its constructor with an initialized
:py:class:`VectorBuilder <dumpling.Common.VectorBuilder.VectorBuilder>`
instance. The :py:class:`JTAGDriver <dumpling.Drivers.JTAG.JTAGDriver>` is then
configured to match the actual JTAG chain of the target DUT. For each TAP in the
JTAG chain, an instance of :py:class:`JTAGTap
<dumpling.JTAGTaps.JTAGTap.JTAGTap>` or its subclasses is added in the order the
`TDI` signal traverses them. The baseclass :py:class:`JTAGTap
<dumpling.JTAGTaps.JTAGTap.JTAGTap>` serves the key purpose of informing the
:py:class:`JTAGDriver <dumpling.Drivers.JTAG.JTAGDriver>` driver instance about
the position and IR length of each JTAG tap in the chain. Here is an example::

  Jtag_chain = JTAGDriver(vector_builder=builder)
  tap1 = PULPJTAGTap(jtag_chain) 
  tap2 = JTAGTap("Dummy Tap", ir_size=5, driver=jtag_chain)
  jtag_chain.add_tap(tap1)
  jtag_chain.add_tap(tap2)


In this example we configure a :py:class:`JTAGDriver
<dumpling.Drivers.JTAG.JTAGDriver>` driver instance with two TAPs. The first one
being an instance of :py:class:`PULPJTAGTap
<dumpling.JTAGTaps.PULPJTAGTap.PULPJTAGTap>` and the second one being some other
generic TAP that we don't need to interact with but nonetheless inform the
driver abouth its presence so it can adjust the vectors to account for the
additional chain element during JTAG interaction.

Note that we first instantiate the individual taps by providing them a handle to
the :py:class:`JTAGDriver <dumpling.Drivers.JTAG.JTAGDriver>` driver instance.
The subclasses of :py:class:`JTAGTap <dumpling.JTAGTaps.JTAGTap.JTAGTap>` use
this handle to interact with the chain through the driver without having to be
aware of the presence of other TAPs on the same chain.


Once configured, the :py:class:`JTAGDriver <dumpling.Drivers.JTAG.JTAGDriver>`
driver instance can be used to directly interact with the jtag chain (which is
what the subclasses of :py:class:`JTAGTap <dumpling.JTAGTaps.JTAGTap.JTAGTap>`
do internally for high level operations). Here is an example of such an interaction::

  vectors = scan_chain.jtag_set_IR(tap1, "010011", comment="Selecting the FLL config register")
  vectors += scan_chain.jtag_set_DR(tap1, "1110", comment="Write 0xE to FLL config register")

Since driver functions almost always return lists of vectors we can conveniently
append them using the ``+=`` operator.

.. attention::

   Since the JTAG driver is already aware of the presence of other JTAG taps
   (e.g. Dummy TAP "tap2" in our example) we don't have to account for it
   anymore when chosing the IR or DR values. The bitstrings are automatically
   padded according to the chain configuration. Read the documentation of
   :py:meth:`JTAGDriver.jtag_set_ir
   <dumpling.Drivers.JTAG.JTAGDriver.jtag_set_ir>` and
   :py:meth:`JTAGDriver.jtag_set_ir
   <dumpling.Drivers.JTAG.JTAGDriver.jtag_set_dr>` for additional details.
