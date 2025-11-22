class Strategy:
    """ Base class for fuzzing strategies. """
    def run(self):
        """ Run the strategy. """
        raise NotImplementedError()


class Fuzzer:
    """ Base class for fuzzers. """
    def __init__(self, strategy: Strategy):
        self.strategy = strategy

    def run(self):
        """ Run the fuzzer using its strategy. """
        self.strategy.run()

# start at 0, -1, +1, -2, +2, ...
class CentralExpansionFuzzer(Fuzzer):
    """ Fuzzer that expands inputs from the center outwards. """
    def __init__(self):
        raise NotImplementedError()
        strategy = None
        super().__init__(strategy)