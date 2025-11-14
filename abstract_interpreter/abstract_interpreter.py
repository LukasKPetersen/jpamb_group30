import jpamb
from jpamb import jvm
from dataclasses import dataclass
from typing import Iterable, TypeVar
import sign_abstraction

import sys
from loguru import logger
from typing import Dict, Set, Any

logger.remove()
logger.add(sys.stderr, format="[{level}] {message}")

methodid, input = jpamb.getcase()
print(f"This is the methodid: {methodid}\nThis is the input: {input}")

# for now: written by copilot
@dataclass
class aPC:
    """Mapping from program counters (PC) to sets of states (AState or str)."""
    mapping: Dict[Any, Set[Any]]

    @classmethod
    def empty(cls) -> "aPC":
        return cls({})

    def __getitem__(self, pc: Any) -> Set[Any]:
        return self.mapping.get(pc, set())

    def keys(self):
        return self.mapping.keys()

    def __le__(self, other: "aPC") -> bool:
        """
        Pointwise ordering: self <= other iff for every pc and every state s in self[pc]
        there exists a state t in other[pc] with s <= t (if s supports <=), or s == t
        for non-comparable values (e.g. strings).
        """
        for pc, states in self.mapping.items():
            other_states = other.mapping.get(pc, set())
            if not other_states:
                return False
            for s in states:
                if isinstance(s, str):
                    # compare error/terminal states by equality
                    if s not in other_states:
                        return False
                    continue

                # find some t in other_states such that s <= t
                found = False
                for t in other_states:
                    if isinstance(t, str):
                        continue
                    try:
                        if s <= t:
                            found = True
                            break
                    except Exception:
                        # fallback to equality if no __le__ implemented
                        if s == t:
                            found = True
                            break
                if not found:
                    return False
        return True

    def __and__(self, other: "aPC") -> "aPC":
        """
        Meet operator: pointwise union of state-sets (as specified).
        """
        keys = set(self.mapping.keys()) | set(other.mapping.keys())
        new_map: Dict[Any, Set[Any]] = {}
        for k in keys:
            new_map[k] = set(self.mapping.get(k, set())) | set(other.mapping.get(k, set()))
        return aPC(new_map)

    def __or__(self, other: "aPC") -> "aPC":
        """
        Join operator: pointwise intersection of state-sets (dual to meet above).
        """
        keys = set(self.mapping.keys()) & set(other.mapping.keys())
        new_map: Dict[Any, Set[Any]] = {}
        for k in keys:
            new_map[k] = set(self.mapping.get(k, set())) & set(other.mapping.get(k, set()))
        return aPC(new_map)

    # convenience aliases
    def meet(self, other: "aPC") -> "aPC":
        return self.__and__(other)

    def join(self, other: "aPC") -> "aPC":
        return self.__or__(other)

    def __str__(self) -> str:
        return "{" + ", ".join(f"{k}: {v}" for k, v in self.mapping.items()) + "}"


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
    
    # helper function for clearer use of the "join" operation
    def join(self, other: "PerVarFrame[AV]") -> "PerVarFrame[AV]":
        return self.__or__(other)

    def __str__(self):
        locals = ", ".join(f"{k}:{v}" for k, v in sorted(self.locals.items()))
        return f"<{{{locals}}}, {self.stack}>"


@dataclass
class AState:
    heap: dict[int, jvm.Value] # TODO: should this be in the abstract interpreter too?
    frames: Stack[PerVarFrame]

    def __str__(self):
        return f"{self.heap} {self.frames}"

# abstract stepping function
def step(state: AState) -> Iterable[AState | str]:
    assert isinstance(state, AState), f"expected frame but got {state}"
    frame = state.frames.peek()
    opr = bc[frame.pc]
    logger.debug(f"STEP {opr}\n{state}")
    match opr:
        case jvm.Ifz(condition=c, target=t):
            # TODO: implement abstract interpretation for Ifz
            pass
        case a:
            a.help()
            raise NotImplementedError(f"Don't know how to handle: {a!r}")

def many_step(state: dict[PC, AState | str]) -> dict[PC, AState | str]:
    new_state = dict()
    for k, v in state.items():
        for s in step(v):
            if s.pc in new_state:
                new_state[s.pc] = new_state[s.pc].join(s)
            else:
                new_state[s.pc] = s
    return new_state

frame = PerVarFrame.abstract(methodid)
state = AState({}, Stack.empty())

for i, v in enumerate(input.values):
    # We have to sort between types in the input and where we store them
    # Primitives can go directly into the locals array
    # Objects and arrays go into the heap

    if isinstance(v.type, (jvm.Array | jvm.Object)):
        heap_length = len(state.heap)
        # Create a reference of the object
        ref = jvm.Value(jvm.Reference(), heap_length)
        # insert value in heap and reference in locals
        state.heap[ref.value] = v
        frame.locals[i] = ref
    else:
        frame.locals[i] = v

state.frames.push(frame)

many_step({PC(methodid, 0): state})
