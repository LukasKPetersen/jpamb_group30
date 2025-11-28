import random
import threading
from typing import List

from fuzzer_syntactic_analysis.query import get_static_variables_combinations
import interpreter
from fuzzer import Fuzzer, Strategy
from jpamb import jvm
from jpamb.model import Input
from central_expansion import fair_product, generators_for_method
import logging



class CentralExpansionAndSyntaticAnalysisStrategy(Strategy):
    def __init__(self, method_signature: jvm.AbsMethodID, argument: None|Input):
        self.method_signature = method_signature
        self.argument = argument # FIXME: is this needed???
        self.checked = set()
    
    def run(self):
        # Set of actual program execution outputs encountered (ok, divide by zero, etc.)
        outputs_encountered = set()
        stop_event = threading.Event()

        def fuzz_loop(static_method_inputs: List[Input], stop_event):
            if not self.method_signature.extension.params:
                input_val = []
                method_input: Input = Input(values=(*input_val,))
                outputs_encountered.add(interpreter.run(self.method_signature, method_input, stop_event))
                return
            
            
            # fuzz static inputs first
            while not stop_event.is_set() and static_method_inputs:
                method_input: Input = static_method_inputs.pop()
                # logging.debug(f"Fuzzing with static input: {method_input}")
                outputs_encountered.add(interpreter.run(self.method_signature, method_input, stop_event))
            
            # fuzz with centrally expanded inputs
            generators = generators_for_method(self.method_signature)
            if generators:  # Only if there are parameters
                for generated_input in fair_product(*generators):
                    if stop_event.is_set():
                        break
                    # logging.debug(f"Fuzzing with generated input: {generated_input}")
                    outputs_encountered.add(interpreter.run(self.method_signature, Input(values=generated_input), stop_event))


        static_method_inputs = get_static_variables_combinations(self.method_signature)

        # Start fuzzing in a separate thread
        t = threading.Thread(target=fuzz_loop, args=(static_method_inputs, stop_event,))
        t.daemon = True
        t.start()
        t.join(timeout=6)

        if t.is_alive():
            stop_event.set()
            t.join()

        for output in outputs_encountered:
            if output == "not done":
                continue
            # if output == "*":
            #     # print(f"{output};50%")
            #     continue
            print(f"{output};100%")
        exit(0)

class CentralExpansionAndSyntaticAnalysisFuzzer(Fuzzer):
    def __init__(self, method_signature: jvm.AbsMethodID, argument: None|Input):
        strategy = CentralExpansionAndSyntaticAnalysisStrategy(method_signature, argument)
        super().__init__(strategy)