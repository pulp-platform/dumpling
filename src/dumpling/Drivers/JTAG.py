import bitstring
from bitstring import BitArray

from JTAGTaps.JTAGTap import JTAGTap, JTAGRegister

bitstring.set_lsb0(True) #Enables the experimental mode to index LSB with 0 instead of the MSB (see thread https://github.com/scott-griffiths/bitstring/issues/156)
from dumpling.Common.VectorBuilder import VectorBuilder

class JTAGDriver:
    """
    The `JTAGDriver` class provides convenience functions to interact with a specific JTAG chain.

    The driver instance requires a `VectorBuilder` instance in order generate vector in the required format.

    The JTAGDriver expects the VectorBuilder to contain pin declarations with the following *logical name* (the
    physical name is not relevant for the driver):

    - 'tck': The jtag clock pin
    - 'trst': The test logic reset pin
    - 'tms': The test mode select pin
    - 'tdi': The test data in pin
    - 'tdo': The test data out pin

    For the tck, tms, trst and tms pins the driver will write vectors containing the '0' and '1' on state character to
    denote application of logic low and logic high (or no-clk and clk in the case of TCK). The state character for the
    tdo pin can either be '0' for sampling and comparison with logic low, '1' for sampling and comparison with logic
    high or 'X' if the output of TDO should be 'don't care' for the current vector.

    After instantiation of the driver, the JTAG chain configuration needs to be configured by adding JTAGTap
    instances in the order they are hooked up the JTAG chain. This enables the JTAGDriver class and the JTAGTap
    instances that interact with this driver to provide high-level functions for JTAG interaction without needing to
    now the number of additional TAPs on the same chain.

    E.g.::

       driver = JTAGDriver(my_vector_builder)
       riscv_debug_tap = RISCVDebugTap(driver)
       driver.add_tap(risc_debug_tap)
       driver.add_tap(JTAGTap(ir_size=5, driver=driver)) #Add some dummy tap

       #Start using the taps or the driver driver directly
       vectors = risc_debug_tap.halt_harts(...)
       vectors += driver.jtag_set_dr(...)
       writer.write_vectors(vectors)

    For TAPs that we don't need to interact you can just add instantiations of the `JTAGTap` base class as a dummy
    tap to make sure the driver accounts for the additional flip-flops in the chains path. Unless otherwise stated,
    the high-level functions provided by the individual taps will always select the BYPASS register for all other
    taps except the one that should be currently used.

    Args:
        vector_builder(VectorBuilder): A handle to a configured vector builder.

    """
    def __init__(self, vector_builder: VectorBuilder):
        self.vector_builder = vector_builder
        self.chain = []

    def set_jtag_default_values(self):
        """
        Apply default (idle) values to the jtag pins.

        This function will only alter the state of the jtag pins in the underlying vector builder without generating any
        vectors yet. It will not affect any non-jtag pin that might be present in the vector_builder instance.

        Returns:

        """
        self.vector_builder.tck = '0'
        self.vector_builder.trst = '1'
        self.vector_builder.tms = '0'
        self.vector_builder.tdi = '0'
        self.vector_builder.tdo = 'X'

    def add_tap(self, jtag_tap: JTAGTap):
        """
        Adds a new JTAG TAP to the chain controlled by this driver instance.

        The TAPs are supposed to be added in the same order that the TDI signal passes through them. E.g. if the TDI
        enters the chip, passes TAP1, leaves TAP1 through it's TDO, enters TAP2 through the TDI and finally leaves the
        chip through TDO, register the TAPs in the following order::

          self.add_tap(TAP1)
          self.add_tap(TAP2)


        Args:
            jtag_tap: The JTAG TAP to add to the chain.

        Returns:

        """
        self.chain.insert(0, jtag_tap)


    def jtag_idle_vector(self, repeat=1, comment=None):
        """
        Returns a single vector with the given 'repeat' value to keep the JTAG interface idle.

        The vector will turn off the JTAG clock and keep the TMS pin low.

        Args:
            repeat: The number of cycles to repeat the idle vector
            comment(str): An optional comment to annotate the generated vector with

        Returns:
            Mapping: A single vector
        """
        self.set_jtag_default_values()
        return self.vector_builder.vector(repeat=repeat, comment=comment)

    def jtag_idle_vectors(self, count=1):
        """
        Returns a list of JTAG idle vectors of the given length.

        This function does basically the same as jtag_idle_vector but will just return a list with the required
        number of jtag idle vectors as element instead of making us of the repeat value of the vector.

        Args:
            count: The number of jtag idle vectors to return

        Returns:
            List[Mapping]: A list of vectors

        """
        return count*[self.jtag_idle_vector()]

    def jtag_reset(self):
        """
        Returns vectors to reset the jtag interface.


        Returns:
             List[Mapping]: A list of vectors

        """
        vectors = []
        self.set_jtag_default_values()
        self.vector_builder.trst = '0'
        vectors += [self.vector_builder.vector(comment="JTAG Reset")]
        vectors += 9*[self.vector_builder.vector()]
        self.vector_builder.trst = '1'
        self.vector_builder.tck = '1'
        self.vector_builder.tms = '0'
        vectors += 10*[self.vector_builder.vector()]
        return vectors

    def jtag_goto_shift_dr(self, comment=""):
        vectors = []
        self.set_jtag_default_values()
        self.vector_builder.tms = '1'
        self.vector_builder.tck = '0'  # Always change TMS and TDI one cycle earlier
        vectors.append(self.vector_builder.vector(comment=comment))
        self.vector_builder.tck = '1'
        self.vector_builder.tms = '0'
        vectors.append(self.vector_builder.vector())
        vectors.append(self.vector_builder.vector(comment="Goto shift DR"))
        return vectors

    def jtag_goto_shift_ir(self, comment=""):
        vectors = []
        self.set_jtag_default_values()
        self.vector_builder.tms = '1'
        self.vector_builder.tck = '0'  # Always change TMS and TDI one cycle earlier
        vectors.append(self.vector_builder.vector(comment=comment))
        self.vector_builder.tck = '1'
        vectors.append(self.vector_builder.vector())
        self.vector_builder.tms = '0'
        vectors.append(self.vector_builder.vector())
        vectors.append(self.vector_builder.vector(comment="Goto shift IR"))
        return vectors

    def jtag_shift(self, chain, expected_chain=None, comment="", noexit=False):
        self.set_jtag_default_values()
        self.vector_builder.tck = '1'
        self.vector_builder.tms = '0'
        vectors = []
        comment += "/Start shifting. "
        # Shift in the values
        for idx, bit in enumerate(chain):
            self.vector_builder.tdi = bit
            # Check if expected_chain != None and doesn't only contain don't care
            if expected_chain and not all(map(lambda x: x in ['x', 'X'], expected_chain)):
                self.vector_builder.tdo = expected_chain[idx]
            if idx == len(chain) - 1 and not noexit:
                self.vector_builder.tms = '1'
            vectors.append(self.vector_builder.vector(comment=comment + "Shift bit {}".format(bit) + (" expecting tdo {}".format(expected_chain[idx]) if expected_chain else "")))
            comment = "" # Only write full comment for first shift cycle

        # Update and go to idle
        if not noexit:
            vectors.append(self.vector_builder.vector(comment="goto Update DR/IR"))
            self.vector_builder.tms = '0'
            vectors.append(self.vector_builder.vector(comment="goto run test idle"))
            vectors.append(self.vector_builder.vector(comment="idle"))
        return vectors

    def jtag_set_ir(self, tap: JTAGTap, ir_value, comment=""):
        """Sets the IR value LSB first of the given JTAG tap while putting all other taps into BYPASS mode. The IR Value is written LSB first"""
        comment += "/Set IR of tap {} to [{}]".format(tap.name, BitArray(bin=ir_value))
        vectors = self.jtag_goto_shift_ir(comment)
        chain = ""
        for chain_elem in self.chain:
            if chain_elem == tap:
                chain += ir_value[::-1]
            else:
                chain += chain_elem.reg_bypass.IR_value[::-1]

        # Now we are in Shift IR state
        vectors += self.jtag_shift(chain, comment=comment)
        return vectors

    def jtag_set_dr(self, tap: JTAGTap, dr_value, expected_dr_value=None, comment="", noexit=False):
        """Sets the DR value LSB first of the given JTAG tap. If expected_dr_value is not None, the read value will be matched against it. This function assumes that all other taps are in bypass mode."""
        comment += "/Set DR of tap {} to [{}]".format(tap.name, BitArray(bin=dr_value))
        if expected_dr_value and not all(map(lambda x: x in ['x', 'X'], expected_dr_value)):
            comment += " expecting to read {}".format(expected_dr_value)
        vectors = self.jtag_goto_shift_dr(comment)
        # Now we are in Shift DR state
        chain = ""
        for chain_elem in self.chain:
            if chain_elem == tap:
                chain += dr_value[::-1]
            else:
                chain += '0'

        expected_chain = ""
        if expected_dr_value:
            for chain_elem in self.chain:
                if chain_elem == tap:
                    expected_chain += expected_dr_value[::-1]
                else:
                    expected_chain += 'X'
        vectors += self.jtag_shift(chain, expected_chain, comment, noexit)
        return vectors

    def read_reg(self, tap: JTAGTap, reg: JTAGRegister, reg_length, expected_value=None, comment=""):
        """Returns the vectors to read from the given register from the JTAG TAP with the given name. """
        vectors = []
        if not reg in tap.registers:
            raise ValueError("The supplied JTAG register does belong to the supplied JTAG tap")
        vectors += self.jtag_set_ir(tap, reg.IR_value, comment=comment)
        vectors += self.jtag_set_dr(tap, dr_value=reg_length * '0', expected_dr_value=expected_value, comment="Read value from DR. Expected value: {}".format(expected_value))
        return vectors

    def write_reg(self, tap, reg, value, comment=""):
        """Returns the vectors to write to the given register from the JTAG TAP with the given name. """
        vectors = []
        if not reg in tap.registers:
            raise ValueError("The supplied JTAG register does belong to the supplied JTAG tap")
        vectors += self.jtag_set_ir(tap, reg.IR_value, comment=comment)
        vectors += self.jtag_set_dr(tap, dr_value=value, comment="Write value {} to DR.".format(value))
        return vectors

    def poll_reg(self, tap, reg, expected_value, max_retries, idle_cycles, comment=""):
        """Poll the given register until the expected value is read back waiting 'idle_cycles' number of jtag clock cycles between every poll. This number must be a multiple of 8 in order to be able to reconstruct the results on the ASIC tester"""
        condition_vectors = self.read_reg(tap, reg, len(expected_value), expected_value, comment=comment)

        # Pad the condition vectors to be a multiple of 8
        condition_vectors = pad_vectors(condition_vectors, self.jtag_idle_vectors(1))
        idle_vectors = self.jtag_idle_vectors(8)
        vectors = self.vector_builder.matched_loop(condition_vectors, idle_vectors, max_retries)
        vectors += self.jtag_idle_vectors(8) #Make sure there are at least 8 normal vectors before the next matched loop by insertion idle instructions
        return vectors