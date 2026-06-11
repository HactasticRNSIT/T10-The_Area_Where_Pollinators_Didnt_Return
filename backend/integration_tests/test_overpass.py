import pytest
from data_fetcher import fetch_water_proximity

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_overpass_water_proximity():
    """Test that the OSM Overpass API returns valid float scores in [0.0, 1.0] and not the 0.5 sentinel."""
    # Test near a known water body (e.g., near Hooghly river in Kolkata)
    lat, lon = 22.5726, 88.3639
    
    result = fetch_water_proximity(lat, lon, radius_m=1000)
    
    assert "water_proximity_score" in result
    score = result["water_proximity_score"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    assert score != 0.5, "Received the 0.5 sentinel fallback instead of real data"
    
    # Test a typically drier location (e.g., Jaipur)
    lat_dry, lon_dry = 26.9124, 75.7873
    result_dry = fetch_water_proximity(lat_dry, lon_dry, radius_m=500)
    
    assert "water_proximity_score" in result_dry
    score_dry = result_dry["water_proximity_score"]
    assert isinstance(score_dry, float)
    assert 0.0 <= score_dry <= 1.0
    assert score_dry != 0.5, "Received the 0.5 sentinel fallback instead of real data"
