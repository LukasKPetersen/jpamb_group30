from dataclasses import dataclass
from logging import log
from typing import TypeAlias
from typing import Iterable

class Infinity:
    """Represents positive or negative infinity"""
    def __init__(self, positive: bool = True):
        self.positive = positive
    
    def __str__(self):
        return "∞" if self.positive else "-∞"
    
    def __repr__(self):
        return f"Infinity({self.positive})"
    
    def __eq__(self, other):
        if isinstance(other, Infinity):
            return self.positive == other.positive
        return False
    
    def __lt__(self, other):
        if isinstance(other, Infinity):
            return not self.positive and other.positive
        return not self.positive  # -inf < any number
    
    def __le__(self, other):
        return self == other or self < other
    
    def __gt__(self, other):
        if isinstance(other, Infinity):
            return self.positive and not other.positive
        return self.positive  # +inf > any number
    
    def __ge__(self, other):
        return self == other or self > other
    
    def __add__(self, other):
        if isinstance(other, Infinity):
            if self.positive != other.positive:
                raise ValueError("Infinity - Infinity is undefined")
            return self
        return self  # inf + number = inf
    
    def __radd__(self, other):
        return self.__add__(other)
    
    def __sub__(self, other):
        if isinstance(other, Infinity):
            if self.positive == other.positive:
                raise ValueError("Infinity - Infinity is undefined")
            return self
        return self  # inf - number = inf
    
    def __rsub__(self, other):
        # number - inf = -inf (flip sign)
        return Infinity(not self.positive)
    
    def __mul__(self, other):
        if isinstance(other, Infinity):
            return Infinity(self.positive == other.positive)
        if other == 0:
            return 0
        # inf * positive = inf, inf * negative = -inf
        return Infinity(self.positive if other > 0 else not self.positive)
    
    def __rmul__(self, other):
        return self.__mul__(other)
    
    def __floordiv__(self, other):
        if isinstance(other, Infinity):
            return 0  # inf / inf = 0 (conservative approximation)
        if other == 0:
            raise ValueError("Division by zero")
        return Infinity(self.positive if other > 0 else not self.positive)
    
    def __rfloordiv__(self, other):
        # number / inf = 0
        return 0
    
    def __neg__(self):
        return Infinity(not self.positive)
    
    def __hash__(self):
        return hash(("Infinity", self.positive))

# Convenient constants
POS_INF = Infinity(True)
NEG_INF = Infinity(False)

