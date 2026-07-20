import os
import sys

# Ensure backend directory is in sys.path so tests can import backend modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import pytest
import data_fetcher
import geo_classifier
import ai_analyzer
import threading

@pytest.fixture(autouse=True)
def _global_teardown():
    yield
    # Teardown logic runs after each test
    data_fetcher.clear_data_cache()
    geo_classifier.clear_crop_cache()
    
    with ai_analyzer._cb_lock:
        ai_analyzer._cb_failures = 0
        ai_analyzer._cb_open_until = 0.0

    for breaker in data_fetcher._breakers.values():
        breaker.record_success()
