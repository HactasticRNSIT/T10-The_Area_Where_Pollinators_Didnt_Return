import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def make_session() -> requests.Session:
    """
    Create and configure a new requests.Session with robust retry logic.
    Using a factory prevents connection pool state and headers from being
    unintentionally shared across different modules (e.g. data_fetcher and geo_classifier).
    """
    session = requests.Session()
    adapter = HTTPAdapter(
        max_retries=Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        )
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
