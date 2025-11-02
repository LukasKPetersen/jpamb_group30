from dataclasses import dataclass

@dataclass
class Wager:
    """
    Fields (original labels -> attribute names):
      - "ok" -> ok
      - "divide by zero" -> divide_by_zero
      - "assertion error" -> assertion_error
      - "out of bounds" -> out_of_bounds
      - "null pointer" -> null_pointer
      - "*" -> inf
    """
    ok: float
    divide_by_zero: float
    assertion_error: float
    out_of_bounds: float
    null_pointer: float
    inf: float

    def __init__(self):
        self.ok = 0.5
        self.divide_by_zero = 0.1
        self.assertion_error = 0.1
        self.out_of_bounds = 0.1
        self.null_pointer = 0.1
        self.inf = 0.1

    def print_wager(self):
        print(
            f"ok;{self.ok*100}%\n"
            f"divide by zero;{self.divide_by_zero*100}%\n"
            f"assertion error;{self.assertion_error*100}%\n"
            f"out of bounds;{self.out_of_bounds*100}%\n"
            f"null pointer;{self.null_pointer*100}%\n"
            f"*;{self.inf*100}%"
        )