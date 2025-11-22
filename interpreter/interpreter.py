import jpamb
from jpamb import jvm
from dataclasses import dataclass

import sys
from loguru import logger

logger.remove()
logger.add(sys.stderr, format="[{level}] {message}")

# methodid, input = jpamb.getcase()
# print(f"This is the methodid: {methodid}\nThis is the input: {input}")

from dataclasses import dataclass
from typing import TypeAlias, Literal

Sign : TypeAlias = Literal["+"] | Literal["-"] | Literal["0"]

@dataclass
class SignSet:
    def __init__(self):
        self.signs : set[Sign] = set()

    def add(self, sign_set: set[Sign]):
        self |= sign_set

    def add(self, num: int):
        if (num > 0):
            self.signs.add(Literal["+"])
        elif (num < 0):
            self.signs.add(Literal["-"])
        else:
            self.signs.add(Literal["0"])

    def compare(self, other: "SignSet"):
        return self.signs.issubset(other.signs)

    # Meet operator (the largest element that is less than or equal to both self and other)
    def __and__(self, other: "SignSet"):
        return self.signs.intersection(other.signs)
    
    # Join operator (the smallest element that is greater than or equal to both self and other)
    def __or__(self, other: "SignSet"):
        return self.signs.union(other.signs)


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


@dataclass
class Frame:
    locals: dict[int, jvm.Value]
    stack: Stack[jvm.Value]
    pc: PC

    def __str__(self):
        locals = ", ".join(f"{k}:{v}" for k, v in sorted(self.locals.items()))
        return f"<{{{locals}}}, {self.stack}, {self.pc}>"

    def from_method(method: jvm.AbsMethodID) -> "Frame":
        return Frame({}, Stack.empty(), PC(method, 0))


@dataclass
class State:
    heap: dict[int, jvm.Value]
    frames: Stack[Frame]

    def __str__(self):
        return f"{self.heap} {self.frames}"


