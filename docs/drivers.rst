=======
Drivers
=======

While the :py:class:`VectorBuilder
<dumpling.Common.VectorBuilder.VectorBuilder>` already simplifies the
programatic generation of vectors it is still a very low level scheme to
interact with a DUT.

This section introduces the drivers currently supported by *dumpling* that
provide functions for chip interaction at a much higher abstraction-level.

.. important::

   Each driver reports the set of *logical pins* that it is going to interact
   with. The driver will only assign values to these signals. Any other signal
   that might have been declared during instantiation of the
   :py:class:`VectorBuilder <dumpling.Common.VectorBuilder.VectorBuilder>`
   instance will not be affected at all. E.g. lets suppose you wanted to generate a vector
   file that, in addition to the defined JTAG pins of the JTAG driver, also
   contains a global ``chip_reset`` pin. Now have a look at the following example::

     builder.chip_reset = 0
     vectors = jtag_driver.jtag_reset(comment="Resetting the jtag iface")
     builder.chip_reset = 1
     vectors += jtag_driver.jtag_idle_vectors(count=10, comment="Deasserting global reset and idling JTAG")

   Since you altered the value of chip reset before generating vectors using the
   :py:class:`JTAGDriver <dumpling.Drivers.JTAG.JTAGDriver>` instance, each
   vector generated by the driver will have the value '0' assigned to
   ``chip_reset`` while each vector generated by the second interaction driver
   will have the ``chip_reset`` pin assume the value '1'.


.. include:: drivers/jtag.rst
