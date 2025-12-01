from dataclasses import dataclass
from typing import TypeAlias, Literal

Sign : TypeAlias = Literal["+"] | Literal["-"] | Literal["0"]

@dataclass
class SignSet:
    signs : set[Sign]

    def __str__(self) -> str:
        return "{" + ", ".join(sorted(self.signs)) + "}"

    # ordering relation (to make into Partially Ordered Set - Poset)
    def __le__(self, other: "SignSet") -> bool:
        return self.signs.issubset(other.signs)
    
    # join operator (for lattice functionality)
    def __or__(self, other: "SignSet") -> "SignSet":
        return SignSet(self.signs | other.signs)
    
    # meet operator (for lattice functionality)
    def __and__(self, other: "SignSet") -> "SignSet":
        return SignSet(self.signs & other.signs)
    
    @classmethod
    def abstract(cls, items : set[int]): 
        signset = set()
        if 0 in items:
            signset.add("0")
        if any(x > 0 for x in items):
            signset.add("+")
        if any(x < 0 for x in items):
            signset.add("-")
        return cls(signset)
    
    def __contains__(self, member : int): 
        if (member == 0 and "0" in self.signs): 
            return True
        if (member > 0 and "+" in self.signs): 
            return True
        if (member < 0 and "-" in self.signs): 
            return True
        return False
    
    def __add__(self, other: "SignSet") -> "SignSet":
        return Arithmetic.add_signsets(self, other)
    
    def __sub__(self, other: "SignSet") -> "SignSet":
        return Arithmetic.subtract_signsets(self, other)
    
    def __mul__(self, other: "SignSet") -> "SignSet":
        return Arithmetic.multiply_signsets(self, other)
    
    def __truediv__(self, other: "SignSet") -> "SignSet":
        return Arithmetic.divide_signsets(self, other)

class Arithmetic:
    @staticmethod
    def add(a: Sign, b: Sign) -> SignSet:
        if a == "0":
            return SignSet({b})
        if b == "0":
            return SignSet({a})
        if a == "+" and b == "+":
            return SignSet({"+"})
        if a == "-" and b == "-":
            return SignSet({"-"})
        if (a == "+" and b == "-") or (a == "-" and b == "+"):
            return SignSet({"-", "0", "+"})
        raise ValueError("Invalid signs for addition.")
    
    @staticmethod
    def add_signsets(xs: SignSet, ys: SignSet) -> SignSet:
        result_signs: set[Sign] = set()
        # compute all pairwise additions and accumulate their sign results
        for x in xs.signs:
            for y in ys.signs:
                sum_signset = Arithmetic.add(x, y)  # returns a SignSet
                result_signs.update(sum_signset.signs)  # merge the inner signs
        return SignSet(result_signs)

    @staticmethod
    def subtract(a: Sign, b: Sign) -> SignSet:
        if b == "0":
            return SignSet({a})
        if a == "0":
            if b == "+":
                return SignSet({"-"})
            if b == "-":
                return SignSet({"+"})
        if a == b:
            return SignSet({"-", "0", "+"})
        if (a == "+" and b == "-"):
            return SignSet({ "+" })
        if (a == "-" and b == "+"):
            return SignSet({ "-" })
        raise ValueError("Invalid signs for subtraction.")
    
    @staticmethod
    def subtract_signsets(xs: SignSet, ys: SignSet) -> SignSet:
        result_signs = set()
        result_signs.update(Arithmetic.subtract(x, y).signs for x in xs.signs for y in ys.signs)
        return SignSet(result_signs)

    @staticmethod
    def multiply(a: Sign, b: Sign) -> SignSet:
        if a == "0" or b == "0":
            return SignSet({"0"})
        if a == b:
            return SignSet({ "+" })
        else:
            return SignSet({ "-" })

    @staticmethod
    def multiply_signsets(xs: SignSet, ys: SignSet) -> SignSet:
        result_signs = set()
        result_signs.update(Arithmetic.multiply(x, y).signs for x in xs.signs for y in ys.signs)
        return SignSet(result_signs)

    @staticmethod
    def divide(a: Sign, b: Sign) -> SignSet:
        if b == "0":
            raise ValueError("Division by zero is undefined.")
        if a == "0":
            return SignSet({"0"})
        if a == b:
            return SignSet({ "+" })
        else:
            return SignSet({ "-" })
        
    @staticmethod
    def divide_signsets(xs: SignSet, ys: SignSet) -> SignSet:
        result_signs = set()
        for x in xs.signs:
            for y in ys.signs:
                try:
                    result_signs.update(Arithmetic.divide(x, y).signs)
                except ValueError:
                    continue  # Skip division by zero
        return SignSet(result_signs)

class Comparison:
    @staticmethod
    def le(a: Sign, b: Sign) -> bool:
        if a == b:
            return True
        if a == "-" and b in {"0", "+"}:
            return True
        if a == "0" and b == "+":
            return True
        return False

    @staticmethod
    def ge(a: Sign, b: Sign) -> bool:
        if a == b:
            return True
        if a == "+" and b in {"0", "-"}:
            return True
        if a == "0" and b == "-":
            return True
        return False

    @staticmethod
    def gt(a: Sign, b: Sign) -> bool:
        if a == b:
            return False
        if a == "+" and b in {"0", "-"}:
            return True
        if a == "0" and b == "-":
            return False
        return False
    
    @staticmethod
    def lt(a: Sign, b: Sign) -> bool:
        if a == b:
            return False
        if a == "-" and b in {"0", "+"}:
            return True
        if a == "0" and b == "+":
            return True
        return False

    @staticmethod
    def compare(op: str, a: Sign, b: Sign) -> bool:
        if op == "le":
            return Comparison.le(a, b)
        elif op == "ge":
            return Comparison.ge(a, b)
        elif op == "gt":
            return Comparison.gt(a, b)
        elif op == "lt":
            return Comparison.lt(a, b)
        else:
            raise ValueError("Unsupported comparison operation.")
