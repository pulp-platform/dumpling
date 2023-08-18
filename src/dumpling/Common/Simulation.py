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
from numbers import Real
import os
from pathlib import Path
from typing import Union, Literal, Coroutine, Awaitable, Callable

import cocotb
from _decimal import Decimal
from dumpling.Common.HP93000 import HP93000VectorReader
from cocotb.binary import BinaryValue
from cocotb.triggers import Timer
from cocotb.handle import NonHierarchyObject


class CocotbVectorDriver:
    """
    A class to simulate the application of vectors with
    an RTL simulator.

    The class mimics the behavior of the ASIC tester's wave table. It provides cocotb coroutines that apply the given
    vectors to a device under test. It addition to the dut handle to which the vectors are applied that constructor also
    expects the pins declaration corresponding to the vectors according to the format specified in `VectorBuilder`
    docstring. There is however one additional key that needs to be provided for each pin:

    The CocotbDriver expects the pinlist 'pins' to contain a wavefun key for each pin with an associated coroutine
    function that will be used to apply values to the signal or sample them. This allows to mimick the behavior of the
    ASIC tester wavetable by arbitrary shifting the time were data is applied or sampled.

    Each wavefunction is supposed to have the signature like the following example wavefunction::

       async def my_stimuli_appl_fun(signal, value):
         await cocotb.trigger.Timer('2', units='ns') #Wait 2ns
         signal <= value

    signals is a CocoTB simulation object handle (a signal handle) and value is the pin state character of the pin
    for the current vector.
    The example wavefunction from above will advance simulation time by 2ns before applying the value to the signals.

    The CocotbVectorDriver will fork the supplied coroutine for each pin supplying the cocotb pin signal handle to
    'signal' and the value of the current vector to 'value' as arguments to the coroutine function. After all
    wavefunction coroutines have terminated, the driver proceeds with applying the next vectors. It is good practice to
    have all wavefunctions associated with each pin consume the same amount of simulated time (i.e. the period of the
    device cycle on the ASIC tester)

    The CocotbDriver class contains static helper functions to generate wavefunction coroutines for commonly used
    wavetable schemes ('simple_clock_gen_wavefun', 'simple_stimuli_appl_wavefun' and 'simple_response_acq_wavefun').

    Args:
        pins: The pins description dictionary as described in the Docstring of VectorWriter.
        dut: The cocotb design under thest simulation handle i.e. the toplevel module where stimuli should be applied to.

    See Also:
        - CocoTB Documentation: https://docs.cocotb.org/en/stable/
        - Documentation of the apply_vector method.

    """

    @staticmethod
    def simple_clock_gen_wavefun(
        period_ps: Union[float, Decimal],
        duty_cycle: Union[float, Decimal] = 0.5,
        start_high=False,
        idle_low=True,
    ):
        """
        This function returns a coroutine wavefunction for clock application with the given period.

        The coroutine will apply a clock to signal if the value is '1'. The clock can either be idle-Low or idle-high when value is '0'.
        The start_high parameter decides whether the clock period a rising edge (start_high='False') or if the rising edge is applied after (1-duty_cycle)*period_ps

        Args:
            period_ps: The clock period used by the returned coroutine
            duty_cycle: The percentage of 'period_ps' the clock remains High
            start_high: Whether to start the period with a Rising Edge or with the Falling Edge
            idle_low: If signal should remain low when value is '0' or if it should remain high

        Returns:
            A coroutine for stimuli application that can be passed to 'CocotbDriver' as a wavefunction in the pin dictionary.
        """

        # Cast both, period and duty_cycle to Decimal to avoid floating-point inaccuracy issues
        period_ps = Decimal(period_ps)
        duty_cycle = Decimal(duty_cycle)

        @cocotb.coroutine
        async def wavefun(
            signal: NonHierarchyObject,
            value: Union[bool, Literal[0, 1, "0", "1"]],
        ) -> bool:
            if value in [True, 1, "1"]:  # Make sure it's not a string '0'
                if start_high:
                    signal.value = 1
                    await Timer(period_ps * duty_cycle, units="ps")
                    signal.value = 0
                    await Timer(period_ps * (1 - duty_cycle), units="ps")
                else:
                    signal.value = 0
                    await Timer(period_ps * (1 - duty_cycle), units="ps")
                    signal.value = 1
                    await Timer(period_ps * (duty_cycle), units="ps")
            else:
                if idle_low:
                    signal.value = 0
                else:
                    signal.value = 0
                await Timer(period_ps, units="ps")
            return True  # No missmatchs since we only apply data

        return wavefun

    @staticmethod
    def simple_stimuli_appl_wavefun(
        appl_delay_ps: Union[Decimal, float], wave_period_ps: Union[Decimal, float]
    ):
        """
        This function returns a coroutine wavefunction that implements a basic waveform applier that assigns signal the given value the desired skew after the rising clock edge.

        Args:
            signal: the signal to assign to
            value: the value to assign to the signal
            appl_delay_ps (int): the application delay in unit pico second
            wave_period_ps (int): the period of one wave, e.g. the period of the reference clock

        Returns:
            A coroutine for stimuli application that can be passed to 'CocotbDriver' as a wavefunction in the pin dictionary.

        """
        # Cast both, period and duty_cycle to Decimal to avoid floating-point inaccuracy issues
        appl_delay_ps = Decimal(appl_delay_ps)
        wave_period_ps = Decimal(wave_period_ps)

        @cocotb.coroutine
        async def wavefun(signal: NonHierarchyObject, value):
            await Timer(appl_delay_ps, units="ps")
            signal.value = BinaryValue(value)
            await Timer(wave_period_ps - appl_delay_ps, units="ps")
            return True  # No missmatch since we do only apply data

        return wavefun

    @staticmethod
    def simple_response_acq_wavefun(
        acq_delay_ps: Union[Decimal, float], wave_period_ps: Union[Decimal, float]
    ) -> Callable[
        [NonHierarchyObject, Union[str, int, Literal["x", "X"]]], Awaitable[bool]
    ]:
        """
        This function returns a coroutine wavefunction that implements a basic waveform acquisition that samples the signal and compares it to the given value 'acq_delay_s' before the end of
        'wave_period_s'.

         I.e. the signal the value will be assigned to signal after 'wave_period_ps' - 'appl_delay_ps' pico seconds and the wavefun returns the result of the check
        after wave_period_ps has elapsed after its invocation.

        Args:
            acq_delay_ps (int): The skew before the end of the wave_period when the signal is sampled and compared.
            wave_period_ps (int): The period of the wave in unit pico seconds

        Returns:
            A coroutine for response acquisition that can be passed to 'CocotbDriver' as a wavefunction in the pin dictionary.

        """
        # Cast both, period and duty_cycle to Decimal to avoid floating-point inaccuracy issues
        acq_delay_ps = Decimal(acq_delay_ps)
        wave_period_ps = Decimal(wave_period_ps)

        @cocotb.coroutine
        async def wavefun(
            signal: NonHierarchyObject,
            expected_value: Union[str, int, Literal["x", "X"]],
        ) -> bool:
            match = True
            await Timer(wave_period_ps - acq_delay_ps, units="ps")
            if expected_value not in ["X", "x"]:
                if not signal.value.is_resolvable or signal != BinaryValue(
                    expected_value
                ):
                    signal._log.error(
                        "Mismatch on signal {}: Was {} instead of {}".format(
                            signal._name, signal.value, expected_value
                        )
                    )
                    match = False
            await Timer(acq_delay_ps, units="ps")
            return match

        return wavefun

    def __init__(self, pins, dut):
        self.pins = pins
        self.dut = dut
        self.vectors = []
        self.dut = dut

    async def simulate_avc(self, avc_path: os.PathLike) -> bool:
        """
        A Coroutine that parses and iteratively applies all vectors from an AVC file to the device under test.

        Args:
            avc_path: The path of the AVC files who's vectors shall be applied to the DUT.

        Returns:
            bool: True, if all vectors were applied without any missmatches, False otherwise.

        See Also:
            `apply_vector`

        """
        self.dut._log.info("Applying vector from file {} to DUT.".format(avc_path))
        with HP93000VectorReader(avc_path, self.pins) as reader:
            passed: bool = True
            for vector in reader.vectors():
                passed &= await self.apply_vector(vector)
            return passed

    async def apply_vectors(self, vectors) -> bool:
        """
        Apply a list of vectors in intermediate representation to the DUT.

        Args:
            vectors:

        Returns:
            bool: True if all vectors passed (had no missmatches), False otherwise.

        """
        self.dut._log.info("Applying {} vectors to DUT...".format(len(vectors)))
        passed = True
        for vector in vectors:
            passed &= await self.apply_vector(vector)
        return passed

    async def apply_vector(self, vector) -> bool:
        """
        Applies a single vector in intermediate representation (dictionary) to the DUT.

        This coroutine will print the annotated comment of the vector (if not None or "") to the simulation log and
        applies the vector to the DUT (appropriately handling matched_loops, normal loops and the 'repeat' value of
        normal vectors.

        Args:
            vector: The vector to apply to the DUT

        Returns:
            True, if there was a missmatch during application of the vector, False otherwise
        """
        passed = False
        if vector.get("comment", "") not in ["", None]:
            self.dut._log.info(vector["comment"])
        if vector["type"] == "vec":
            passed = True
            for i in range(vector["repeat"]):
                # Generate a list of all wavefunction coroutines
                wavefuns = []
                for logical_name, value in vector["vector"].items():
                    wavefun = self.pins[logical_name]["wavefun"]
                    signal = getattr(self.dut, self.pins[logical_name]["name"])
                    wavefuns.append(wavefun(signal, value))
                # Execute all wavefunction in parallel and wait for completion
                forked_coroutines = [cocotb.fork(wavefun) for wavefun in wavefuns]
                # Aggregate the return value of each coroutine. If one wavefun returns false, the aggregated return value is also false
                for forked_coroutine in forked_coroutines:
                    passed &= await forked_coroutine

        elif vector["type"] == "match_loop":
            retry_count = 0
            # Try applying the condition vectors
            self.dut._log.info(
                "Starting matched loop with {} retries.".format(vector["retries"])
            )
            while not passed and retry_count <= vector["retries"]:
                passed = True
                for cond_vector in vector["cond_vectors"]:
                    passed &= await self.apply_vector(cond_vector)
                if not passed:
                    retry_count += 1
                    self.dut._log.info(
                        "Matched loop condition failed. Applying idle vectors and trying again."
                    )
                    for idle_vector in vector["idle_vectors"]:
                        await self.apply_vector(idle_vector)
            if not passed:
                self.dut._log.error(
                    "Matched loop failed permanently for {} retries.".format(
                        retry_count
                    )
                )
            else:
                self.dut._log.info(
                    "Matched loop succeeded after {} retries".format(retry_count)
                )
        elif vector["type"] == "loop":
            passed = True
            self.dut._log.info(
                "Looping over {} vectors for {} iterations.".format(
                    len(vector["loop_body"]), vector["repeat"]
                )
            )
            for i in range(vector["repeat"]):
                for loop_vector in vector["loop_body"]:
                    passed &= await self.apply_vector(loop_vector)
        return passed
