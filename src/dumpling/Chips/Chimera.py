# Lorenzo Leone <lleone@iis.ee.ethz.ch>
# Michael Rogenmoser <michaero@iis.ee.ethz.ch>
#
# Copyright (C) 2023 ETH Zürich
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
import math
import re
from pathlib import Path
from collections import namedtuple
from typing import Mapping

import bitstring
import click
from dumpling.Common.ElfParser import ElfParser
from bitstring import BitArray

bitstring.lsb0 = True  # Enables the experimental mode to index LSB with 0 instead of the MSB (see thread https://github.com/scott-griffiths/bitstring/issues/156)
from dumpling.Common.HP93000 import HP93000VectorWriter
from dumpling.JTAGTaps.PulpJTAGTap import PULPJtagTap
from dumpling.Common.VectorBuilder import PinDecl, VectorBuilder
from dumpling.Drivers.JTAG import JTAGDriver
from dumpling.JTAGTaps.RISCVDebugTap import RISCVDebugTap, RISCVReg

# Pin Setup

pins: Mapping[str, PinDecl] = {
    "chip_reset": {"name": "reset_n", "default": "1", "type": "input"},
    "trst": {"name": "jtag_trst", "default": "1", "type": "input"},
    "tms": {"name": "jtag_tms", "default": "0", "type": "input"},
    "tck": {"name": "jtag_tck", "default": "0", "type": "input"},
    "tdi": {"name": "jtag_tdi", "default": "0", "type": "input"},
    "tdo": {"name": "jtag_tdo", "default": "X", "type": "output"},
}

HOST_CORE_ID: BitArray = BitArray("0x00000")  # type: ignore until https://github.com/scott-griffiths/bitstring/issues/276 is closed

# GPIO Functional Modes?

# Minimal setup
vector_builder = VectorBuilder(pins)
jtag_driver = JTAGDriver(vector_builder)

# Instantiate the JTAG tap in chimera Chimera
riscv_debug_tap = RISCVDebugTap(jtag_driver, "0x1c5e5db3")
# Add the taps to the jtag chain in the right order
jtag_driver.add_tap(riscv_debug_tap)

# Commands
pass_VectorWriter = click.make_pass_decorator(HP93000VectorWriter)


# Entry point for all chimera related commands
@click.group()
@click.option(
    "--port-name", "-p", type=str, default="jtag_and_reset_port", show_default=True
)
@click.option("--wtb-name", "-w", type=str, default="multiport", show_default=True)
@click.option(
    "--output",
    "-o",
    type=click.Path(exists=False, file_okay=True, writable=True),
    default="vectors.avc",
    show_default=True,
)
@click.option(
    "--device_cycle_name",
    "-d",
    type=str,
    default="dvc_1",
)
@click.pass_context
def chimera(ctx, port_name, wtb_name, device_cycle_name, output):
    """Generate stimuli for the GF22 chimera chip."""
    # Instantiate the vector writer and attach it to the command context so subcommands can access it.
    vector_builder.init()
    ctx.obj = HP93000VectorWriter(
        stimuli_file_path=Path(output),
        pins=pins,
        port=port_name,
        device_cycle_name=device_cycle_name,
        wtb_name=wtb_name,
    )



@chimera.command()
@pass_VectorWriter
def verify_idcode(vector_writer):
    """Generate vectors to verify IDCODE of the RISC-V debug unit.

    Puts all taps except the debug unit into bypass mode and verifies the value of the debug units IDCODE register.
    In Chimera, the value should match "0x2f33ddb3". After the idcode read-out, the debug unit TAP remains selected.
    """
    with vector_writer as writer:
        vectors = riscv_debug_tap.verify_idcode()
        writer.write_vectors(vectors)
