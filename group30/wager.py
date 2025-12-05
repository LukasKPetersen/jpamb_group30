from dataclasses import dataclass

@dataclass
class PercentWager:
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
        self.inf = 0.01
        self.assertion_error = 0.01
        self.divide_by_zero = 0.01
        self.null_pointer = 0.01
        self.ok = 0.01
        self.out_of_bounds = 0.01
        
    def set_value(self, label: str, value: float):
        if label == "ok":
            self.ok = value
        elif label == "divide by zero":
            self.divide_by_zero = value
        elif label == "assertion error":
            self.assertion_error = value
        elif label == "out of bounds":
            self.out_of_bounds = value
        elif label == "null pointer":
            self.null_pointer = value
        elif label == "*":
            self.inf = value
        else:
            raise ValueError(f"Unknown label: {label}")

    def print_wager(self):
        print(
            f"*;{self.inf*100:.0f}%\n"
            f"assertion error;{self.assertion_error*100:.0f}%\n"
            f"divide by zero;{self.divide_by_zero*100:.0f}%\n"
            f"null pointer;{self.null_pointer*100:.0f}%\n"
            f"ok;{self.ok*100:.0f}%\n"
            f"out of bounds;{self.out_of_bounds*100:.0f}%"
        )

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
    ok: int
    divide_by_zero: int
    assertion_error: int
    out_of_bounds: int
    null_pointer: int
    inf: int

    def __init__(self):
        self.inf = -50
        self.assertion_error = -50
        self.divide_by_zero = -50
        self.null_pointer = -50
        self.ok = -50
        self.out_of_bounds = -50
        
    def set_value(self, label: str, value: int):
        if label == "ok":
            self.ok = value
        elif label == "divide by zero":
            self.divide_by_zero = value
        elif label == "assertion error":
            self.assertion_error = value
        elif label == "out of bounds":
            self.out_of_bounds = value
        elif label == "null pointer":
            self.null_pointer = value
        elif label == "*":
            self.inf = value
        else:
            raise ValueError(f"Unknown label: {label}")

    def print_wager(self):
        print(
            f"*;{self.inf}\n"
            f"assertion error;{self.assertion_error}\n"
            f"divide by zero;{self.divide_by_zero}\n"
            f"null pointer;{self.null_pointer}\n"
            f"ok;{self.ok}\n"
            f"out of bounds;{self.out_of_bounds}"
        )