# Manuel Eggimann <meggimann@iis.ee.ethz.ch>
#
# Copyright (C) 2020-2022 ETH Zürich
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from bitstring import BitArray

class JTAGRegister:
    """
    A convenience class used by class `JTAGTap` to instantiate JTAG Registers.

    Args:
        name(str): The human readable name of the JTAG Tap (e.g. "IDCODE").
        IR_value(str): The value that must be written to the IR to select this JTAG Register has a binary string (
        e.g. "0100111")
        default number.
    """
    def __init__(self, name, IR_value, DR_size, default_value:str=None):
        self.name = name
        self.IR_value = IR_value
        self.DR_size = DR_size
        self.default_value = default_value
        self.tap = None

    def atach(self, tap: 'JTAGTap'):
        self.tap = tap

    def read(self, reg_length = None, expected_value:str=None, comment=""):
        """
        A convenience function to generate vectors to read from a JTAG register using dot notation (e.g. my_tap.reg1.read().

        The stimuli generated will first select the correct IR and put all other TAPs into bypass. Then it will shift DR the data out of chip.

         Internally, the register will forward the call to the JTAG driver.
        This function will fail if the JTAGRegister has not yet been attached to a JTAG Tap!

        Args:
            reg_length(int): The number of bits to read. If none, the DR length attribute of the register itself will be used.
            expected_value(str): A string (hex or binary notation) of a value to compare to the data register. If none, the value will not be compared ('X')
            comment(str): An optional comment with which to annotate the generated vectors

        Returns:
            List[Mapping]: A list of vectors
        """
        if self.tap is None:
            raise ValueError("Cannot read from a JTAGRegister that has not yet been attached to a JTAGTap. Please call reg.attach(tap) first.")
        return self.tap.driver.read_reg(self.tap, self, self.DR_size if reg_length is None else reg_length, expected_value, comment)


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
        jtag_reg.atach(self)
        return jtag_reg
