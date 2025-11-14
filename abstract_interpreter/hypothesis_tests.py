from hypothesis import given
from hypothesis.strategies import integers, sets

from sign_abstraction import Comparison, SignSet, Arithmetic

## TODO: keep in mind: may or must?

@given(sets(integers()))
def test_valid_sign_abstraction(xs):
    s = SignSet.abstract(xs) 
    assert all(x in s for x in xs)

@given(sets(integers()), sets(integers()))
def test_sign_adds(xs, ys):
  assert (
    SignSet.abstract({x + y for x in xs for y in ys}) 
      <= Arithmetic.add_signsets(SignSet.abstract(xs), SignSet.abstract(ys))
    )

## TODO: implement interval abstraction
# @given(sets(integers()))
# def test_interval_abstraction_valid(xs):
#     r = Interval.abstract(xs) 
#     assert all(x in r for x in xs)

# @given(sets(integers()), sets(integers()))
# def test_interval_abstraction_distributes(xs, ys):
#     assert (Interval.abstract(xs) | Interval.abstract(ys)) == Interval.abstract(xs | ys)

test_valid_sign_abstraction()
print("✓ Successfully validated sign abstraction.")
test_sign_adds()
print("✓ Successfully validated sign addition.")
