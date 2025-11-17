import jpamb
from jpamb import jvm
from dataclasses import dataclass
from typing import Iterable, TypeVar
import sign_abstraction

import sys
from loguru import logger
from typing import Set

logger.remove()
logger.add(sys.stderr, format="[{level}] {message}")

methodid, input = jpamb.getcase()
print(f"This is the methodid: {methodid}\nThis is the input: {input}")

@dataclass
class PC:
    method: jvm.AbsMethodID
    offset: int

    def __iadd__(self, delta):
        self.offset += delta
        return self

    def __add__(self, delta):
        return PC(self.method, self.offset + delta)
    
    def set(self, delta):
        self.offset = delta
        return self

    def __str__(self):
        return f"{self.method}:{self.offset}"


@dataclass
class Bytecode:
    suite: jpamb.Suite
    methods: dict[jvm.AbsMethodID, list[jvm.Opcode]]

    def __getitem__(self, pc: PC) -> jvm.Opcode:
        try:
            opcodes = self.methods[pc.method]
        except KeyError:
            opcodes = list(self.suite.method_opcodes(pc.method))
            self.methods[pc.method] = opcodes

        return opcodes[pc.offset]


@dataclass
class Stack[T]:
    items: list[T]

    def __bool__(self) -> bool:
        return len(self.items) > 0

    @classmethod
    def empty(cls):
        return cls([])

    def peek(self) -> T:
        return self.items[-1]

    def pop(self) -> T:
        return self.items.pop(-1)

    def push(self, value):
        self.items.append(value)
        return self

    def __str__(self):
        if not self:
            return "ϵ"
        return "".join(f"{v}" for v in self.items)


suite = jpamb.Suite()
bc = Bytecode(suite, dict())

V = TypeVar("V") # Value
AV = TypeVar("AV") # Abstract Value

@dataclass
class PerVarFrame[AV]:
    locals: dict[int, V]
    stack: Stack[AV]

    def __le__(self, other: "PerVarFrame[AV]") -> bool:
        return self.locals.items() <= other.locals.items() # TODO: make a proper ordering

    # instead of a `from_method` method as in the original interpreter, we can have an `abstract` method
    def abstract(method: jvm.AbsMethodID) -> "PerVarFrame[AV]":
        return PerVarFrame({}, Stack.empty())

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

    def __str__(self):
        locals = ", ".join(f"{k}:{v}" for k, v in sorted(self.locals.items()))
        return f"<{{{locals}}}, {self.stack}>"

@dataclass
class AState:
    frames: Stack[PerVarFrame[AV]]

    @classmethod
    def initialstate_from_method(cls, methodid: jvm.AbsMethodID) -> "StateSet[AState]":
        initial_frame = PerVarFrame.abstract(methodid)
        initial_state = cls(frames=Stack([initial_frame]))
        initial_pc = PC(method=methodid, offset=0)
        return StateSet(per_inst={initial_pc: initial_state}, needswork={initial_pc})

@dataclass
class StateSet[AState]:
    per_inst : dict[PC, AState]
    needswork : set[PC]

    def per_instruction(self):
        for pc in self.needswork: 
            yield (pc, self.per_inst[pc])

    # sts |= astate
    def __ior__(self, astate):
        old = self.per_inst[astate] 
        self.per_inst[astate.pc] |= astate
        if old != self.per_inst[astate.pc]:
            self.needswork.add(astate.pc)
    
    def __str__(self):
        return "{" + ", ".join(f"{pc}: {state}" for pc, state in self.per_inst.items()) + "}"

# abstract stepping function
def step(state: AState) -> Iterable[AState | str]:
    frame = state.frames.peek()
    opr = bc[frame.pc]
    logger.debug(f"STEP {opr}\n{state}")
    match opr:
        case jvm.Ifz(condition=con, target=target):
            for ([va1], after) in state.group(pop=[jvm.Int()]):
                for res in after.binary(con, va1, 0):
                    match res:
                        case (True, after):
                            after.frame.update(pc=target)  # deleted a `yield`
                        case (False, after):
                            after.frame.update(pc=pc+1)  # deleted a `yield`
                        case err:
                            err  # deleted a `yield`
        case a:
            a.help()
            raise NotImplementedError(f"Don't know how to handle: {a!r}")

def manystep(sts : StateSet[AState]) -> Iterable[AState | str]:
    return

# perform abstract interpretation
MAX_STEPS = 100
final = {}
sts = AState.initialstate_from_method(methodid) # TODO: better naming - ´sts´ refer to set of states
for i in range(MAX_STEPS):
    for s in manystep(sts):
        if isinstance(s, str):
            final.add(s)
        else:
            sts |= s
logger.info(f"The following final states {final} is possible in {MAX_STEPS}")

# grouping per instruction (§2.1)
for pc, state in sts.per_instruction():
    match bc[pc]:
        case jvm.Binary(type=jvm.Int(), operant=opr):
            match opr:
                case jvm.Add():
                    pass
                case _:
                    raise NotImplementedError(f"Don't know how to handle: {opr!r}")
        case _:
            raise NotImplementedError(f"Don't know how to handle: {bc[pc]!r}")

# grouping per variable (§2.2)
for ([va1, va2], after) in state.group(pop=[jvm.Int(), jvm.Int()]):
    match (va1, va2):
        case (sign_abstraction.SignSet(), sign_abstraction.SignSet()):
            result = sign_abstraction.Arithmetic.add_signsets(va1, va2)
            assert isinstance(result, sign_abstraction.SignSet)
            after.stack.push(result)
        case _:
            raise NotImplementedError(f"Don't know how to handle: {va1!r}, {va2!r}")
        
# doing the operation (§2.3)

# if the result is not a failure, we update the state with the new value, using an update method.
for res in after.binary(opr, va1, va2):
    match res:
        case (va3, after):
            after.frame.update(push=[va3], pc=pc+1)  # deleted a `yield`
        case err:
            err  # deleted a `yield`