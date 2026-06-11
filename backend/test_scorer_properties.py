import pytest
from hypothesis import given, strategies as st
import math

# We can import the math functions from pesticide_data or where they are defined, 
# but let's test the general properties of the math used in the application.
# If they are in a specific file, we can import them. Let's assume they are in math_utils or similar, 
# or just test the inline implementations if they are in scorer or pesticide_data.
from pesticide_data import compute_pesticide_proxy
# For now, let's write property tests for invariants that should hold for the pesticide proxy
# since it uses a sigmoid/bell-curve logic.

@given(
    intensity=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    flowering=st.booleans(),
    wind=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    rain=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_compute_pesticide_proxy_bounds(intensity, flowering, wind, rain):
    result = compute_pesticide_proxy(intensity, flowering, wind, rain)
    assert 0.0 <= result["risk_score"] <= 1.0

@given(
    intensity1=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    intensity2=st.floats(min_value=50.1, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_compute_pesticide_proxy_monotonicity(intensity1, intensity2):
    # Higher intensity should result in higher or equal risk
    r1 = compute_pesticide_proxy(intensity1, False, 0.0, 0.0)["risk_score"]
    r2 = compute_pesticide_proxy(intensity2, False, 0.0, 0.0)["risk_score"]
    assert r2 >= r1

