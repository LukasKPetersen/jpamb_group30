from collections.abc import Iterator
from itertools import product as _product

from jpamb import jvm

def _index_tuples_with_max_r(lengths, r):
    """
    All index-tuples (i0, ..., ik-1) such that:
      0 <= ij < lengths[j]  and  max(ij) == r
    """
    k = len(lengths)
    idx = [0] * k

    def backtrack(pos, has_r):
        if pos == k:
            if has_r:
                yield tuple(idx)
            return
        max_i = min(lengths[pos] - 1, r)
        if max_i < 0:
            return
        for v in range(max_i + 1):
            idx[pos] = v
            yield from backtrack(pos + 1, has_r or (v == r))

    yield from backtrack(0, False)


def _to_iter(source):
    # If it's already an iterator, keep it; otherwise call iter() on it
    return source if isinstance(source, Iterator) else iter(source)


def fair_product(*sources):
    """
    Lazily enumerate the (fair) Cartesian product of several
    iterables/generators, possibly infinite, possibly mixed types.

    Example:
        fair_product(ints(), bools())
        fair_product(ints(), strings_over(), bools())
    """
    iters = [_to_iter(s) for s in sources]
    pools = [[] for _ in iters]   # values we've pulled so far per dimension
    done  = [False] * len(iters)  # whether that dimension is exhausted

    r = 0                         # 'radius' in index-space
    first_yielded = False

    while True:
        # Ensure each non-exhausted dimension has at least r+1 elements, if possible
        for i, it in enumerate(iters):
            while not done[i] and len(pools[i]) <= r:
                try:
                    pools[i].append(next(it))
                except StopIteration:
                    done[i] = True
                    break

        lengths = [len(p) for p in pools]

        # If some dimension is empty *and* exhausted, the product is empty
        if not first_yielded and any(lengths[i] == 0 and done[i] for i in range(len(iters))):
            return

        any_yielded = False
        for idxs in _index_tuples_with_max_r(lengths, r):
            yield tuple(pools[i][idx] for i, idx in enumerate(idxs))
            first_yielded = True
            any_yielded = True

        # If no new tuples and everything is exhausted, we’re done
        if all(done) and not any_yielded:
            break

        r += 1



def ints():
    """All integers: 0, 1, -1, 2, -2, ..."""
    yield 0
    n = 1
    while True:
        yield n
        yield -n
        n += 1


def bools():
    """All booleans (finite)."""
    yield False
    yield True




def int_values():
    """All integers as jvm.Value: 0, 1, -1, 2, -2, ..."""
    yield jvm.Value.int(0)
    n = 1
    while True:
        yield jvm.Value.int(n)
        yield jvm.Value.int(-n)
        n += 1


def bool_values():
    """All booleans as jvm.Value."""
    yield jvm.Value.boolean(False)
    yield jvm.Value.boolean(True)


def int_array_values():
    """Generate int arrays of increasing sizes with fair value combinations."""
    # Empty array first
    yield jvm.Value.array(jvm.Int(), [])
    
    # Then arrays of increasing length with expanding values
    for length in range(1, 100):
        # Generate arrays with combinations of central-expanding ints
        for vals in fair_product(*[ints() for _ in range(length)]):
            yield jvm.Value.array(jvm.Int(), list(vals))


def char_array_values():
    """Generate char arrays of increasing sizes."""
    # Empty array first
    yield jvm.Value.array(jvm.Char(), [])
    
    # Common chars to use
    chars = [chr(i) for i in range(32, 127)]  # printable ASCII
    
    for length in range(1, 10):
        # Simple combinations of chars
        for combo in _product(chars[:10], repeat=length):  # limit to first 10 chars
            yield jvm.Value.array(jvm.Char(), list(combo))


def generators_for_method(method_signature):
    """Return a list of generators for each parameter type in the method signature."""
    generators = []
    for param in method_signature.extension.params:
        match param:
            case jvm.Int():
                generators.append(int_values())
            case jvm.Boolean():
                generators.append(bool_values())
            case jvm.Array(jvm.Int()):
                generators.append(int_array_values())
            case jvm.Array(jvm.Char()):
                generators.append(char_array_values())
            case _:
                raise NotImplementedError(f"Generator not implemented for type: {param}")
    return generators