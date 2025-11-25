import random
import threading
import queue
from loguru import logger

import interpreter
from fuzzer import Fuzzer, Strategy
from jpamb import jvm
import jpamb
from jpamb.model import Input
from CFG import CFG, Node, Edge
import queue

class CoverageGuidedStrategy(Strategy):
    """ Random input generation strategy. """
    def __init__(self, method_signature: jvm.AbsMethodID, argument: None|Input):
        self.method_signature = method_signature
        self.argument = argument # FIXME: is this needed???
        # Yes, we need argument. Create methods to 
        self.cfg = CFG(jpamb.Suite(), self.method_signature)
        self.all_edges = self.cfg.extract_all_edges() # A set with all edges
        self.global_coverage: set[Edge] = set()
        self.checked = set()
        #self.corpus = Queue()

        # laver en CFG
        # interpreteren og får en liste af edges
        # sammenligner du med CFG
        # Edge checking

        # Initial values begin
        # If new edges found -> use the same input but mutated
        # If no new edges are found -> revert back to random strategy 

        # state, traversed_edges = interpreter.run(method_signature, argument, None, True)
        # # set of edges from running the interpreter
        # traversed_edges = self.cfg.convert_to_set_of_edges(traversed_edges)
        

    def mutate_input(self, input: Input) -> Input:
        mutated_inputs= []

        for input in input.values:
            match input.type:
                case jvm.Int():
                    # Just doing one form of mutation to input
                    v = input.value
                    v += random.randint(-10, 10) # small range
                    mutated_inputs.append(jvm.Value.int(v))

                    # Following methods for mutations (int):
                    # 1 small integer decrements/increments
                    # 2 add/subtract a small range (what we do now)
                    # 3 bit flips
                    # 4 replace with a random integer (fallback)
                    # 5 interesting values (which is a specific set of values that are good to test with)
                case jvm.Boolean():
                    v = input.value
                    v = not v
                    mutated_inputs.append(jvm.Value.boolean(v))
                case jvm.Array(jvm.Int()):
                    arr = list(input.value)
                    if len(arr) > 0:
                        index = random.randint(0, len(arr)-1)
                        arr[index] = arr[index] + random.randint(-10, 10)
                    mutated_inputs.append(jvm.Value.array(jvm.Int(), arr))
                case jvm.Array(jvm.Char()):
                    arr = list(input.value)
                    if len(arr) > 0:
                        index = random.randint(0, len(arr)-1)
                        arr[index] = chr(random.randint(32, 126))
                    mutated_inputs.append(jvm.Value.array(jvm.Char(), arr))
                case _:
                    raise NotImplementedError(f"Mutation not implemented for type: {input}")
            
        return Input(values=mutated_inputs)
    
    def run(self):
        # Set of actual program execution outputs encountered (ok, divide by zero, etc.)
        outputs_encountered = set()
        stop_event = threading.Event()

        corpus: queue.Queue[Input] = queue.Queue()

        def fuzz_loop(stop_event):
            if not self.method_signature.extension.params:
                input_val = []
                method_input: Input = Input(values=(*input_val,))
                outputs_encountered.add(interpreter.run(self.method_signature, method_input, stop_event))
                return

            while not stop_event.is_set() and len(self.global_coverage) < len(self.all_edges):
                input_val = []


                if corpus.qsize() > 0:
                    method_input = corpus.get()
                else:
                    # Generate random inputs based on method signature
                    for elem in self.method_signature.extension.params:

                        match elem:
                            case jvm.Int():
                                val = random.randint(-2147483648, 2147483647) # -2^31 to (2^31)-1
                                input_val.append(jvm.Value.int(val))
                            case jvm.Boolean():  # boolean
                                val = random.choice([True, False])
                                input_val.append(jvm.Value.boolean(val))
                            case jvm.Array(jvm.Int()):
                                length = random.randint(0, 5)
                                array_vals = [random.randint(-2147483648, 2147483647) for _ in range(length)]
                                input_val.append(jvm.Value.array(jvm.Int(), array_vals))
                            case jvm.Array(jvm.Char()):
                                length = random.randint(0, 5)
                                array_vals = [chr(random.randint(32, 126)) for _ in range(length)]
                                input_val.append(jvm.Value.array(jvm.Char(), array_vals))
                            case _:
                                raise NotImplementedError(f"Random input generation not implemented for type: {elem}")

                    method_input: Input = Input(values=(*input_val,))

                state, traversed_edges = interpreter.run(self.method_signature, method_input, stop_event, True)
                outputs_encountered.add(state)
                traversed_edges = self.cfg.convert_to_set_of_edges(traversed_edges)

                if len(traversed_edges.difference(self.global_coverage)) != 0:

                    # Found interesting new edges - interesting input!
                    # Update global coverage
                    self.global_coverage.update(traversed_edges)
                    corpus.put(self.mutate_input(method_input))


        # Start fuzzing in a separate thread
        t = threading.Thread(target=fuzz_loop, args=(stop_event,))
        t.daemon = True
        t.start()
        t.join(timeout=1)

        if t.is_alive():
            stop_event.set()
            t.join()

        for output in outputs_encountered:
            if output == "not done":
                continue
            print(f"{output};100%")
        exit(0)
