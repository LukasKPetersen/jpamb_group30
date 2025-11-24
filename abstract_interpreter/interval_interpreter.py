import jpamb
from jpamb import jvm
from dataclasses import dataclass
from typing import Iterable, TypeVar
import sign_abstraction
from interval_abstraction import Interval, Arithmetic

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

@dataclass(frozen=True)
class AbstractValue:
    """Wrapper for abstract values using interval abstraction"""
    type: jvm.Type
    interval: Interval
    
    @classmethod
    def from_concrete(cls, value: jvm.Value) -> "AbstractValue":
        """Create abstract value from concrete jvm.Value"""
        if isinstance(value.type, jvm.Int):
            int_val = int(value.value) if isinstance(value.value, int) else 0
            return cls(type=jvm.Int(), interval=Interval(int_val, int_val))
        else:
            # For non-int types (like Reference), we don't abstract
            return cls(type=value.type, interval=Interval.empty())
    
    @classmethod
    def int_interval(cls, interval: Interval) -> "AbstractValue":
        """Create abstract integer value from interval"""
        return cls(type=jvm.Int(), interval=interval)
    
    def __str__(self):
        if isinstance(self.type, jvm.Int):
            return f"Int{self.interval}"
        return f"{self.type}"

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
        
        # Join frames - for now, we only handle single frame case
        if len(self.frames.items) != len(other.frames.items):
            # Can't join states with different frame depths
            return self
        
        joined_frames = []
        for f1, f2 in zip(self.frames.items, other.frames.items):
            # Join locals
            all_keys = set(f1.locals.keys()) | set(f2.locals.keys())
            joined_locals = {}
            for key in all_keys:
                if key in f1.locals and key in f2.locals:
                    v1 = f1.locals[key]
                    v2 = f2.locals[key]
                    if isinstance(v1, AbstractValue) and isinstance(v2, AbstractValue):
                        joined_locals[key] = AbstractValue.int_interval(v1.interval | v2.interval)
                    else:
                        joined_locals[key] = v1  # fallback
                elif key in f1.locals:
                    joined_locals[key] = f1.locals[key]
                else:
                    joined_locals[key] = f2.locals[key]
            
            # Join stacks - must have same length
            joined_stack_items = []
            if len(f1.stack.items) == len(f2.stack.items):
                for s1, s2 in zip(f1.stack.items, f2.stack.items):
                    if isinstance(s1, AbstractValue) and isinstance(s2, AbstractValue):
                        joined_stack_items.append(AbstractValue.int_interval(s1.interval | s2.interval))
                    else:
                        joined_stack_items.append(s1)
            else:
                # Stacks don't match - use first one as fallback
                joined_stack_items = f1.stack.items
            
            joined_frames.append(PerVarFrame(locals=joined_locals, stack=Stack(joined_stack_items)))
        
        return AState(frames=Stack(joined_frames), pc=self.pc)

    @classmethod
    def initialstate_from_method(cls, methodid: jvm.AbsMethodID, input_values: tuple = ()) -> "StateSet":
        # Initialize locals with input parameters as abstract values
        initial_locals = {}
        for i, val in enumerate(input_values):
            if isinstance(val, jvm.Value):
                initial_locals[i] = AbstractValue.from_concrete(val)
            else:
                initial_locals[i] = val
        
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
    
    # Debug: Show current frame state with intervals
    if state.frames.items:
        frame = state.frames.peek()
        logger.debug(f"* - locals: {', '.join(f'{k}={v}' for k, v in frame.locals.items())}")
        logger.debug(f"* - stack: [{', '.join(str(v) for v in frame.stack.items)}]")
    
    match opr:
        case jvm.Get(field=f, static=s):
            # We assume that the field only has one '.'
            s = str(f).split('.')
            assert len(s) == 2, "There is not 1 '.' in the field string, opr: get"
            if (s[1] == "$assertionsDisabled:Z"):
                # We always assume assertions are enabled
                frame = state.frames.peek()
                zero_val = AbstractValue.int_interval(Interval(0, 0))
                new_stack = Stack(frame.stack.items + [zero_val])
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
            # Conditional branch - use interval analysis for precise exploration
            frame = state.frames.peek()
            
            # Pop value from stack for both branches
            if not frame.stack.items:
                return
            v = frame.stack.items[-1]
            new_stack_items = frame.stack.items[:-1]
            
            # Analyze which branches are feasible based on the interval
            if not isinstance(v, AbstractValue) or not isinstance(v.type, jvm.Int):
                # Fallback to exploring both branches
                new_stack = Stack(new_stack_items)
                new_frame = PerVarFrame(locals=frame.locals.copy(), stack=new_stack)
                new_frames = Stack(state.frames.items[:-1] + [new_frame])
                jump_pc = PC(pc.method, t)
                yield AState(frames=new_frames, pc=jump_pc)
                fall_pc = pc + 1
                yield AState(frames=new_frames, pc=fall_pc)
                return
            
            interval = v.interval
            
            logger.debug(f"  -> Ifz condition '{c}' on interval {interval}")
            # Check which branches are feasible based on condition
            # Condition types: eq, ne, lt, ge, gt, le (compared to zero)
            if c == "eq":  # == 0
                can_be_true = 0 in interval
                can_be_false = interval.lower < 0 or interval.upper > 0
            elif c == "ne":  # != 0
                can_be_true = interval.lower < 0 or interval.upper > 0
                can_be_false = 0 in interval
            elif c == "lt":  # < 0
                can_be_true = interval.lower < 0
                can_be_false = interval.upper >= 0
            elif c == "ge":  # >= 0
                can_be_true = interval.upper >= 0
                can_be_false = interval.lower < 0
            elif c == "gt":  # > 0
                can_be_true = interval.upper > 0
                can_be_false = interval.lower <= 0
            elif c == "le":  # <= 0
                can_be_true = interval.lower <= 0
                can_be_false = interval.upper > 0
            else:
                # Unknown condition, be conservative
                can_be_true = True
                can_be_false = True
            
            new_stack = Stack(new_stack_items)
            new_frame = PerVarFrame(locals=frame.locals.copy(), stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            
            logger.debug(f"  -> Branch analysis: can_be_true={can_be_true}, can_be_false={can_be_false}")
            # Only yield branches that are feasible
            if can_be_true:
                jump_pc = PC(pc.method, t)
                jump_state = AState(frames=new_frames, pc=jump_pc)
                yield jump_state
            
            if can_be_false:
                fall_pc = pc + 1
                fall_state = AState(frames=new_frames, pc=fall_pc)
                yield fall_state
        case jvm.If(condition=c, target=t):
            # Condition between two values - use interval analysis for precise exploration
            frame = state.frames.peek()
            
            if len(frame.stack.items) < 2:
                return
            
            value2_obj = frame.stack.items[-1]
            value1_obj = frame.stack.items[-2]
            new_stack_items = frame.stack.items[:-2]
            
            # Analyze which branches are feasible based on intervals
            if (not isinstance(value1_obj, AbstractValue) or not isinstance(value1_obj.type, jvm.Int) or
                not isinstance(value2_obj, AbstractValue) or not isinstance(value2_obj.type, jvm.Int)):
                # Fallback to exploring both branches
                new_stack = Stack(new_stack_items)
                new_frame = PerVarFrame(locals=frame.locals.copy(), stack=new_stack)
                new_frames = Stack(state.frames.items[:-1] + [new_frame])
                jump_pc = PC(pc.method, t)
                yield AState(frames=new_frames, pc=jump_pc)
                fall_pc = pc + 1
                yield AState(frames=new_frames, pc=fall_pc)
                return
            
            i1 = value1_obj.interval
            i2 = value2_obj.interval
            
            logger.debug(f"  -> If condition '{c}': {i1} cmp {i2}")
            # Check which branches are feasible based on condition
            # Condition types: eq, ne, lt, ge, gt, le (value1 cond value2)
            if c == "eq":  # value1 == value2
                # Intervals overlap?
                overlap = not (i1 & i2).is_empty
                can_be_true = overlap
                can_be_false = i1.lower < i2.lower or i1.upper > i2.upper or i2.lower < i1.lower or i2.upper > i1.upper
            elif c == "ne":  # value1 != value2
                can_be_true = i1.lower != i2.upper or i1.upper != i2.lower or i1.lower != i2.lower or i1.upper != i2.upper
                can_be_false = not (i1 & i2).is_empty
            elif c == "lt":  # value1 < value2
                can_be_true = i1.lower < i2.upper
                can_be_false = i1.upper >= i2.lower
            elif c == "ge":  # value1 >= value2
                can_be_true = i1.upper >= i2.lower
                can_be_false = i1.lower < i2.upper
            elif c == "gt":  # value1 > value2
                can_be_true = i1.upper > i2.lower
                can_be_false = i1.lower <= i2.upper
            elif c == "le":  # value1 <= value2
                can_be_true = i1.lower <= i2.upper
                can_be_false = i1.upper > i2.lower
            else:
                # Unknown condition, be conservative
                can_be_true = True
                can_be_false = True
            
            new_stack = Stack(new_stack_items)
            new_frame = PerVarFrame(locals=frame.locals.copy(), stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            
            logger.debug(f"  -> Branch analysis: can_be_true={can_be_true}, can_be_false={can_be_false}")
            # Only yield branches that are feasible
            if can_be_true:
                jump_pc = PC(pc.method, t)
                jump_state = AState(frames=new_frames, pc=jump_pc)
                yield jump_state
            
            if can_be_false:
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
            abs_val = AbstractValue.from_concrete(v)
            logger.debug(f"  -> Pushing interval: {abs_val}")
            new_stack = Stack(frame.stack.items + [abs_val])
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
            assert isinstance(v.type, jvm.Int), f"Wrong type for istore. Found {v}"
            
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
            assert isinstance(ref.type, jvm.Reference), (
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
            assert isinstance(v1.type, jvm.Int), f"expected int, but got {v1}"
            assert isinstance(v2.type, jvm.Int), f"expected int, but got {v2}"
            
            logger.debug(f"  -> Div: {v1.interval} / {v2.interval}")
            # Check if divisor interval contains zero
            if 0 in v2.interval:
                logger.debug(f"  -> Divisor can be zero, yielding divide by zero error")
                yield "divide by zero"
            
            # If divisor can be non-zero, perform division
            if v2.interval.lower != 0 or v2.interval.upper != 0:
                # For interval division, we need to handle all combinations
                # Simplified: assume divisor is non-zero
                if not v1.interval.is_empty and not v2.interval.is_empty:
                    results = set()
                    for a in [v1.interval.lower, v1.interval.upper]:
                        for b in [v2.interval.lower, v2.interval.upper]:
                            if b != 0:
                                results.add(a // b)
                    if results:
                        result_interval = Interval(min(results), max(results))
                        result = AbstractValue.int_interval(result_interval)
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
            assert isinstance(v1.type, jvm.Int), f"expected int, but got {v1}"
            assert isinstance(v2.type, jvm.Int), f"expected int, but got {v2}"
            result_interval = Arithmetic.sub(v1.interval, v2.interval)
            logger.debug(f"  -> Sub: {v1.interval} - {v2.interval} = {result_interval}")
            result = AbstractValue.int_interval(result_interval)
            result = AbstractValue.int_interval(result_interval)
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
            assert isinstance(v1.type, jvm.Int), f"expected int, but got {v1}"
            assert isinstance(v2.type, jvm.Int), f"expected int, but got {v2}"
            result_interval = Arithmetic.add(v1.interval, v2.interval)
            logger.debug(f"  -> Add: {v1.interval} + {v2.interval} = {result_interval}")
            result = AbstractValue.int_interval(result_interval)
            result = AbstractValue.int_interval(result_interval)
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
            assert isinstance(v1.type, jvm.Int), f"expected int, but got {v1}"
            assert isinstance(v2.type, jvm.Int), f"expected int, but got {v2}"
            # For multiplication, compute all corner products
            if not v1.interval.is_empty and not v2.interval.is_empty:
                products = [
                    v1.interval.lower * v2.interval.lower,
                    v1.interval.lower * v2.interval.upper,
                    v1.interval.upper * v2.interval.lower,
                    v1.interval.upper * v2.interval.upper
                ]
                result_interval = Interval(min(products), max(products))
                logger.debug(f"  -> Mul: {v1.interval} * {v2.interval} = {result_interval}")
            else:
                result_interval = Interval.empty()
                logger.debug(f"  -> Mul: {v1.interval} * {v2.interval} = ∅")
            result = AbstractValue.int_interval(result_interval)
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
            assert isinstance(v1.type, jvm.Int), f"expected int, but got {v1}"
            assert isinstance(v2.type, jvm.Int), f"expected int, but got {v2}"
            # For remainder, result is bounded by divisor
            if not v1.interval.is_empty and not v2.interval.is_empty:
                # Remainder is in range [-(|divisor|-1), |divisor|-1]
                max_div = max(abs(v2.interval.lower), abs(v2.interval.upper))
                if max_div > 0:
                    result_interval = Interval(-(max_div - 1), max_div - 1)
                else:
                    result_interval = Interval(0, 0)
            else:
                result_interval = Interval.empty()
            result = AbstractValue.int_interval(result_interval)
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
            assert isinstance(v.type, jvm.Int), f"expected int, but got {v}"
            new_locals = frame.locals.copy()
            n_interval = Interval(n, n)
            result_interval = Arithmetic.add(v.interval, n_interval)
            new_locals[idx] = AbstractValue.int_interval(result_interval)
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

# Output final intervals at each program point
logger.info("")
logger.info("Final intervals at each program point:")
for pc in sorted(sts.per_inst.keys(), key=lambda p: (str(p.method), p.offset)):
    state = sts.per_inst[pc]
    if state.frames.items:
        frame = state.frames.peek()
        locals_str = ', '.join(f'{k}={v}' for k, v in sorted(frame.locals.items()))
        stack_str = ', '.join(str(v) for v in frame.stack.items)
        logger.info(f"  {pc}:")
        if locals_str:
            logger.info(f"    locals: {{{locals_str}}}")
        if stack_str:
            logger.info(f"    stack: [{stack_str}]")
        else:
            logger.info(f"    stack: []")