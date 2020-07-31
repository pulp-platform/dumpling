import bitstring
from bitstring import BitArray
bitstring.set_lsb0(True) #Enables the experimental mode to index LSB with 0 instead of the MSB (see thread https://github.com/scott-griffiths/bitstring/issues/156)
from dumpling.Common.VectorBuilder import VectorBuilder

class JTAGRegister:
    def __init__(self, name, IR_value, default_ID_size):
        self.name = name
        self.IR_value = IR_value
        self.default_ID_size = default_ID_size


class JTAGTap:
    """
        Create a JTAGTap config object with a user defineable name, the given IR
        register size. The init function will automatically add the BYPASS
        register to the JTAGTap object
        """

    def __init__(self, name, IR_size, driver: 'JTAGDriver'):
        self.name = name
        self.IR_size = IR_size
        self.registers = []
        self.driver = driver
        self.reg_bypass = self._add_reg(JTAGRegister('BYPASS', IR_size * "1", 1))

    def _add_reg(self, jtag_reg: JTAGRegister):
        self.registers.append(jtag_reg)
        return jtag_reg


class JTAGDriver:
    def __init__(self, vector_writer: VectorBuilder):
        self.vector_writer = vector_writer
        self.chain = []

    def set_jtag_default_values(self):
        self.vector_writer.tck = '0'
        self.vector_writer.trst = '1'
        self.vector_writer.tms = '0'
        self.vector_writer.tdi = '0'
        self.vector_writer.tdo = 'X'

    def add_tap(self, jtag_tap: JTAGTap):
        """
        Adds a new JTAG TAP to the chain controlled by this driver instance.

        The TAPs are supposed to be added in the same order that the TDI signal passes through them.
        E.g. if the TDI enters the chip, passes TAP1, leaves TAP1 through it's TDO, enters TAP2 through the TDI and finally leaves the chip through TDO,
        register the TAPs in the following order::

          self.add_tap(TAP1)
          self.add_tap(TAP2)


        Args:
            jtag_tap: The JTAG TAP to add to the chain.

        Returns:

        """
        self.chain.insert(0, jtag_tap)


    def jtag_idle_vector(self, repeat=1, comment=None):
        self.set_jtag_default_values()
        return self.vector_writer.vector(repeat=repeat, comment=comment)

    def jtag_idle_vectors(self, count=1):
        return count*[self.jtag_idle_vector()]

    def jtag_reset(self):
        vectors = []
        self.set_jtag_default_values()
        self.vector_writer.trst = '0'
        vectors += [self.vector_writer.vector(comment="JTAG Reset")]
        vectors += 9*[self.vector_writer.vector()]
        self.vector_writer.trst = '1'
        self.vector_writer.tck = '1'
        self.vector_writer.tms = '0'
        vectors += 10*[self.vector_writer.vector()]
        return vectors

    def jtag_goto_shift_dr(self, comment=""):
        vectors = []
        self.set_jtag_default_values()
        self.vector_writer.tms = '1'
        self.vector_writer.tck = '0'  # Always change TMS and TDI one cycle earlier
        vectors.append(self.vector_writer.vector(comment=comment))
        self.vector_writer.tck = '1'
        self.vector_writer.tms = '0'
        vectors.append(self.vector_writer.vector())
        vectors.append(self.vector_writer.vector(comment="Goto shift DR"))
        return vectors

    def jtag_goto_shift_ir(self, comment=""):
        vectors = []
        self.set_jtag_default_values()
        self.vector_writer.tms = '1'
        self.vector_writer.tck = '0'  # Always change TMS and TDI one cycle earlier
        vectors.append(self.vector_writer.vector(comment=comment))
        self.vector_writer.tck = '1'
        vectors.append(self.vector_writer.vector())
        self.vector_writer.tms = '0'
        vectors.append(self.vector_writer.vector())
        vectors.append(self.vector_writer.vector(comment="Goto shift IR"))
        return vectors

    def jtag_shift(self, chain, expected_chain=None, comment="", noexit=False):
        self.set_jtag_default_values()
        self.vector_writer.tck = '1'
        self.vector_writer.tms = '0'
        vectors = []
        comment += "/Start shifting. "
        # Shift in the values
        for idx, bit in enumerate(chain):
            self.vector_writer.tdi = bit
            # Check if expected_chain != None and doesn't only contain don't care
            if expected_chain and not all(map(lambda x: x in ['x', 'X'], expected_chain)):
                self.vector_writer.tdo = expected_chain[idx]
            if idx == len(chain) - 1 and not noexit:
                self.vector_writer.tms = '1'
            vectors.append(self.vector_writer.vector(comment=comment+"Shift bit {}".format(bit)+(" expecting tdo {}".format(expected_chain[idx]) if expected_chain else "")))
            comment = "" # Only write full comment for first shift cycle

        # Update and go to idle
        if not noexit:
            vectors.append(self.vector_writer.vector(comment="goto Update DR/IR"))
            self.vector_writer.tms = '0'
            vectors.append(self.vector_writer.vector(comment="goto run test idle"))
            vectors.append(self.vector_writer.vector(comment="idle"))
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
        vectors = self.vector_writer.matched_loop(condition_vectors, idle_vectors, max_retries)
        vectors += self.jtag_idle_vectors(8) #Make sure there are at least 8 normal vectors before the next matched loop by insertion idle instructions
        return vectors