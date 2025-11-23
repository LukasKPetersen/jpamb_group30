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
            locals={var_id: self.locals[var_id] and other.locals[var_id] for var_id in self.locals},
            stack=self.stack and other.stack
        )
    
    # join operator (for lattice functionality)
    def __or__(self, other: "PerVarFrame[AV]") -> "PerVarFrame[AV]":
        return PerVarFrame(
            locals={var_id: self.locals[var_id] or other.locals[var_id] for var_id in self.locals},
            stack=self.stack or other.stack
        )

    def __str__(self):
        locals = ", ".join(f"{k}:{v}" for k, v in sorted(self.locals.items()))
        return f"<{{{locals}}}, {self.stack}>"

@dataclass
class AState:
    frames: Stack[PerVarFrame]
    pc: PC

    def __or__(self, other: "AState") -> "AState":
        """Join operator for states - used when merging states at the same program point"""
        if self.pc != other.pc:
            raise ValueError("Cannot join states at different program points")
        
        return self  # TODO: needs proper implementation

    @classmethod
    def initialstate_from_method(cls, methodid: jvm.AbsMethodID, input_values: tuple = ()) -> "StateSet":
        # Initialize locals with input parameters
        initial_locals = {i: input_values[i] for i in range(len(input_values))}
        initial_frame = PerVarFrame(locals=initial_locals, stack=Stack.empty())
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
    
    match opr:
        case jvm.Get(field=f, static=s):
            # We assume that the field only has one '.'
            s = str(f).split('.')
            assert len(s) == 2, "There is not 1 '.' in the field string, opr: get"
            if (s[1] == "$assertionsDisabled:Z"):
                # We always assume assertions are enabled
                frame = state.frames.peek()
                new_stack = Stack(frame.stack.items + [jvm.Value(type=jvm.Int(), value=0)])
                new_frame = PerVarFrame(locals=frame.locals, stack=new_stack)
                new_frames = Stack(state.frames.items[:-1] + [new_frame])
                new_pc = pc + 1
                new_state = AState(frames=new_frames, pc=new_pc)
                yield new_state
            else:
                raise NotImplementedError(f"For jvm.Get in the stepping function. Do not know how to handle: {f}")
        case jvm.Goto(target=t):
            # An unconditional jump to offset = target
            # Create new state with updated PC
            new_pc = PC(pc.method, t)
            new_state = AState(frames=state.frames, pc=new_pc)
            yield new_state
        case jvm.New(classname=c):
            if c._as_string == "java/lang/AssertionError":
                yield "assertion error"
            else:
                raise NotImplementedError(f"jvm.New case not handled yet!")
        case jvm.Ifz(condition=c, target=t):
            # Conditional branch - explore BOTH paths for abstract interpretation
            frame = state.frames.peek()
            
            # Pop value from stack for both branches
            if not frame.stack.items:
                return
            v = frame.stack.items[-1]
            new_stack_items = frame.stack.items[:-1]
            
            # For abstract interpretation, we explore both branches
            # This ensures soundness - we don't miss any possible execution paths
            new_stack = Stack(new_stack_items)
            new_frame = PerVarFrame(locals=frame.locals.copy(), stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            
            # Always yield jump branch
            jump_pc = PC(pc.method, t)
            jump_state = AState(frames=new_frames, pc=jump_pc)
            yield jump_state
            
            # Always yield fall-through branch
            fall_pc = pc + 1
            fall_state = AState(frames=new_frames, pc=fall_pc)
            yield fall_state
        case jvm.If(condition=c, target=t):
            # Condition between two values - explore BOTH branches for abstract interpretation
            frame = state.frames.peek()
            
            if len(frame.stack.items) < 2:
                return
            
            value2_obj = frame.stack.items[-1]
            value1_obj = frame.stack.items[-2]
            new_stack_items = frame.stack.items[:-2]
            
            # For abstract interpretation, we explore both branches
            # This ensures soundness - we don't miss any possible execution paths
            new_stack = Stack(new_stack_items)
            new_frame = PerVarFrame(locals=frame.locals.copy(), stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            
            # Always yield jump branch
            jump_pc = PC(pc.method, t)
            jump_state = AState(frames=new_frames, pc=jump_pc)
            yield jump_state
            
            # Always yield fall-through branch
            fall_pc = pc + 1
            fall_state = AState(frames=new_frames, pc=fall_pc)
            yield fall_state
        case jvm.ArrayLength():
            # Note: ArrayLength appears twice in original code - this is the first occurrence
            # For abstract interpretation without heap, we'll skip this for now
            raise NotImplementedError("ArrayLength requires heap abstraction")
        case jvm.New(classname=c):
            if str(c) == "java/lang/AssertionError":
                # Just advance PC for AssertionError creation
                new_pc = pc + 1
                new_state = AState(frames=state.frames, pc=new_pc)
                yield new_state
            else:
                raise NotImplementedError(f"For jvm.New in the stepping function. Do not know how to handle: {c}")
        case jvm.Dup(words=words):
            frame = state.frames.peek()
            if not frame.stack.items:
                return
            v = frame.stack.items[-1]
            new_stack = Stack(frame.stack.items + [v])
            new_frame = PerVarFrame(locals=frame.locals, stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            new_pc = pc + 1
            new_state = AState(frames=new_frames, pc=new_pc)
            yield new_state
        case jvm.Push(value=v):
            frame = state.frames.peek()
            new_stack = Stack(frame.stack.items + [v])
            new_frame = PerVarFrame(locals=frame.locals, stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            new_pc = pc + 1
            new_state = AState(frames=new_frames, pc=new_pc)
            yield new_state
        case jvm.Store(type=jvm.Int(), index=idx):
            frame = state.frames.peek()
            if not frame.stack.items:
                return
            v = frame.stack.items[-1]
            assert v.type == jvm.Int(), f"Wrong type for istore. Found {v}"
            
            new_stack = Stack(frame.stack.items[:-1])
            new_locals = frame.locals.copy()
            new_locals[idx] = v
            new_frame = PerVarFrame(locals=new_locals, stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            new_pc = pc + 1
            new_state = AState(frames=new_frames, pc=new_pc)
            yield new_state
        case jvm.Store(type=jvm.Reference(), index=idx):
            frame = state.frames.peek()
            if not frame.stack.items:
                return
            ref = frame.stack.items[-1]
            assert ref.type == jvm.Reference(), (
                "Store requires the popped stack object to be of type Reference or returnAddress"
            )
            
            new_stack = Stack(frame.stack.items[:-1])
            new_locals = frame.locals.copy()
            new_locals[idx] = ref
            new_frame = PerVarFrame(locals=new_locals, stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            new_pc = pc + 1
            new_state = AState(frames=new_frames, pc=new_pc)
            yield new_state
        case jvm.ArrayStore(type=jvm.Int()):
            # ArrayStore requires heap abstraction
            raise NotImplementedError("ArrayStore requires heap abstraction")
        case jvm.ArrayLength():
            # Second ArrayLength - requires heap abstraction
            raise NotImplementedError("ArrayLength requires heap abstraction")
        case jvm.ArrayLoad(type=t):
            # ArrayLoad requires heap abstraction
            raise NotImplementedError("ArrayLoad requires heap abstraction")
        case jvm.Load(type=(jvm.Int() | jvm.Reference()), index=i):
            frame = state.frames.peek()
            if i not in frame.locals:
                return
            v = frame.locals[i]
            new_stack = Stack(frame.stack.items + [v])
            new_frame = PerVarFrame(locals=frame.locals, stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            new_pc = pc + 1
            new_state = AState(frames=new_frames, pc=new_pc)
            yield new_state
        case jvm.Binary(type=jvm.Int(), operant=jvm.BinaryOpr.Div):
            frame = state.frames.peek()
            if len(frame.stack.items) < 2:
                return
            v2 = frame.stack.items[-1]
            v1 = frame.stack.items[-2]
            assert v1.type is jvm.Int(), f"expected int, but got {v1}"
            assert v2.type is jvm.Int(), f"expected int, but got {v2}"
            
            # For abstract interpretation, explore both possibilities:
            # 1. Divisor could be zero -> divide by zero error
            yield "divide by zero"
            
            # 2. Divisor could be non-zero -> computation succeeds
            # Use concrete value if available, or abstract value otherwise
            result = jvm.Value.int(v1.value // v2.value if v2.value != 0 else 0)
            new_stack = Stack(frame.stack.items[:-2] + [result])
            new_frame = PerVarFrame(locals=frame.locals, stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            new_pc = pc + 1
            new_state = AState(frames=new_frames, pc=new_pc)
            yield new_state
        case jvm.Binary(type=jvm.Int(), operant=jvm.BinaryOpr.Sub):
            frame = state.frames.peek()
            if len(frame.stack.items) < 2:
                return
            v2 = frame.stack.items[-1]
            v1 = frame.stack.items[-2]
            assert v1.type is jvm.Int(), f"expected int, but got {v1}"
            assert v2.type is jvm.Int(), f"expected int, but got {v2}"
            result = jvm.Value.int(v1.value - v2.value)
            new_stack = Stack(frame.stack.items[:-2] + [result])
            new_frame = PerVarFrame(locals=frame.locals, stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            new_pc = pc + 1
            new_state = AState(frames=new_frames, pc=new_pc)
            yield new_state
        case jvm.Binary(type=jvm.Int(), operant=jvm.BinaryOpr.Add):
            frame = state.frames.peek()
            if len(frame.stack.items) < 2:
                return
            v2 = frame.stack.items[-1]
            v1 = frame.stack.items[-2]
            assert v1.type is jvm.Int(), f"expected int, but got {v1}"
            assert v2.type is jvm.Int(), f"expected int, but got {v2}"
            result = jvm.Value.int(v1.value + v2.value)
            new_stack = Stack(frame.stack.items[:-2] + [result])
            new_frame = PerVarFrame(locals=frame.locals, stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            new_pc = pc + 1
            new_state = AState(frames=new_frames, pc=new_pc)
            yield new_state
        case jvm.Binary(type=jvm.Int(), operant=jvm.BinaryOpr.Mul):
            frame = state.frames.peek()
            if len(frame.stack.items) < 2:
                return
            v2 = frame.stack.items[-1]
            v1 = frame.stack.items[-2]
            assert v1.type is jvm.Int(), f"expected int, but got {v1}"
            assert v2.type is jvm.Int(), f"expected int, but got {v2}"
            result = jvm.Value.int(v1.value * v2.value)
            new_stack = Stack(frame.stack.items[:-2] + [result])
            new_frame = PerVarFrame(locals=frame.locals, stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            new_pc = pc + 1
            new_state = AState(frames=new_frames, pc=new_pc)
            yield new_state
        case jvm.Binary(type=jvm.Int(), operant=jvm.BinaryOpr.Rem):
            frame = state.frames.peek()
            if len(frame.stack.items) < 2:
                return
            v2 = frame.stack.items[-1]
            v1 = frame.stack.items[-2]
            assert v1.type is jvm.Int(), f"expected int, but got {v1}"
            assert v2.type is jvm.Int(), f"expected int, but got {v2}"
            result = jvm.Value.int(v1.value % v2.value)
            new_stack = Stack(frame.stack.items[:-2] + [result])
            new_frame = PerVarFrame(locals=frame.locals, stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            new_pc = pc + 1
            new_state = AState(frames=new_frames, pc=new_pc)
            yield new_state
        case jvm.Cast(from_=f, to_=t):
            frame = state.frames.peek()
            if not frame.stack.items:
                return
            v = frame.stack.items[-1]
            match t:
                case jvm.Short():
                    # i2s - convert int to short and sign-extend back to int
                    pass
                case _:
                    raise NotImplementedError("Case not implemented, opr: jvm.Cast()")
            # Stack unchanged for i2s
            new_pc = pc + 1
            new_state = AState(frames=state.frames, pc=new_pc)
            yield new_state
        case jvm.Incr(index=idx, amount=n):
            frame = state.frames.peek()
            if idx not in frame.locals:
                return
            v = frame.locals[idx]
            assert v.type is jvm.Int(), f"expected int, but got {v}"
            new_locals = frame.locals.copy()
            new_locals[idx] = jvm.Value.int(v.value + n)
            new_frame = PerVarFrame(locals=new_locals, stack=frame.stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            new_pc = pc + 1
            new_state = AState(frames=new_frames, pc=new_pc)
            yield new_state
        case jvm.Return(type=(jvm.Int() | jvm.Reference())):
            frame = state.frames.peek()
            if not frame.stack.items:
                return
            v1 = frame.stack.items[-1]
            
            # Pop current frame
            if len(state.frames.items) <= 1:
                # Returning from main method
                yield "ok"
            else:
                # Return to caller
                caller_frame = state.frames.items[-2]
                new_caller_stack = Stack(caller_frame.stack.items + [v1])
                new_caller_frame = PerVarFrame(locals=caller_frame.locals, stack=new_caller_stack)
                new_frames = Stack(state.frames.items[:-2] + [new_caller_frame])
                # PC should already be set correctly (incremented when call was made)
                new_state = AState(frames=new_frames, pc=state.pc)
                yield new_state
        case jvm.Return(type=None): # None is equivalent for void
            # Pop the current frame
            if len(state.frames.items) <= 1:
                # Returning from main method
                yield "ok"
            else:
                # Return to caller
                new_frames = Stack(state.frames.items[:-1])
                # PC should already be set correctly
                new_state = AState(frames=new_frames, pc=state.pc)
                yield new_state
        case jvm.NewArray(type=jvm.Int(), dim=dim):
            # NewArray requires heap abstraction
            raise NotImplementedError("NewArray requires heap abstraction")
        case jvm.InvokeSpecial(_, method_name, _):
            string_method = str(method_name)[:24]
            assert string_method == "java/lang/AssertionError", f"Only assertion errors are handled so far, not {string_method}"
            if str(method_name)[:24] == "java/lang/AssertionError":
                yield "assertion error"
        case jvm.InvokeStatic(method=static_methodid):
            # invoke a static method
            frame = state.frames.peek()
            num_params = len(static_methodid.methodid.params._elements)
            
            if len(frame.stack.items) < num_params:
                return
            
            # Pop arguments from caller's stack
            args = frame.stack.items[-num_params:]
            new_caller_stack = Stack(frame.stack.items[:-num_params])
            new_caller_frame = PerVarFrame(locals=frame.locals, stack=new_caller_stack)
            
            # Create new frame for callee with arguments in locals
            new_callee_locals = {i: args[i] for i in range(num_params)}
            new_callee_frame = PerVarFrame(locals=new_callee_locals, stack=Stack.empty())
            
            # Push new frame onto frame stack
            new_frames = Stack(state.frames.items[:-1] + [new_caller_frame, new_callee_frame])
            
            # Set PC to start of called method
            new_pc = PC(static_methodid, 0)
            new_state = AState(frames=new_frames, pc=new_pc)
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
sts = AState.initialstate_from_method(methodid, input.values) # TODO: better naming - ´sts´ refer to set of states

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