class JTAGTap:
    """
        Create a JTAGTap config object with a user defineable name and the given IR register size in bits.

        The constructor will automatically add the BYPASS register to the JTAGTap object using the IR_size to determine
        the BYPASS register's IR value.

        Create subclasses of this class that implement tap specific functions. That 'driver' field contains a handle
        to the jtag_driver and allows interaction with jtag chain.

        Args:
            name(str): The human readable name of this TAP
            IR_size(int): The IR size of this TAP in bits
            driver('JTAGDriver')
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


class JTAGRegister:
    """
    A convenience class used by class `JTAGTap` to instantiate JTAG Registers.

    Args:
        name(str): The human readable name of the JTAG Tap (e.g. "IDCODE").
        IR_value(str): The value that must be written to the IR to select this JTAG Register has a binary string (
        e.g. "0100111")
        default number.
    """
    def __init__(self, name, IR_value, DR_size):
        self.name = name
        self.IR_value = IR_value
        self.DR_size = DR_size