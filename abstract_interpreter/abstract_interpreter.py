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

@dataclass(frozen=True)
class PC:
    method: jvm.AbsMethodID
    offset: int

    def __add__(self, delta):
        return PC(self.method, self.offset + delta)
    
    def set(self, delta):
        return PC(self.method, delta)

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
    locals: dict[int, AV]  # Changed from V to AV
    stack: Stack[AV]

    def __le__(self, other: "PerVarFrame[AV]") -> bool:
        return self.locals.items() <= other.locals.items() # TODO: make a proper ordering

    # instead of a `from_method` method as in the original interpreter, we can have an `abstract` method
    @staticmethod
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
    pc: PC

    def __or__(self, other: "AState") -> "AState":
        """Join operator for states - used when merging states at the same program point"""
        if self.pc != other.pc:
            raise ValueError("Cannot join states at different program points")
        
        # For now, simple implementation - should join frames
        # In a more sophisticated implementation, would need to join corresponding frames
        return self  # Placeholder - needs proper implementation
    
    def __eq__(self, other: "AState") -> bool:
        """Equality check for states"""
        return (self.pc == other.pc and 
                str(self.frames) == str(other.frames))  # Simple comparison

    @classmethod
    def initialstate_from_method(cls, methodid: jvm.AbsMethodID) -> "StateSet":
        initial_frame = PerVarFrame.abstract(methodid)
        initial_pc = PC(method=methodid, offset=0)
        initial_state = cls(frames=Stack([initial_frame]), pc=initial_pc)
        return StateSet(per_inst={initial_pc: initial_state}, needswork={initial_pc})

@dataclass
class StateSet:
    per_inst : dict[PC, AState]
    needswork : set[PC]

    def per_instruction(self):
        # Copy the set to avoid modification during iteration
        work = list(self.needswork)
        self.needswork.clear()
        for pc in work: 
            yield (pc, self.per_inst[pc])

    # sts |= astate
    def __ior__(self, astate: AState):
        pc = astate.pc
        if pc in self.per_inst:
            old = self.per_inst[pc]
            new = old | astate  # Use join operator
            if new != old:
                self.per_inst[pc] = new
                self.needswork.add(pc)
        else:
            self.per_inst[pc] = astate
            self.needswork.add(pc)
        return self
    
    def __str__(self):
        return "{" + ", ".join(f"{pc}: {state}" for pc, state in self.per_inst.items()) + "}"

# abstract stepping function
def step(state: AState) -> Iterable[AState | str]:
    pc = state.pc
    opr = bc[pc]
    logger.debug("")
    logger.debug(f"* STEP {pc}:")
    logger.debug(f"* - operation: {opr}")
    logger.debug(f"* - state: {state}")
    logger.debug("")
    
    match opr:
        case jvm.Get(field=f, static=s):
            # For abstract interpretation, we can just push a placeholder value
            new_frames = Stack([PerVarFrame(
                locals=dict(state.frames.peek().locals),
                stack=Stack(state.frames.peek().stack.items[:])
            )])
            new_frames.peek().stack.push(f"FIELD({f})")
            new_state = AState(frames=new_frames, pc=pc + 1)
            yield new_state
        case jvm.Ifz(condition=con, target=target):
            # Pop value from stack and branch based on condition
            frame = state.frames.peek()
            if not frame.stack:
                yield "ERROR: Empty stack on Ifz"
                return
            
            # Pop the value from the stack
            stack_copy = Stack(frame.stack.items[:-1])  # All but last item
            va1 = frame.stack.peek()
            
            # Create state after pop
            after_frame = PerVarFrame(
                locals=dict(frame.locals),
                stack=stack_copy
            )
            
            # For abstract interpretation, we need to consider both branches
            # Branch 1: condition is true (jump to target)
            true_frames = Stack([PerVarFrame(
                locals=dict(after_frame.locals),
                stack=Stack(after_frame.stack.items[:])
            )])
            true_state = AState(frames=true_frames, pc=PC(pc.method, target))
            yield true_state
            
            # Branch 2: condition is false (continue to next instruction)
            false_frames = Stack([PerVarFrame(
                locals=dict(after_frame.locals),
                stack=Stack(after_frame.stack.items[:])
            )])
            false_state = AState(frames=false_frames, pc=pc + 1)
            yield false_state
        case jvm.Return():
            # Return from method - final state
            yield "ok"
        case jvm.Load(type=typ, index=idx):
            # Load from local variable onto stack
            frame = state.frames.peek()
            if idx not in frame.locals:
                yield "ERROR: Local variable not found on Load"
                return
            val = frame.locals[idx]
            new_frames = Stack([PerVarFrame(
                locals=dict(frame.locals),
                stack=Stack(frame.stack.items[:])
            )])
            new_frames.peek().stack.push(val)
            new_state = AState(frames=new_frames, pc=pc + 1)
            yield new_state
        case jvm.Binary(type=typ, operator=op):
            # Binary operation (pop two values, push result)
            frame = state.frames.peek()
            if len(frame.stack.items) < 2:
                yield "ERROR: Not enough values on stack for binary operation"
                return
            val2 = frame.stack.items[-1]
            val1 = frame.stack.items[-2]
            # For now, just push a placeholder result
            new_frames = Stack([PerVarFrame(
                locals=dict(frame.locals),
                stack=Stack(frame.stack.items[:-2])
            )])
            new_frames.peek().stack.push(f"({val1} {op} {val2})")
            new_state = AState(frames=new_frames, pc=pc + 1)
            yield new_state
        case _:
            logger.warning(f"Unhandled opcode: {opr!r}")
            yield f"ERROR: Unhandled opcode {opr!r}"

def manystep(sts : StateSet) -> Iterable[AState | str]:
    for pc, state in sts.per_instruction():
        yield from step(state)

# perform abstract interpretation
MAX_STEPS = 100
final = set()
sts = AState.initialstate_from_method(methodid) # TODO: better naming - ´sts´ refer to set of states

for i in range(MAX_STEPS):
    if not sts.needswork:
        logger.info(f"Fixed point reached after {i} iterations")
        break
    
    for s in manystep(sts):
        if isinstance(s, str):
            final.add(s)
        else:
            sts |= s
else:
    logger.warning(f"Reached MAX_STEPS ({MAX_STEPS}) without convergence")

logger.info(f"The following final states {final} are possible")
logger.info(f"Total states explored: {len(sts.per_inst)}")