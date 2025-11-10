from dataclasses import dataclass
from typing import TypeVar, Generic

from solutions.interpreter import Stack
from sign_abstraction import sign_abstraction

V = TypeVar("V") # Value
AV = TypeVar("AV") # Abstract Value

@dataclass
class PerVarFrame[AV]:
    locals: dict[int, V]
    stack: Stack[AV]

    def __le__(self, other: "PerVarFrame[AV]") -> bool:
        return self.locals.items() <= other.locals.items() # TODO: make a proper ordering

    def abstract(self) -> "PerVarFrame[AV]":
        return PerVarFrame(
            locals={var_id: sign_abstraction.abstract(self.locals[var_id]) for var_id in self.locals},
            stack=self.stack.abstract()
        )

    # meet operator (for lattice functionality)
    def __and__(self, other: "PerVarFrame[AV]") -> "PerVarFrame[AV]":
        return PerVarFrame(
            locals={var_id: self.locals[var_id] & other.locals[var_id] for var_id in self.locals},
            stack=self.stack & other.stack
        )
    
    # join operator (for lattice functionality)
    def __or__(self, other: "PerVarFrame[AV]") -> "PerVarFrame[AV]":
        return PerVarFrame(
            locals={var_id: self.locals[var_id] | other.locals[var_id] for var_id in self.locals},
            stack=self.stack | other.stack
        )


#### Pseudo elements ####
@dataclass
class Bot:
    # We can think of this as the "bottom" element in the lattice
    def __or__(self, other):
        return other
    
    def __and__(self, other):
        return self
    
    def __le__(self, other):
        return True
    
    def __str__(self):
        return "⊥"

@dataclass
class Err:
    # We can think of this as the "top" element in the lattice
    def __or__(self, other):
        return self
    
    def __and__(self, other):
        return other
    
    def __le__(self, other):
        return isinstance(other, Err)
    
    def __str__(self):
        return "Error"

@dataclass
class Ok:
    def __or__(self, other):
        if isinstance(other, Err):
            return other
        return self
    
    def __and__(self, other):
        return other
    
    def __le__(self, other):
        return isinstance(other, (Ok, Err))
    
    def __str__(self):
        return "Ok"