@dataclass
class Interval:
    lower: int | Infinity
    upper: int | Infinity
    # K is the set of all constants of the program (`frozenset` is used to ensure uniqueness)
    K: frozenset[int] = frozenset()
    use_widening: bool = True

    def init_K(self, vals: Iterable[int]):
        self.K = frozenset(sorted(vals))

    def add_to_K(self, val: int):
        Ks = self.K | frozenset([val])
        self.K = frozenset(sorted(Ks))

    @classmethod
    def empty(cls) -> "Interval":
        # We represent the empty interval by having lower > upper
        return cls(POS_INF, NEG_INF)
    
    @classmethod
    def universal(cls) -> "Interval":
        return cls(NEG_INF, POS_INF)

    @property
    def is_empty(self) -> bool:
        return self.lower > self.upper

    def __str__(self) -> str:
        return "∅" if self.is_empty else f"[{self.lower}, {self.upper}]"

    # ordering relation (to make into Partially Ordered Set - Poset)
    def __le__(self, other: "Interval") -> bool:
        # empty interval is subset of every interval
        if self.is_empty:
            return True
        # non-empty cannot be subset of empty (handled above)
        if other.is_empty:
            return False
        return self.lower >= other.lower and self.upper <= other.upper

    # join 'U' operator (for lattice functionality)
    def __or__(self, other: "Interval") -> "Interval":
        if self.use_widening:
            return self.widening(other)
        
        if self.is_empty:
            return other
        if other.is_empty:
            return self
        # Preserve K from self (or other if self has no K)
        K = self.K if self.K else other.K
        result = Interval(min(self.lower, other.lower), max(self.upper, other.upper))
        result.K = K
        return result

    # meet '∩' operator (for lattice functionality)
    def __and__(self, other: "Interval") -> "Interval":
        if self.is_empty or other.is_empty:
            return Interval.empty()
        lower = max(self.lower, other.lower)
        upper = min(self.upper, other.upper)
        if lower > upper:
            return Interval.empty()
        return Interval(lower, upper)

    @classmethod
    def abstract(cls, items: set[int]):
        if not items:
            return cls.empty()
        return cls(min(items), max(items))
    
    @classmethod
    def concrete(cls, interval: "Interval") -> set[int]:
        if interval.is_empty:
            return set()
        # Cannot concretize infinite intervals
        if isinstance(interval.lower, Infinity) or isinstance(interval.upper, Infinity):
            raise ValueError("Cannot concretize an infinite interval")
        return set(range(interval.lower, interval.upper + 1))

    def __contains__(self, member: int | Infinity):
        if self.is_empty:
            return False
        return self.lower <= member <= self.upper

    def __add__(self, other: "Interval") -> "Interval":
        if self.is_empty or other.is_empty:
            return Interval.empty()
        return Arithmetic.add(self, other)
    
    def __sub__(self, other: "Interval") -> "Interval":
        if self.is_empty or other.is_empty:
            return Interval.empty()
        return Arithmetic.sub(self, other)
    
    def __mul__(self, other: "Interval") -> "Interval":
        if self.is_empty or other.is_empty:
            return Interval.empty()
        return Arithmetic.mul(self, other)
    
    def __truediv__(self, other: "Interval") -> "Interval":
        if self.is_empty or other.is_empty:
            return Interval.empty()
        return Arithmetic.div(self, other)
    
    def widening(self, other: "Interval") -> "Interval":
        """Widening operator to ensure convergence in fixpoint computations"""
        
        def min_K_J(a: int | Infinity, b: int | Infinity, Ks: frozenset[int]) -> int | Infinity:
            """Function to return the largest element in K that is less than min(a,b)"""
            # If either bound is -inf, return -inf
            if isinstance(a, Infinity) and not a.positive:
                return NEG_INF
            if isinstance(b, Infinity) and not b.positive:
                return NEG_INF
            # assume that K is a sorted set
            if not Ks:
                return NEG_INF  # If K is empty, widen to -inf
            ret = NEG_INF # prev value: next(iter(Ks))
            for k in Ks:
                if k > min(a, b):
                    return ret
                else:
                    ret = k
            return ret
        
        def max_K_J(a: int | Infinity, b: int | Infinity, Ks: frozenset[int]) -> int | Infinity:
            """Function to return the smallest element in K that is greater than max(a,b)"""
            # If either bound is +inf, return +inf
            if isinstance(a, Infinity) and a.positive:
                return POS_INF
            if isinstance(b, Infinity) and b.positive:
                return POS_INF
            # assume that K is a sorted set
            if not Ks:
                return POS_INF  # If K is empty, widen to +inf
            for k in Ks:
                if k >= max(a, b):
                    return k
            # result = next(iter(reversed(sorted(Ks))))
            return POS_INF

        if self.is_empty:
            return other
        if other.is_empty:
            return self
        lower = min_K_J(self.lower, other.lower, self.K)
        upper = max_K_J(self.upper, other.upper, self.K)
        result = Interval(lower, upper)
        result.K = self.K  # Preserve K
        return result

class Arithmetic:
    @staticmethod
    def add(a: Interval, b: Interval) -> Interval:
        result = Interval(a.lower + b.lower, a.upper + b.upper)
        result.K = a.K if a.K else b.K  # Preserve K
        return result
    
    @staticmethod
    def sub(a: Interval, b: Interval) -> Interval:
        result = Interval(a.lower - b.upper, a.upper - b.lower)
        result.K = a.K if a.K else b.K  # Preserve K
        return result
    
    @staticmethod
    def mul(a: Interval, b: Interval) -> Interval:
        products = [
            a.lower * b.lower,
            a.lower * b.upper,
            a.upper * b.lower,
            a.upper * b.upper,
        ]
        result = Interval(min(products), max(products))
        result.K = a.K if a.K else b.K  # Preserve K
        return result
    
    @staticmethod
    def div(a: Interval, b: Interval) -> Interval:
        if 0 in b:
            # Division by interval containing zero results in universal interval
            return Interval.universal()
        quotients = [
            a.lower // b.lower,
            a.lower // b.upper,
            a.upper // b.lower,
            a.upper // b.upper,
        ]
        return Interval(min(quotients), max(quotients))