from hypothesis import given
from hypothesis.strategies import integers, sets

from interval_abstraction import Interval
from sign_abstraction import SignSet

## TODO: keep in mind: may or must?

@given(sets(integers()))
def test_valid_sign_abstraction(xs):
    s = SignSet.abstract(xs) 
    assert all(x in s for x in xs)

@given(sets(integers()), sets(integers()))
def test_sign_adds(xs, ys):
  assert (
    SignSet.abstract({x + y for x in xs for y in ys}) 
      <= SignSet.abstract(xs) + SignSet.abstract(ys)
    )

@given(sets(integers()))
def test_interval_abstraction_valid(xs):
    r = Interval.abstract(xs) 
    assert all(x in r for x in xs)

@given(sets(integers()), sets(integers()))
def test_interval_abstraction_distributes(xs, ys):
    assert (Interval.abstract(xs) | Interval.abstract(ys)) == Interval.abstract(xs | ys)
  
@given(sets(integers()), sets(integers()))
def test_interval_abstraction_add(xs,ys):
    r = Interval.abstract(xs) + Interval.abstract(ys)
    assert all(x + y in r for x in xs for y in ys)

# Running tests
print("Running Sign Abstraction tests...")
test_valid_sign_abstraction()
print("✓ Successfully validated sign abstraction.")
test_sign_adds()
print("✓ Successfully validated sign addition.")

print("Running Interval Abstraction tests...")
test_interval_abstraction_valid()
print("✓ Successfully validated interval abstraction.")
test_interval_abstraction_distributes()
print("✓ Successfully validated interval abstraction distribution.")
test_interval_abstraction_add()
print("✓ Successfully validated interval addition.")

print("All tests passed successfully!")