from dumpling.Common.ElfParser import ElfParser
from bitstring import BitArray
from dumpling.Common.HP93000 import HP93000VectorWriter
from dumpling.Common.PulpJTAGTapRosetta import PULPJTagTapRosetta
from dumpling.Common.VectorBuilder import VectorBuilder
from dumpling.Drivers.JTAG import JTAGDriver
from dumpling.JTAGTaps.RISCVDebugTap import RISCVDebugTap, RISCVReg

pins = {
        'chip_reset' : {'name': 'pad_reset_n', 'default': '0'},
        'trst': {'name': 'pad_jtag_trst', 'default': '1'},
        'tms': {'name': 'pad_jtag_tms', 'default': '0'},
        'tck': {'name': 'pad_jtag_tck', 'default': '0'},
        'tdi': {'name': 'pad_jtag_tdi', 'default': '0'},
        'tdo': {'name': 'pad_jtag_tdo', 'default': 'X'}
    }
FC_CORE_ID = BitArray('0x003e0')

vector_builder = VectorBuilder(pins)
jtag_driver = JTAGDriver(vector_builder)

# Instantiate the two JTAG taps in Rosetta
riscv_debug_tap = RISCVDebugTap(jtag_driver)
pulp_tap = PULPJTagTapRosetta(jtag_driver)
# Add the taps to the jtag chain in the right order
jtag_driver.add_tap(riscv_debug_tap)
jtag_driver.add_tap(pulp_tap)

