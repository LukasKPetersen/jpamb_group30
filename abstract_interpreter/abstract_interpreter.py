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
    """Wraps an interval with a JVM type for abstract interpretation"""
    type: jvm.Type
    interval: Interval
    
    @classmethod
    def from_concrete(cls, value: jvm.Value) -> "AbstractValue":
        """Convert concrete JVM value to abstract value with interval"""
        if isinstance(value.type, jvm.Int):
            return cls(type=jvm.Int(), interval=Interval(value.value, value.value))
        else:
            # For non-int types, return with empty interval (not tracked)
            return cls(type=value.type, interval=Interval.empty())
    
    @classmethod
    def int_interval(cls, interval: Interval) -> "AbstractValue":
        """Create an abstract int value from an interval"""
        return cls(type=jvm.Int(), interval=interval)
    
    @classmethod
    def top_int(cls) -> "AbstractValue":
        """Create top element ([-inf, inf]) for integers"""
        import sys
        return cls(type=jvm.Int(), interval=Interval(-sys.maxsize, sys.maxsize))
    
    def __le__(self, other: "AbstractValue") -> bool:
        """Ordering for lattice"""
        if not isinstance(other, AbstractValue):
            return False
        return self.interval <= other.interval
    
    def __or__(self, other: "AbstractValue") -> "AbstractValue":
        """Join operator"""
        if not isinstance(other, AbstractValue):
            return self
        return AbstractValue(type=self.type, interval=self.interval | other.interval)
    
    def __and__(self, other: "AbstractValue") -> "AbstractValue":
        """Meet operator"""
        if not isinstance(other, AbstractValue):
            return self
        return AbstractValue(type=self.type, interval=self.interval & other.interval)
    
    def __str__(self) -> str:
        return f"{self.type}:{self.interval}"

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
        # Join locals: take union of keys and join values
        all_vars = set(self.locals.keys()) | set(other.locals.keys())
        joined_locals = {}
        for var_id in all_vars:
            if var_id in self.locals and var_id in other.locals:
                joined_locals[var_id] = self.locals[var_id] | other.locals[var_id]
            elif var_id in self.locals:
                joined_locals[var_id] = self.locals[var_id]
            else:
                joined_locals[var_id] = other.locals[var_id]
        
        # Join stacks: they should have same length at merge points
        if len(self.stack.items) != len(other.stack.items):
            # If stacks differ in length, use the shorter one (conservative)
            min_len = min(len(self.stack.items), len(other.stack.items))
            joined_stack = Stack([self.stack.items[i] | other.stack.items[i] for i in range(min_len)])
        else:
            joined_stack = Stack([self.stack.items[i] | other.stack.items[i] for i in range(len(self.stack.items))])
        
        return PerVarFrame(locals=joined_locals, stack=joined_stack)

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
        
        # Join frames stacks
        if len(self.frames.items) != len(other.frames.items):
            # Conservative: take minimum frame depth
            min_depth = min(len(self.frames.items), len(other.frames.items))
            joined_frames = Stack([self.frames.items[i] | other.frames.items[i] for i in range(min_depth)])
        else:
            joined_frames = Stack([self.frames.items[i] | other.frames.items[i] for i in range(len(self.frames.items))])
        
        return AState(frames=joined_frames, pc=self.pc)

    @classmethod
    def initialstate_from_method(cls, methodid: jvm.AbsMethodID, input_values: tuple = ()) -> "StateSet":
        # Initialize locals with input parameters as abstract values with intervals
        initial_locals = {i: AbstractValue.from_concrete(input_values[i]) for i in range(len(input_values))}
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
                # We always assume assertions are enabled (push 0)
                frame = state.frames.peek()
                abs_val = AbstractValue.int_interval(Interval(0, 0))
                new_stack = Stack(frame.stack.items + [abs_val])
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
            # Conditional branch - use interval analysis for feasibility
            frame = state.frames.peek()
            
            if not frame.stack.items:
                return
            v = frame.stack.items[-1]
            new_stack_items = frame.stack.items[:-1]
            
            # Analyze which branches are feasible based on the interval
            if not isinstance(v, AbstractValue) or not isinstance(v.type, jvm.Int):
                # Conservative: explore both branches
                can_be_true = True
                can_be_false = True
            else:
                interval = v.interval
                # Check condition against zero
                if c == "eq":  # value == 0
                    can_be_true = 0 in interval
                    can_be_false = interval.lower != 0 or interval.upper != 0
                elif c == "ne":  # value != 0
                    can_be_true = interval.lower != 0 or interval.upper != 0
                    can_be_false = 0 in interval
                elif c == "lt":  # value < 0
                    can_be_true = interval.lower < 0
                    can_be_false = interval.upper >= 0
                elif c == "ge":  # value >= 0
                    can_be_true = interval.upper >= 0
                    can_be_false = interval.lower < 0
                elif c == "gt":  # value > 0
                    can_be_true = interval.upper > 0
                    can_be_false = interval.lower <= 0
                elif c == "le":  # value <= 0
                    can_be_true = interval.lower <= 0
                    can_be_false = interval.upper > 0
                else:
                    can_be_true = True
                    can_be_false = True
            
            new_stack = Stack(new_stack_items)
            new_frame = PerVarFrame(locals=frame.locals.copy(), stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            
            # Only yield feasible branches
            if can_be_true:
                jump_pc = PC(pc.method, t)
                jump_state = AState(frames=new_frames, pc=jump_pc)
                yield jump_state
            
            if can_be_false:
                fall_pc = pc + 1
                fall_state = AState(frames=new_frames, pc=fall_pc)
                yield fall_state
        case jvm.If(condition=c, target=t):
            # Condition between two values - use interval analysis
            frame = state.frames.peek()
            
            if len(frame.stack.items) < 2:
                return
            
            value2_obj = frame.stack.items[-1]
            value1_obj = frame.stack.items[-2]
            new_stack_items = frame.stack.items[:-2]
            
            # Analyze which branches are feasible
            if (not isinstance(value1_obj, AbstractValue) or not isinstance(value1_obj.type, jvm.Int) or
                not isinstance(value2_obj, AbstractValue) or not isinstance(value2_obj.type, jvm.Int)):
                can_be_true = True
                can_be_false = True
            else:
                i1 = value1_obj.interval
                i2 = value2_obj.interval
                
                # Check feasibility based on condition
                if c == "eq":  # v1 == v2
                    overlap = i1 & i2
                    can_be_true = not overlap.is_empty
                    can_be_false = not (i1.lower == i1.upper == i2.lower == i2.upper)
                elif c == "ne":  # v1 != v2
                    can_be_true = not (i1.lower == i1.upper == i2.lower == i2.upper)
                    can_be_false = not (i1 & i2).is_empty
                elif c == "lt":  # v1 < v2
                    can_be_true = i1.lower < i2.upper
                    can_be_false = i1.upper >= i2.lower
                elif c == "ge":  # v1 >= v2
                    can_be_true = i1.upper >= i2.lower
                    can_be_false = i1.lower < i2.upper
                elif c == "gt":  # v1 > v2
                    can_be_true = i1.upper > i2.lower
                    can_be_false = i1.lower <= i2.upper
                elif c == "le":  # v1 <= v2
                    can_be_true = i1.lower <= i2.upper
                    can_be_false = i1.upper > i2.lower
                else:
                    can_be_true = True
                    can_be_false = True
            
            new_stack = Stack(new_stack_items)
            new_frame = PerVarFrame(locals=frame.locals.copy(), stack=new_stack)
            new_frames = Stack(state.frames.items[:-1] + [new_frame])
            
            # Only yield feasible branches
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
            
            # Check if divisor interval contains zero
            if 0 in v2.interval:
                yield "divide by zero"
            
            # If divisor can be non-zero, perform division
            if v2.interval.lower != 0 or v2.interval.upper != 0:
                # Conservative interval for division (hard to compute precisely)
                # Use top element for non-trivial intervals
                if v2.interval.lower == v2.interval.upper and v2.interval.lower != 0:
                    # Exact divisor known
                    divisor = v2.interval.lower
                    result_interval = Interval(v1.interval.lower // divisor, v1.interval.upper // divisor)
                else:
                    # Conservative: use top element
                    import sys
                    result_interval = Interval(-sys.maxsize, sys.maxsize)
                
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
            else:
                result_interval = Interval.empty()
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
                # Conservative: remainder is in range [-(abs(divisor)-1), abs(divisor)-1]
                max_abs_divisor = max(abs(v2.interval.lower), abs(v2.interval.upper))
                result_interval = Interval(-max_abs_divisor + 1, max_abs_divisor - 1)
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
logger.info("Final abstract values at each program point:")
for pc in sorted(sts.per_inst.keys(), key=lambda p: (str(p.method), p.offset)):
    state = sts.per_inst[pc]
    if state.frames.items:
        frame = state.frames.items[-1]
        locals_str = ", ".join(f"v{k}={v.interval}" for k, v in sorted(frame.locals.items()) if isinstance(v, AbstractValue))
        stack_str = ", ".join(f"{v.interval}" for v in frame.stack.items if isinstance(v, AbstractValue))
        logger.info(f"  {pc}: locals=[{locals_str}] stack=[{stack_str}]")