def step(state: State) -> State | str:
    assert isinstance(state, State), f"expected frame but got {state}"
    frame = state.frames.peek()
    opr = bc[frame.pc]
    logger.debug(f"STEP {opr}\n{state}")
    match opr:
        case jvm.Get(field=f, static=s):
            # We assume that the field only has one '.'
            s = str(f).split('.')
            assert len(s) == 2, "There is not 1 '.' in the field string, opr: get"
            if (s[1] == "$assertionsDisabled:Z"):
                # We always assume assertions are enabled
                frame.stack.push(jvm.Value(type=jvm.Int(), value=0))
                frame.pc += 1
                return state
            else:
                raise NotImplementedError(f"For jvm.Get in the stepping function. Do not know how to handle: {f}")
        case jvm.Goto(target=t):
            # An unconditional jump to offset = target
            frame.pc.set(t)
            return state
        case jvm.New(classname=c):
            if c._as_string == "java/lang/AssertionError":
                return "assertion error"
            else:
                raise NotImplementedError(f"jvm.New case not handled yet!")
        case jvm.Ifz(condition=c, target=t):
            v = frame.stack.pop()
            v_value = v.value

            if v.type is jvm.Boolean():
                v_value = 0 if v.value == False else 1
            assert type(v_value) is int, f"Expected int but got {v}"
            # jump or not?
            jump = False
            match c:
                case "eq" : jump = (v_value == 0)
                case "ne" : jump = (v_value != 0)
                case "lt" : jump = (v_value < 0)
                case "ge" : jump = (v_value >= 0)
                case "gt" : jump = (v_value > 0)
                case "le" : jump = (v_value <= 0)

            if jump:
                # Jump to target
                frame.pc.set(t)
            else:
                # Continue without jumping
                frame.pc += 1
            return state
        case jvm.If(condition=c, target=t):
            # Condition between two values

            value2 = frame.stack.pop().value
            value1 = frame.stack.pop()

            if value1.type == jvm.Char():
                # Convert characters into ascii number
                value1 = ord(value1.value)
            else:
                value1 = value1.value

            match c:
                case "eq" : jump = (value1 == value2)
                case "ne" : jump = (value1 != value2)
                case "lt" : jump = (value1 < value2)
                case "ge" : jump = (value1 >= value2)
                case "gt" : jump = (value1 > value2)
                case "le" : jump = (value1 <= value2)

            if jump:
                frame.pc.set(t)
            else:
                frame.pc += 1

            return state
        case jvm.ArrayLength():
            ref = frame.stack.pop()
            # The value must be of type reference
            assert ref.type == jvm.Reference(), f"The value is not of type reference but {ref.type}, jvm.ArrayLength"
            # Check for null pointer exception
            idx = ref.value
            if idx == None:
                return "null pointer"
            # Otherwise 
            arr = state.heap[idx]
            # Check that the array is indeed of type array
            assert isinstance(arr.type, jvm.Array), "The object in the heap is not of type array, opr: ArrayLength()"
            length = jvm.Value(jvm.Int(), len(arr.value))
            # Push back onto operand stack
            frame.stack.push(length)
            frame.pc += 1
            return state
        case jvm.New(classname=c):
            if str(c) == "java/lang/AssertionError":
                frame.pc += 1
                return state
            else:
                raise NotImplementedError(f"For jvm.Get in the stepping function. Do not know how to handle: {c}")
        case jvm.Dup(words=words):
            v = frame.stack.peek()
            frame.stack.push(v)
            frame.pc += 1
            return state
        case jvm.Push(value=v):
            frame.stack.push(v)
            frame.pc += 1
            return state
        case jvm.Store(type=jvm.Int(), index=idx):
            v = frame.stack.pop()
            # The value on top of the frame must be an integer
            assert v.type == jvm.Int(), f"Wrong type for istore. Found {v}"
            # Access locals and insert v at idx
            frame.locals[idx] = v
            frame.pc += 1
            return state
        case jvm.Store(type=jvm.Reference(), index=idx):
            # Store the reference of the object in locals
            # pop the reference to the object
            ref = frame.stack.pop()
            # asserting it is indeed a reference
            assert ref.type == jvm.Reference(), (
                "Store requires the popped stack object to be of type Reference or returnAddress"
            )
            # Store it in locals
            frame.locals[idx] = ref

            frame.pc += 1

            return state
        case jvm.ArrayStore(type=jvm.Int()):
            value = frame.stack.pop()
            index = frame.stack.pop()
            ref = frame.stack.pop()
            assert value.type == jvm.Int() and index.type == jvm.Int(), (
                "The value and the index must be integers for opr: iastore"
            )
            assert ref.type == jvm.Reference(), "reference object not of correct type, opr: iastore"
            # Check that the array is not null
            if ref.value == None:
                return "null pointer"
            # Check that the type of the array is of int
            assert state.heap[ref.value].type == jvm.Array(jvm.Int()), "The array has to hold values of type integers, opr: iastore"
            # Check out if bounds property is obstructed
            if len(state.heap[ref.value].value) <= index.value:
                return "out of bounds"
            # Insert the integer at index in the array
            state.heap[ref.value].value[index.value] = value.value
            frame.pc += 1
            return state
        case jvm.ArrayLength():
            arr_ref = frame.stack.pop()
            frame.pc += 1
            assert arr_ref.type == jvm.Reference(), "Problem"
            arr_len = jvm.Value(jvm.Int(), len(state.heap[arr_ref.value].value))
            frame.stack.push(arr_len)
            return state
        case jvm.ArrayLoad(type=t):
            idx = frame.stack.pop()
            ref = frame.stack.pop()
            assert ref.type == jvm.Reference(), f"reference has to be of type reference but is {ref.type}, opr: ArrayLoad"
            arr = state.heap[ref.value]
            assert isinstance(arr.type, jvm.Array), f"arr has to be of type array but is {arr.type}, opr: ArrayLoad"
            # Check for out of bounds
            if len(arr.value) <= idx.value:
                return "out of bounds"
            # Access the array (tuple) at index idx
            v = jvm.Value(t, arr.value[idx.value])
            frame.stack.push(v)
            frame.pc += 1
            return state
        case jvm.Load(type=(jvm.Int() | jvm.Reference()), index=i):
            frame.stack.push(frame.locals[i])
            frame.pc += 1
            return state
        case jvm.Binary(type=jvm.Int(), operant=jvm.BinaryOpr.Div):
            v2, v1 = frame.stack.pop(), frame.stack.pop()
            assert v1.type is jvm.Int(), f"expected int, but got {v1}"
            assert v2.type is jvm.Int(), f"expected int, but got {v2}"
            if v2.value == 0:
                return "divide by zero"
            
            frame.stack.push(jvm.Value.int(v1.value // v2.value))
            frame.pc += 1
            return state
        case jvm.Binary(type=jvm.Int(), operant=jvm.BinaryOpr.Sub):
            v2, v1 = frame.stack.pop(), frame.stack.pop()
            assert v1.type is jvm.Int(), f"expected int, but got {v1}"
            assert v2.type is jvm.Int(), f"expected int, but got {v2}"
            frame.stack.push(jvm.Value.int(v1.value - v2.value))
            frame.pc += 1
            return state
        case jvm.Binary(type=jvm.Int(), operant=jvm.BinaryOpr.Add):
            v2, v1 = frame.stack.pop(), frame.stack.pop()
            assert v1.type is jvm.Int(), f"expected int, but got {v1}"
            assert v2.type is jvm.Int(), f"expected int, but got {v2}"
            frame.stack.push(jvm.Value.int(v1.value + v2.value))
            frame.pc += 1
            return state
        case jvm.Binary(type=jvm.Int(), operant=jvm.BinaryOpr.Mul):
            v2, v1 = frame.stack.pop(), frame.stack.pop()
            assert v1.type is jvm.Int(), f"expected int, but got {v1}"
            assert v2.type is jvm.Int(), f"expected int, but got {v2}"
            frame.stack.push(jvm.Value.int(v1.value * v2.value))
            frame.pc += 1
            return state
        case jvm.Binary(type=jvm.Int(), operant=jvm.BinaryOpr.Rem):
            v2, v1 = frame.stack.pop(), frame.stack.pop()
            assert v1.type is jvm.Int(), f"expected int, but got {v1}"
            assert v2.type is jvm.Int(), f"expected int, but got {v2}"
            frame.stack.push(jvm.Value.int(v1.value % v2.value))
            frame.pc += 1
            return state
        case jvm.Cast(from_=f, to_=t):
            v = frame.stack.pop()
            # We do not check what value we go from
            match t:
                case jvm.Short():
                    # We do nothing here (i2s jvm command) 
                    # It converts an int to a short and then sign-extend it into an int again...
                    pass
                case _:
                    raise NotImplementedError("Case not implemented, opr: jvm.Cast()")
            frame.stack.push(v)
            frame.pc += 1
            return state
        case jvm.Incr(index=idx, amount=n):
            v = frame.locals[idx]
            assert v.type is jvm.Int(), f"expected int, but got {v}"
            frame.locals[idx] = jvm.Value.int(v.value + n)
            frame.pc += 1
            return state
        case jvm.Return(type=(jvm.Int() | jvm.Reference())):
            v1 = frame.stack.pop()
            state.frames.pop()
            if state.frames:
                frame = state.frames.peek()
                frame.stack.push(v1)
                frame.pc += 1
                return state
            else:
                return "ok"
        case jvm.Return(type=None): # None is equivalent for void
            # Pop the current frame
            state.frames.pop()
            if state.frames:
                # Increment program counter
                frame = state.frames.peek()
                frame.pc += 1
                return state
            else:
                return "ok"
        case jvm.NewArray(type=jvm.Int(), dim=dim):
            assert dim <= 1, "Cannot yet handle dimensions >1"
            size = frame.stack.pop()
            # TODO: Implement dimension handling dim > 1
            # We load the array with the default initial value, 0
            arr = jvm.Value(type=jvm.Array(jvm.Int()), value=[0]*size.value)
            ref = len(state.heap)
            state.heap[ref] = arr
            # Push reference to the stack
            frame.stack.push(jvm.Value(jvm.Reference(), ref))
            frame.pc += 1
            return state
        case jvm.InvokeSpecial(_, method_name, _):
            string_method = str(method_name)[:24]
            assert string_method == "java/lang/AssertionError", f"Only assertion errors are handled so far, not {string_method}"
            # We know that it will throw an assertion error if the following is encountered
            if str(method_name)[:24] == "java/lang/AssertionError":
                return "assertion error"

            return state
        case jvm.InvokeStatic(method=static_methodid):
            # invoke a static method
            # Create a new frame
            new_frame = Frame.from_method(static_methodid)
            # TODO: Not sure about the order of the inpus values
            # pop the arguments from the caller's stack and insert them into the new stack's locals arrays
            for i in range(len(static_methodid.methodid.params._elements)-1, -1, -1):
                v = frame.stack.pop()
                new_frame.locals[i] = v
            state.frames.push(new_frame)
            # Do not increment program counter (first increment after the callee method returns)
            return state
        case a:
            a.help()
            raise NotImplementedError(f"Don't know how to handle: {a!r}")


# frame = Frame.from_method(methodid)
# state = State({}, Stack.empty())

# for i, v in enumerate(input.values):
#     # We have to sort between types in the input and where we store them
#     # Primitives can go directly into the locals array
#     # Objects and arrays go into the heap

#     if isinstance(v.type, (jvm.Array | jvm.Object)):
#         heap_length = len(state.heap)
#         # Create a reference of the object
#         ref = jvm.Value(jvm.Reference(), heap_length)
#         # insert value in heap and reference in locals
#         state.heap[ref.value] = v
#         frame.locals[i] = ref
#     else:
#         frame.locals[i] = v

# state.frames.push(frame)

# for x in range(100000):
#     state = step(state)
#     if isinstance(state, str):
#         print(state)
#         break
# else:
#     print("*")
