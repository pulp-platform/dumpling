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
import math
import re
from pathlib import Path

import bitstring
import click
from dumpling.Common.ElfParser import ElfParser
from bitstring import BitArray
bitstring.lsb0 = True #Enables the experimental mode to index LSB with 0 instead of the MSB (see thread https://github.com/scott-griffiths/bitstring/issues/156)
from dumpling.Common.HP93000 import HP93000VectorWriter
from dumpling.JTAGTaps.PulpJTAGTapRosetta import PULPJTagTapRosetta
from dumpling.Common.VectorBuilder import VectorBuilder
from dumpling.Drivers.JTAG import JTAGDriver
from dumpling.JTAGTaps.RISCVDebugTap import RISCVDebugTap, RISCVReg



pins = {
        'chip_reset' : {'name': 'pad_reset_n', 'default': '1'},
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


#Commands
pass_VectorWriter = click.make_pass_decorator(HP93000VectorWriter)


#Entry point for all rosetta related commands
@click.group()
@click.option("--port-name", '-p', type=str, default="jtag_and_reset_port", show_default=True)
@click.option("--wtb-name", '-w', type=str, default="multiport_ext_clk_wvtbl", show_default=True)
@click.option('--output', '-o', type=click.Path(exists=False, file_okay=True, writable=True, path_type=Path), default="vectors.avc", show_default=True)
@click.option("--device_cycle_name", '-d', type=str, default="dvc_1", )
@click.pass_context
def rosetta(ctx: click.Context, port_name:str, wtb_name:str, device_cycle_name:str, output:Path) ->None:
    """Generate stimuli for the TSMC65 Rosetta chip.
    """
    #Instantiate the vector writer and attach it to the command context so subcommands can access it.
    vector_builder.init()
    ctx.obj = HP93000VectorWriter(stimuli_file_path=Path(output), pins=pins, port=port_name, device_cycle_name=device_cycle_name, wtb_name=wtb_name)



@rosetta.command()
@click.option("--blade/--no-blade", default=True, help="Enables/Disables the BLADE SRAM macros in Rosetta", show_default=True)
@click.option("--edram/--no-edram", default=True, help="Enables/Disables the eDRAM macros in Rosetta", show_default=True)
@click.option("--hd-mem-backend", type=click.Choice(['edram', 'scm']), default='scm', show_default=True,
              help="Switches between SCM and eDRAM as the memory backend for the HD-Computing Accelerator")
@click.option("--bypass-soc-fll", is_flag=True, default=False, help="Bypass the FLL for the SoC clock and use the external SoC clock instead.")
@click.option("--bypass-per-fll", is_flag=True, default=False, help="Bypass the FLL for the Peripheral clock and use the external clock instead.")
@pass_VectorWriter
def write_soc_config(vector_writer: HP93000VectorWriter, blade:bool, edram:bool, hd_mem_backend:str, bypass_soc_fll:bool, bypass_per_fll:bool):
    """
    Writes the given static configuration value to the apb_soc_ctrl register.

    """
    with vector_writer as writer:
        # Set the config register to bypass the internall FLLs and release hardreset
        vectors = pulp_tap.init_pulp_tap()
        vectors += pulp_tap.set_config_reg(BitArray(8), soc_fll_bypass_en=bypass_soc_fll, per_fll_bypass_en=bypass_per_fll, blade_disable=not blade, edram_disable=not edram,
                                          hd_mem_backend_use_edram=hd_mem_backend == 'edram')
        writer.write_vectors(vectors)

@rosetta.command()
@click.option("--blade/--no-blade", default=True, help="Enables/Disables the BLADE SRAM macros in Rosetta", show_default=True)
@click.option("--edram/--no-edram", default=True, help="Enables/Disables the eDRAM macros in Rosetta", show_default=True)
@click.option("--hd-mem-backend", type=click.Choice(['edram', 'scm']), default='scm', show_default=True,
              help="Switches between SCM and eDRAM as the memory backend for the HD-Computing Accelerator")
@click.option("--bypass-soc-fll", is_flag=True, default=False, help="Bypass the FLL for the SoC clock and use the external SoC clock instead.")
@click.option("--bypass-per-fll", is_flag=True, default=False, help="Bypass the FLL for the Peripheral clock and use the external clock instead.")
@pass_VectorWriter
def verify_soc_config(vector_writer: HP93000VectorWriter, blade, edram, hd_mem_backend, bypass_soc_fll, bypass_per_fll):
    """
    Verify that the flags within the current value of the soc config register has the given values
    """
    with vector_writer as writer:
        vectors = pulp_tap.init_pulp_tap()
        vectors += pulp_tap.verify_config_reg(BitArray(8), soc_fll_bypass_en=bypass_soc_fll, per_fll_bypass_en=bypass_per_fll, blade_disable=not blade, edram_disable=not edram,
                                          hd_mem_backend_use_edram=hd_mem_backend == 'edram')
        writer.write_vectors(vectors)



@rosetta.command()
@click.option("--elf", "-e", required=True, type=click.Path(exists=True, file_okay=True, dir_okay=False), help="The path to the elf binary to preload.")
@click.option("--return-code", '-r', type=click.IntRange(min=0, max=255), help="Set a return code to check against during end of computation detection. A matched loop will be inserted to achieve ")
@click.option("--eoc-wait-cycles", '-w', default=0, type=click.IntRange(min=0), help="If set to a non zero integer, wait the given number of cycles for end of computation check and bdon't use ")
@click.option("--verify/--no-verify", default=True, help="Enables/Disables verifying the content written to L2.", show_default=True)
@click.option("--blade/--no-blade", default=True, help="Enables/Disables the BLADE SRAM macros in Rosetta", show_default=True)
@click.option("--edram/--no-edram", default=True, help="Enables/Disables the eDRAM macros in Rosetta", show_default=True)
@click.option("--hd-mem-backend", type=click.Choice(['edram', 'scm']), default='scm', show_default=True, help="Switches between SCM and eDRAM as the memory backend for the HD-Computing "
                                                                                                                 "Accelerator")
@click.option("--bypass-soc-fll", is_flag=True, default=False, help="Bypass the FLL for the SoC clock and use the external SoC clock instead.")
@click.option("--bypass-per-fll", is_flag=True, default=False, help="Bypass the FLL for the Peripheral clock and use the external clock instead.")
@click.option("--compress", '-c', is_flag=True, default=False, show_default=True, help="Compress all vectors by merging subsequent identical vectors into a single vector with increased repeat value.")
@click.option("--no-reset", is_flag=True, default=False, show_default=True, help="Don't reset the chip before executing the binary. Helpfull for debugging and to keep custom config preloaded via "
                                                                                 "JTAG.")
@pass_VectorWriter
def execute_elf(writer: HP93000VectorWriter, elf, return_code, eoc_wait_cycles, verify, blade, edram, hd_mem_backend, bypass_soc_fll, bypass_per_fll, compress, no_reset):
    """Generate vectors to load and execute the given elf binary.

    The command parses the binary supplied with the '--elf' parameter and
    writes the generated stimuli to the given OUTPUT file. Additionally to the
    AVC ASCII output, a .wtb and .tmf with identical basename is created. The
    vectors take care of resetting the chip, halting the core, preloading the
    binary into L2 memory with optional verification and resuming the core. If
    an expected return code is supplied with the optional '--return-code' flag,
    either a matched loop (polling) check or a single check (after a
    configurable number of idle clock cycles) for end of computation is added
    to the end of the stimuli vectors depending on the value of
    --eoc-wait-cycles.

    """

    with writer as vector_writer:
        vectors = []
        if not no_reset:
            # Assert reset
            vector_builder.chip_reset = 0
            # Wait 1us
            reset_vector = vector_builder.vector(comment="Assert reset")
            vectors.append(vector_builder.loop([reset_vector], 10))
            # Write the vectors to disk
            vector_writer.write_vectors(vectors, compress=compress)

            # Reset the jtag interface and wait for 10 cycles
            vectors = jtag_driver.jtag_reset()
            vectors += jtag_driver.jtag_idle_vectors(10)
            vector_writer.write_vectors(vectors, compress=compress)

        # Set the config register to bypass the internall FLLs and release hardreset
        vectors = pulp_tap.set_config_reg(BitArray(8), soc_fll_bypass_en=bypass_soc_fll, per_fll_bypass_en=bypass_per_fll, blade_disable=not blade, edram_disable=not edram,
                                          hd_mem_backend_use_edram=hd_mem_backend=='edram')
        vectors += jtag_driver.jtag_idle_vectors(10)
        vector_builder.chip_reset = 1
        vectors += [vector_builder.vector(comment="Release hard reset")]
        vector_writer.write_vectors(vectors, compress=compress)

        # Start boot procedure
        # Halt fabric controller
        vectors = riscv_debug_tap.init_dmi()
        vectors += riscv_debug_tap.set_dmactive(True)
        vectors += riscv_debug_tap.halt_hart_no_loop(FC_CORE_ID, wait_cycles=100)

        vector_writer.write_vectors(vectors, compress=compress)

        # Write the boot address into dpc
        parser = ElfParser()
        parser.add_binary(elf)
        entry_address = BitArray(int=parser.get_entry(), length=32)
        vectors = riscv_debug_tap.write_reg_abstract_cmd_no_loop(RISCVReg.CSR_DPC, BitArray(entry_address), comment="Writing boot address to DPC")
        vector_writer.write_vectors(vectors, compress=compress)

        # Verify boot address
        vectors = riscv_debug_tap.read_reg_abstract_cmd_no_loop(RISCVReg.CSR_DPC, BitArray(entry_address).bin, wait_cycles=10, comment="Reading DPC")
        vector_writer.write_vectors(vectors, compress=compress)

        # Load L2 memory
        vectors = pulp_tap.init_pulp_tap()
        vectors += pulp_tap.loadL2(elf_binary=elf)
        vector_writer.write_vectors(vectors, compress=compress)

        # Optionally verify the data we just wrote to L2
        if verify:
            vectors = pulp_tap.verifyL2_no_loop(elf, comment="Verify the content of L2 to match the binary.")
            vector_writer.write_vectors(vectors)

        # Resume core
        vectors = riscv_debug_tap.init_dmi()  # Change JTAG IR to DMIACCESS
        vectors += riscv_debug_tap.resume_harts_no_loop(FC_CORE_ID, wait_cycles=100)
        vector_writer.write_vectors(vectors, compress=compress)

        # Wait for end of computation by polling EOC register address
        if return_code != None:
            if eoc_wait_cycles <= 0:
                vectors = riscv_debug_tap.wait_for_end_of_computation(return_code, idle_vector_count=100, max_retries=10)
            else:
                vectors = [jtag_driver.jtag_idle_vector(repeat=1000, comment="Waiting for computation to finish before checking EOC register.")]
                vectors += riscv_debug_tap.check_end_of_computation(return_code, wait_cycles=5000)
            vector_writer.write_vectors(vectors, compress=compress)



@rosetta.command()
@click.argument('address_value_mappings', nargs=-1)
@click.option("--verify/--no-verify", default=True, help="Enables/Disables verifying the content written to L2.", show_default=True)
@click.option("--loop/--no-loop", default=False, help="If true, all matched loops  in the verification vectors are replaced with reasonable delays to avoid the usage of matched loops altogether.")
@click.option("--compress", '-c', is_flag=True, default=False, show_default=True, help="Compress all vectors by merging subsequent identical vectors into a single vector with increased repeat value.")
@pass_VectorWriter
def write_mem(vector_writer: HP93000VectorWriter, address_value_mappings, verify, loop, compress):
    """
    Perform write transactions to the system bus.

    Each value of ADDRESS_VALUE_MAPPING should be of the kind 'address=value[#Comment]' where
    address and value are 32-bit value in hex notation and comment is an optional comment to attach to the vectors.
    E.g.::

    write_mem "0x1c008080=0xdeadbeef#Write to start address" 0x1c008084=0x12345678

    If the optional verify flag is provided, the data written will be read back for verification.
    """
    #Parse all address value mappings and store the result in a list of tuples
    data = []
    pattern = re.compile(r"(?P<address>0x[0-9a-fA-F]{8})=(?P<value>0x[0-9a-fA-F]{0,8})(?:#(?P<comment>.*))?")

    #Use stdin if the user did not provide any arguments
    if not address_value_mappings:
        address_value_mappings = click.get_text_stream('stdin')
    for mapping in address_value_mappings:
        match = pattern.match(mapping)
        if not match:
            raise click.BadArgumentUsage("Illegal argument: {}. Must be of the form 0x<32-bit address>=0x<value>#comment".format(mapping))
        else:
            data.append((BitArray(match.group('address')), BitArray(match.group('value')), match.group('comment')))

    with vector_writer as writer:
        vectors = pulp_tap.init_pulp_tap()
        for address, value, comment in data:
            vectors += pulp_tap.write32(start_addr=address, data=[value], comment=comment if comment else "")
            writer.write_vectors(vectors, compress=compress)
        if verify:
            for address, value, comment in data:
                if loop:
                    vectors = pulp_tap.read32(start_addr=address, expected_data=[value], comment=comment)
                else:
                    vectors = pulp_tap.read32_no_loop(start_addr=address, expected_data=[value], comment=comment if comment else "")
                writer.write_vectors(vectors, compress=compress)


@rosetta.command()
@click.argument('address_value_mappings', nargs=-1)
@click.option("--loop/--no-loop", default=False, help="If true, all matched loops in the verification vectors are replaced with reasonable delays to avoid the usage of matched loops altogether.")
@click.option("--compress", '-c', is_flag=True, default=False, show_default=True, help="Compress all vectors by merging subsequent identical vectors into a single vector with increased repeat value.")
@click.option("--use-pulp-tap", is_flag=True, default=False, show_default=True, help="Use the PULP TAP for readout instead of the RISC-V Debug module.")
@click.option("--wait-cycles", type=click.IntRange(0), default=10, show_default=True, help="The number of cycles to wait for the read operation to complete.")
@pass_VectorWriter
def verify_mem(vector_writer: HP93000VectorWriter, address_value_mappings, loop, compress: bool, use_pulp_tap: bool, wait_cycles: int):
    """
    Perform read transactions on the system bus and compare the values with expected ones

    Each value of ADDRESS_VALUE_MAPPING should be of the kind 'address=value[#Comment]' where
    address and value are 32-bit value in hex notation and comment is an optional comment to attach to the vectors.
    E.g.::

    write_mem "0x1c008080=0xdeadbeef#Write to start address" 0x1c008084=0x12345678

    """
    #Parse all address value mappings and store the result in a list of tuples
    data = []
    pattern = re.compile(r"(?P<address>0x[0-9a-f]{8})=(?P<value>0x[0-9a-fA-F]{0,8})(?:#(?P<comment>.*))?")
    for mapping in address_value_mappings:
        match = pattern.match(mapping)
        if not match:
            raise click.BadArgumentUsage("Illegal argument: {}. Must be of the form 0x<32-bit address>=0x<value>#comment".format(mapping))
        else:
            data.append((BitArray(match.group('address')), BitArray(match.group('value')), match.group('comment')))

    with vector_writer as writer:
        vector_builder.init()
        if use_pulp_tap:
            vectors = pulp_tap.init_pulp_tap()
        else:
            vectors = riscv_debug_tap.init_dmi()
            vectors += riscv_debug_tap.enable_sbreadonaddr()
        for address, value, comment in data:
            if loop:
                if use_pulp_tap:
                    vectors += pulp_tap.read32(start_addr=address, expected_data=[value], comment=comment)
                else:
                    vectors += riscv_debug_tap.readMem(addr=address, expected_data=value, comment=comment)
            else:
                if use_pulp_tap:
                    vectors += pulp_tap.read32_no_loop(start_addr=address, expected_data=[value], wait_cycles=wait_cycles, comment=comment if comment else "")
                else:
                    vectors += riscv_debug_tap.readMem_no_loop(addr=address, expected_data=value, wait_cycles=wait_cycles, comment=comment)
            writer.write_vectors(vectors, compress=compress)

@rosetta.command()
@click.option('--wait-cycles','-w', type=click.IntRange(min=1), default=10, show_default=True, help="The number of cycles to wait before verifying that core was actually resumed.")
@pass_VectorWriter
def resume_core(vector_writer: HP93000VectorWriter, wait_cycles):
    """
    Generate vectors to resume the core.

    The vectors will instruct the RISC-V debug module via JTAG to resume the core and after a configurable number of JTAG clock cycles will verify that the core is in the 'running' state.
    """
    with vector_writer as writer:
        vectors = riscv_debug_tap.init_dmi()
        vectors += riscv_debug_tap.resume_harts_no_loop(FC_CORE_ID, "Resuming core", wait_cycles=wait_cycles)
        writer.write_vectors(vectors)

@rosetta.command()
@click.option('--reset-cycles','-r', type=click.IntRange(min=1), default=10, show_default=True, help="The number of cycles to assert the chip reset line.")
@pass_VectorWriter
def reset_chip(vector_writer: HP93000VectorWriter, reset_cycles):
    """
    Generate vectors to reset the core and the jtag interface

    """
    with vector_writer as writer:
        vectors = []
        vector_builder.chip_reset = 0
        vectors += [vector_builder.vector(reset_cycles, comment="Assert chip reset")]
        vector_builder.chip_reset = 1
        vectors += jtag_driver.jtag_reset()
        vectors += jtag_driver.jtag_idle_vectors(10)
        vectors += riscv_debug_tap.init_dmi()
        vectors += riscv_debug_tap.set_dmactive(True)
        vectors += jtag_driver.jtag_idle_vectors(10)
        writer.write_vectors(vectors)

@rosetta.command()
@click.option('--pc', type=str, help="Read programm counter and compare it with the expected value provided")
@click.option('--resume/--no-resume', show_default=True, default=False, help="Resume the core after reading the program counter.")
@click.option('--assert-reset', is_flag=True, show_default=True, default=False, help="Assert the chip reset line for the whole duration of the generated vectors.")
@click.option('--wait-cycles','-w', type=click.IntRange(min=1), default=10, show_default=True, help="The number of cycles to wait before verifying that core was actually halted.")
@pass_VectorWriter
def halt_core_verify_pc(vector_writer: HP93000VectorWriter, pc, resume, assert_reset, wait_cycles):
    """Halt the core, optionally reading the program counter and resuming the core.

    This command is mainly useful to verify or debug the execution state of a program. The generated vectors will halt the core,
    optionally read the programm counter and optionally resume the core.

    E.g.::
    dumpling rosetta -o halt_core.avc halt_core_verify_pc --pc 0c1c008080 --resume

    Will halt the core, comparing the programm counter to the value 0x1c008080 and resuming the core afterwards.

    The --assert-reset flag allows to keep the reset line asserted during the exeuction of core halt procedure. This allows to halt the core before it statrts to execute
    random data right after reset.
    """
    with vector_writer as writer:
        if assert_reset:
            vector_builder.chip_reset = 0
        vectors = riscv_debug_tap.init_dmi()
        vectors += riscv_debug_tap.halt_hart_no_loop(FC_CORE_ID, wait_cycles=wait_cycles)
        if pc:
            expected_pc = BitArray(pc)
            expected_pc = (32-len(expected_pc)) + expected_pc #Extend to 32-bit
            vectors += riscv_debug_tap.read_reg_abstract_cmd_no_loop(RISCVReg.CSR_DPC, BitArray(expected_pc,length=32).bin, wait_cycles=wait_cycles, comment="Reading DPC")
            if resume:
                vectors += riscv_debug_tap.resume_harts_no_loop(FC_CORE_ID, comment="Resuming the core", wait_cycles=wait_cycles)
        writer.write_vectors(vectors)


@rosetta.command()
@click.argument("FLL", type=click.Choice(['PER_FLL', 'SOC_FLL']))
@click.argument("MULT", type=click.IntRange(min=1, max=65535))
@click.option("--clk-div", default='4', type=click.Choice(['1','2','4','8','16','32','64','128','256']), help="Change the clock division factor of DCO clock to FLL output clock.")
@click.option("--lock", '-l', is_flag = True, default=False, show_default=True, help="Gate the output clock with the FLL lock signal")
@click.option("--tolerance", default=512, show_default=True, type=click.IntRange(min=0, max=2047), help="The margin around the target multiplication factor for clock to be considered stable.")
@click.option("--stable-cycles", default=16, show_default=True, type=click.IntRange(min=0, max=63), help="The number of stable cycles unil LOCK is asserted.")
@click.option("--unstable-cycles", default=16, show_default=True, type=click.IntRange(min=0, max=63), help="The number of unstable cycles unil LOCK is de-asserted.")
@click.option("--enable-dithering", is_flag=True, default=False, show_default=True, help="Enable dithering for higher frequency resolution.")
@click.option("--loop-gain-exponent", default=-7, type=click.IntRange(min=-15,max=0), show_default=True,  help="The gain exponent of the feedback loop. Gain = 2^<value>")
@click.option('--wait-cycles','-w', type=click.IntRange(min=1), default=200, show_default=True, help="The number of jtag cycles to wait between writing the two FLL config registers.")
@pass_VectorWriter
def change_freq(vector_writer: HP93000VectorWriter, fll, mult, clk_div, lock, tolerance, stable_cycles, unstable_cycles, loop_gain_exponent, enable_dithering, wait_cycles):
    """ Generate vectors to change the multiplication factor (MULT) and various other settings of the internal FLLs .

        The FLL argument determines which of the two independent FLLs in Rosetta is configured. 

        The output frequency of the FLL is freq =<ref_freq>*<MULT>/<clk-div>.

        Since we need to write to two registers, we have to wait long enough for the FLL to become stable again before we try to modify the second registers.

    """
    with vector_writer as writer:
        vectors = pulp_tap.init_pulp_tap()
        if fll == "SOC_FLL":
            config1_address = BitArray('0x1a100004')
            config2_address = BitArray('0x1a100008')
        else: #Cannot be anything other than soc_peripherals. Click lib will make sure of this at invocation.
            config1_address = BitArray('0x1a100014')
            config2_address = BitArray('0x1a100018')
        clk_div_value = int(math.log2(int(clk_div)))+1
        config1_value = bitstring.pack('0b1, bool, uint:4, uint:10=136, uint:16', lock, clk_div_value, mult)
        config2_value = bitstring.pack('bool, 0b000, uint:12, uint:6, uint:6, uint:4', enable_dithering, tolerance, stable_cycles, unstable_cycles, -loop_gain_exponent)

        vectors += pulp_tap.write32(start_addr=config1_address, data=[config1_value], comment="Configure {}".format(fll))
        vectors += [jtag_driver.jtag_idle_vector(repeat=wait_cycles)]
        vectors += pulp_tap.write32(start_addr=config2_address, data=[config2_value], comment="Configure {}".format(fll))
        writer.write_vectors(vectors)


@rosetta.command()
@click.option("--return-code", default=0, type=click.IntRange(min=0, max=255), show_default=True, help="The expected return code.")
@click.option('--wait-cycles','-w', type=click.IntRange(min=1), default=10, show_default=True, help="The number of cycles to wait for the eoc_register read operation to complete.")
@pass_VectorWriter
def check_eoc(vector_writer, return_code, wait_cycles):
    """ Generate vectors to check for the end of computation.

    Programs compiled with the pulp-sdk or pulp-runtime write their exit code to a special end-of-computation register
    in APB SOC Control when they leave main. The expected return code (by default 0) can be modified to assume any value
    between 0 and 255. """

    with vector_writer as writer:
        vectors = riscv_debug_tap.init_dmi()
        vectors += riscv_debug_tap.check_end_of_computation(return_code, wait_cycles=wait_cycles)
        writer.write_vectors(vectors)

