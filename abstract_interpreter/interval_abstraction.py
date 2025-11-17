from dataclasses import dataclass
from typing import TypeAlias

@dataclass
class Interval:
    lower: int
    upper: int
    # TODO: a better alternative than `list[int]`?
    K: TypeAlias = list[int]  # A set containing all the constants of the program

    @classmethod
    def empty(cls) -> "Interval":
        # We represent the empty interval by having lower > upper
        return cls(1, 0)

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

    # join operator (for lattice functionality)
    def __or__(self, other: "Interval") -> "Interval":
        if self.is_empty:
            return other
        if other.is_empty:
            return self
        return Interval(min(self.lower, other.lower), max(self.upper, other.upper))

    # meet operator (for lattice functionality)
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
        return set(range(interval.lower, interval.upper + 1))

    def __contains__(self, member: int):
        if self.is_empty:
            return False
        return self.lower <= member <= self.upper

    def __add__(self, other: "Interval") -> "Interval":
        if self.is_empty or other.is_empty:
            return Interval.empty()
        return Arithmetic.add(self, other)
    
    def widening(self, other: "Interval") -> "Interval":
        """Widening operator to ensure convergence in fixpoint computations"""
        
        def min_K_J(a: int, b: int, Ks: list[int]) -> int:
            """Function to return the largest element in K that is less than min(a,b)"""
            # assume that K is a sorted set
            Ks = Ks | self.empty()
            ret = Ks[0]
            for k in Ks:
                if k > min(a, b):
                    return ret
                else:
                    ret = k
            return ret
        
        def max_K_J(a: int, b: int, Ks: list[int]) -> int:
            """Function to return the smallest element in K that is greater than max(a,b)"""
            # assume that K is a sorted set
            Ks = Ks | self.empty()
            for k in Ks:
                if k >= max(a, b):
                    return k
            return Ks[-1]
        
        if self.is_empty:
            return other
        if other.is_empty:
            return self
        lower = min_K_J(self.lower, other.lower, self.K)
        upper = max_K_J(self.upper, other.upper, self.K)
        return Interval(lower, upper)

class Arithmetic:
    @staticmethod
    def add(a: Interval, b: Interval) -> Interval:
        return Interval(a.lower + b.lower, a.upper + b.upper)