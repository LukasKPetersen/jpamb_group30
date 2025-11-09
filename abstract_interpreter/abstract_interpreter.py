from hypothesis import given
from hypothesis.strategies import integers, sets

from sign_abstraction import SignSet, Arithmetic

## TODO: keep in mind: may or must?

@given(sets(integers()))
def test_valid_sign_abstraction(xs):
    s = SignSet.abstract(xs) 
    assert all(x in s for x in xs)

@given(sets(integers()), sets(integers()))
def test_sign_adds(xs, ys):
    a = SignSet.abstract({x + y for x in xs for y in ys})
    a_xs = SignSet.abstract(xs)
    a_ys = SignSet.abstract(ys)
    assert (
        a.is_subset_of(Arithmetic.add_signsets(a_xs, a_ys))
    )

@given(sets(integers()), sets(integers()))
def test_sign_le(xs, ys):
    a_xs = SignSet.abstract(xs)
    a_ys = SignSet.abstract(ys)
    assert (
        Arithmetic.compare_signsets("le", a_xs, a_ys)
    )

## TODO: implement interval abstraction
# @given(sets(integers()))
# def test_interval_abstraction_valid(xs):
#     r = Interval.abstract(xs) 
#     assert all(x in r for x in xs)

# @given(sets(integers()), sets(integers()))
# def test_interval_abstraction_distributes(xs, ys):
#     assert (Interval.abstract(xs) | Interval.abstract(ys)) == Interval.abstract(xs | ys)