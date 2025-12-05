import random
import threading
from typing import Any, List, final
from loguru import logger

from query_used import get_static_variables_combinations, generate_every_input_combination
import interpreter
from fuzzer import Fuzzer, Strategy
from jpamb import jvm
from jpamb.model import Input
from central_expansion import fair_product, generators_for_method
from static_analysis import analyze_method
from interval_abstraction import Interval, Infinity
from wager import PercentWager, Wager

class FullStrategy(Strategy):
    def __init__(self, method_signature: jvm.AbsMethodID, argument: None|Input):
        self.method_signature = method_signature
        self.argument = argument # FIXME: is this needed???
        self.checked = set()
    
    def run(self):
        # Set of actual program execution outputs encountered (ok, divide by zero, etc.)
        outputs_encountered = set()
        final_states = set()
        stop_event = threading.Event()

        def fuzz_loop(static_method_inputs: List[Input], stop_event):
            
            # fuzz the intervals that the unbounded static analysis found
            # NOTE: if the intervals are too large (over THRESHOLD), we skip fuzzing the intervals
            # and go directly to centrally expanded inputs. Because there is a good change that
            # it is just the full range of integers. This can be improved in the future.
            unbounded_final_states, input_intervals = analyze_method(self.method_signature.encode())
            final_states.update(unbounded_final_states)
            # FIXME: This should also happen first (or just earlier) because if the infinite loop
            # has no arguments then it is still ran right now...
            # TODO: check if this is fine
            # if the unbounded analysis only returned "*", we know it is running forever
            # FIXME: It fails `jpamb.cases.Calls.callsAssertFib` and is therefore disabled for now...
            # if len(final_states) == 1 and "*" in final_states:
            #     logger.warning("Static analysis returned only '*', indicating non-termination.")
            #     logger.warning("Skipping interval-based input generation.")
            #     outputs_encountered.add("*")
            #     return
            
            # NOTE: this is with the assumption that every method are deterministic.
            # If any method is non-deterministic, we need to re-run with the same input multiple times.
            if not self.method_signature.extension.params:
                input_val = []
                method_input: Input = Input(values=(*input_val,))
                outputs_encountered.add(interpreter.run(self.method_signature, method_input, stop_event))
                return
            
            # logger.debug(f"static_method_inputs: {static_method_inputs}")
            # fuzz static inputs first
            while not stop_event.is_set() and static_method_inputs:
                method_input: Input = static_method_inputs.pop()
                # logging.debug(f"Fuzzing with static input: {method_input}")
                outputs_encountered.add(interpreter.run(self.method_signature, method_input, stop_event))
            
            THRESHOLD = 2000

            is_interval_exceeding_threshold = False
            is_argument_type_supported = True
            for param_intervals in input_intervals:
                if (param_intervals.upper - param_intervals.lower) > THRESHOLD:
                    is_interval_exceeding_threshold = True
                    break

            if not is_interval_exceeding_threshold:
                input_dict: dict[jvm.Type, List[Any]] = {}
                # find argument type and populate input_dict (not from input_intervals)
                for i, param_type in enumerate(self.method_signature.extension.params):
                    match param_type:
                        case jvm.Int():
                            intervals = input_intervals[i]
                            if isinstance(intervals.lower, Infinity) or isinstance(intervals.upper, Infinity):
                                raise NotImplementedError(f"Cannot generate inputs for unbounded interval: {intervals}")
                            range_values = list(range(intervals.lower, intervals.upper + 1))
                            # logger.warning(f"Generated range for Int parameter: {range_values}")
                            input_dict[jvm.Int()] = range_values
                        case jvm.Boolean():
                            input_dict[jvm.Boolean()] = [True, False]
                        case _:
                            is_argument_type_supported = False
                            break


                if is_argument_type_supported:
                    interval_inputs = generate_every_input_combination(input_dict, self.method_signature.extension.params)
                    for method_input in interval_inputs:
                        if stop_event.is_set():
                            break
                        outputs_encountered.add(interpreter.run(self.method_signature, method_input, stop_event))
            
            # fuzz with centrally expanded inputs
            generators = generators_for_method(self.method_signature)
            if generators:  # Only if there are parameters
                for generated_input in fair_product(*generators):
                    if stop_event.is_set():
                        break
                    # logging.debug(f"Fuzzing with generated input: {generated_input}")
                    outputs_encountered.add(interpreter.run(self.method_signature, Input(values=generated_input), stop_event))


        # final_states, input_intervals = analyze_method(self.method_signature.encode())

        # raise NotImplementedError(final_states, input_intervals)

        static_method_inputs = get_static_variables_combinations(self.method_signature)

        # Start fuzzing in a separate thread
        t = threading.Thread(target=fuzz_loop, args=(static_method_inputs, stop_event,))
        t.daemon = True
        t.start()
        t.join(timeout=10)

        if t.is_alive():
            stop_event.set()
            t.join()

        percent_wager = PercentWager()
        wager = Wager()
        # Adjust wager based on outputs encountered
        for end_state in final_states:
            percent_wager.set_value(end_state, 0.7)
            wager.set_value(end_state, 10)
            
        for output in outputs_encountered:
            if output == "not done":
                continue
            percent_wager.set_value(output, 1.0)
            wager.set_value(output, 10000)
          
        percent_wager.print_wager()
        # wager.print_wager()
          
        exit(0)

class FullFuzzer(Fuzzer):
    def __init__(self, method_signature: jvm.AbsMethodID, argument: None|Input):
        strategy = FullStrategy(method_signature, argument)
        super().__init__(strategy)