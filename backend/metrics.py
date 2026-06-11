from prometheus_client import Counter, Gauge

polynexus_groq_calls = Counter(
    "polynexus_groq_calls_total",
    "Number of Groq LLM API calls made for pollination insights",
)
polynexus_groq_fallback = Counter(
    "polynexus_groq_fallback_total",
    "Number of times Groq API failed and fell back to rule-based insights",
)

polynexus_source_health = Gauge(
    "polynexus_source_health",
    "Health status of external data sources (1=live, 0=fallback)",
    ["source_name"]
)
