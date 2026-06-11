# PolyNexus: Pollinator Ecosystem Intelligence — Walkthrough & Feature Guide

PolyNexus is a real-time pollinator health dashboard and decision-support system designed to monitor, assess, and actively increase pollinator activity and crop fertilisation across agricultural zones in India. By integrating agricultural registry data, remote sensing, and real-time environmental metrics, PolyNexus bridges the gap between scientific ecological data and field-level farming decisions.

This walkthrough outlines all the core features, algorithms, and modules that make up the PolyNexus website and backend.

---

## 🗺️ Product Overview: What PolyNexus Does

Pollinators (like honeybees and solitary bees) are responsible for the fertilization of over 70% of high-value crops (e.g., apples, mustard, mangoes, coffee, and cardamom). When ecosystems suffer from pesticide pressure, monoculture, soil degradation, and climate volatility, pollinator populations drop, leading to **pollination deficits** and severe yield loss.

PolyNexus works by:
1. **Ingesting live environmental factors** (from climate, soil, satellite imagery, and species observations).
2. **Computing a multi-factor stress profile** customized to specific crops and regional agro-climatic zones.
3. **Detecting ecological anomalies** (such as spraying during active flowering windows).
4. **Providing economic valuations** of agricultural yield at risk.
5. **Generating actionable advisory plans and managed hive placements** (using rule-based heuristics and generative AI via Groq) to actively boost pollination and crop fertility.

---

## 🎨 Interactive Front-End Dashboard Features

The PolyNexus frontend is a premium, high-fidelity dashboard built with **React, TypeScript, and Vite**, featuring smooth transitions, micro-animations, and a responsive layout styled using modern HSL colors and glassmorphism.

```
+-----------------------------------------------------------------------------+
|  [PX] PolyNexus   [ Search Indian regions... ]                 API Online   |
+-----------------------------------------------------------------------------+
|  +------------------------+  +------------------------+  +---------------+  |
|  |  Ecosystem Activity    |  |   ECOLOGICAL STRESS    |  |  CROP RISK    |  |
|  |  84%   (Medium Data)   |  |  32%   Compound Stress |  |  ₹45,000      |  |
|  +------------------------+  +------------------------+  +---------------+  |
|  +------------------------+  +------------------------+  +---------------+  |
|  |   Phenology Calendar   |  |   Interventions        |  |  Advisory     |  |
|  |   [   Flowering  ]     |  |   Simulator Sandbox    |  |  AI Chatbot   |  |
|  +------------------------+  +------------------------+  +---------------+  |
+-----------------------------------------------------------------------------+
```

### 1. Unified Glassmorphism UI & Floating Ambience
- **Floating Ambient Orbs**: Dynamic background layers with organic CSS/Framer-Motion animations that glide subtly, giving the dashboard an alive and premium aesthetic.
- **Ambient Hexagon Grid Overlay**: A custom SV-patterned vector background styled to reference honeycomb structures, reacting softly to viewport resizing.
- **Metric Micro-Animations**: Counter widgets utilize spring-based interpolation (`framer-motion`'s `useSpring`) to roll numbers smoothly up to their value on load.

### 2. Location Autocomplete & Geocoding Search
- Integrated with the **OpenStreetMap Nominatim API**.
- Users can type any Indian village, city, district, or state. The search dropdown triggers a debounced query (400ms delay to limit API burden) returning matches within India.
- Selecting a result extracts the exact latitude and longitude, resolving the regional state boundaries to load local crop registries.

### 3. Multi-Zone Comparison & Benchmarking
- **Sticky Comparison Bar**: Triggers when a user checks the "Compare" box on multiple zones (up to 5) in the sidebar.
- ** benchmarking Matrix**: Compares zones side-by-side on Activity Score, Resilience Score, Overall Stress, Primary Risk Drivers, and Data Confidence.
- **Parallel Fetching**: Runs asynchronous calls concurrently to compute scores for all compared zones without locking up the user interface.

### 4. Interactive Interventions Simulator
- A sandbox environment allowing farmers to simulate the impact of ecosystem restoration steps.
- **Available Scenarios**:
  - *IPM Spray Timing*: Switching to evening/morning spraying to avoid active foraging hours.
  - *Flowering Border Strips*: Planting border strips (e.g., marigold, sesame) to enhance floral resources.
  - *Soil Recovery*: Compost and moisture conservation.
  - *Nesting Refugia*: No-till zones protecting ground-nesting solitary bees.
  - *Drought Buffers*: Irrigation and microclimate water sources.
- **Real-Time Projections**: Instantly visualizes the projected ecosystem activity gain, overall stress drop, and factor-by-factor improvement percentages before implementing them in the field.

### 5. Managed Hive Placement Calculator
- For high-dependency crops (pollinator dependency $\ge 60\%$), the app renders custom advice including:
  - Recommended bee species (e.g., *Apis cerana* for high-humidity spice coast, *Apis mellifera* for commercial orchards).
  - Colony density (hives per hectare).
  - Spacing constraints (maximum foraging radius in meters).
  - Optimal release timing relative to phenology.
- **Interactive Sizer**: A slider/input where farmers input their farm size in hectares, and the system automatically rounds up to compute the total number of managed bee colonies needed.

### 6. Dynamic Phenology Crop Calendar
- Displays a visual crop flowering timeline for the current zone.
- Displays a **Today Marker** line relative to the calendar month grid.
- Highlights **Critical Windows** (the flowering period plus a safety buffer of days prior, where chemical pesticide spraying is highly hazardous).

### 7. Farmer Field Observations & Photographic Logging
- A sidebar widget for citizen-science observations where farmers record:
  - Observed pollinator counts and specific species sightings.
  - Custom field notes.
  - **Photo Uploads**: A file input to upload field photographs (which are saved securely in zone-specific subdirectories on the backend).
- **Live Overrides**: Uploaded pollinator counts feed directly into the SQLite database. When the zone is re-analyzed, the system detects these observations and upgrades the visitation quality metric from "modelled" to "live", overriding synthetic proxy scoring.

### 8. Historical Trends & Seasonal baselines
- **12-Week Sparklines**: Sourced from SQLite run-history to draw bezier-smoothed SV-sparklines showing whether ecosystem activity is improving, declining, or stable.
- **Seasonal Baseline Shading**: Shows the typical activity range for the current calendar month based on past years.
- **Baseline Alerts**: Fades in a warning banner if the current activity score drops below the typical seasonal range (e.g. "Activity dropped by 8 points compared to seasonal baseline").

### 9. Farmer Report Export (Print & HTML)
- Generates a lightweight, clean, printer-friendly **Farmer Report** in a popup window or as a downloadable file.
- Contains overall scores, a custom checklist of the top 3 steps to boost fertility, risk drivers, and crop exposures.
- Styled to exclude dashboard menus, keeping print layout margins clean.

### 10. AI Chatbot Sidebar Widget
- An inline chatbot interface allowing farmers to ask general questions about agronomy and pollinator-safe farming practices.
- Connects directly to the backend chat handler, which provides targeted guidelines on soil conservation, tillage, pesticides, and floral resources.

---

## ⚙️ Robust Back-End Core Architecture

The backend is built with **Python 3.10+ and FastAPI**, structured as an analytical data pipeline.

### 1. The 5-Factor Scoring Model (`scorer.py`)
Ecosystems are evaluated out of 100 based on five weighted factors, incorporating state-specific overrides:

| Factor | Primary Sub-Signals | Scoring Formula type |
| :--- | :--- | :--- |
| **Pesticide Exposure** | Runoff concentration (ppm), spray frequency, days since application. | **Sigmoid** (centered at 10ppm) + **Linear** application rates. |
| **Soil Fertility** | pH, soil organic carbon (SOC), Nitrogen, compaction index, root-zone wetness. | **Double Sigmoid** (optimum 6.5 pH) + **Gaussian Bell-Curve** (soil moisture). |
| **Floral Diversity** | Satellite-derived greenness (NDVI / EVI indices). | **Linear** baseline relative to regional averages. |
| **Climate Volatility** | High-temp anomalies, rainfall variance, extreme wind flight boundaries. | **Bell-Curve** deviation metrics. |
| **Nesting Availability** | Proximity to forests, waterbodies, and uncultivated land. | **Linear** proximity indicators from OSM Overpass queries. |

- **Microbial Soil Activity Proxy**: Soil fertility also estimates microbial health by combining organic carbon levels, temperature, and moisture into a combined biological stress factor.
- **Compound Stress Penalty**: If multiple stress factors cross their warning thresholds simultaneously, the scoring engine adds an *interaction penalty* (up to $15\%$ extra stress), acknowledging that compound stressors are exponentially harder for bee populations to recover from.

### 2. Dual-Layer Anomaly & Action Engine
When data is analyzed, it runs through two distinct diagnostic layers:
- **Layer 1: Rule-Based Diagnostics (`anomaly_detector.py`)**:
  - Compares raw variables against a set of regional thresholds.
  - Automatically **translates recommended actions** from temperate-zone suggestions to localized Indian practices (e.g., swapping *"phacelia/buckwheat"* with *"dhaincha/cowpea"*, or *"blackthorn"* with *"Moringa/karanj"*).
  - Triggers **Phenology Escalation**: If a pesticide anomaly is detected during a crop's active flowering window, the anomaly is automatically upgraded to `CRITICAL` severity, altering the activity score.
- **Layer 2: Generative AI Insights (`ai_analyzer.py`)**:
  - If any critical or warning anomalies are flagged, the system invokes the **Groq API (using Llama 3)**.
  - Powered by a prompt written from the persona of a senior agricultural ecologist, it returns structured, action-oriented advisory text focused on *increasing crop fertility and yield* rather than just warning of threats.

### 3. Database Layer (`history_store.py` & `intervention_store.py`)
- Uses **SQLite** configured in **WAL (Write-Ahead Logging) mode**, ensuring rapid, concurrent, non-blocking read and write transactions.
- Automatically initializes and manages lightweight schema migrations idempotently on module import.
- Keeps track of logged intervention outcomes by linking the timestamp of a completed action to the zone's activity score before and after implementation.

### 4. Circuit Breakers & Request Decoupling
- To guarantee dashboard responsiveness even if external databases (such as SoilGrids, NASA POWER, or GBIF) experience latency or downtime, the data-fetching layer is wrapped in **thread-safe Circuit Breakers**.
- If a service fails 3 times, the breaker trips for 60 seconds, immediately serving cached profiles or fallback values.
- Downstream endpoints utilize a shared `requests.Session` factory (`network.py`) to avoid connection state leakage.

### 5. Security & Operations
- **SlowAPI Rate Limiting**: Protects high-cost endpoints like `/analyse` and `/compare` with IP-based limits. It securely parses proxy-aware headers (`X-Forwarded-For` / `X-Real-IP`) verified against an optional trusted CIDR network parameter.
- **FastAPI Lifespan Validation**: Checks for crucial credentials (like `GROQ_API_KEY`) at server startup and alerts DevOps in logs if there are configuration issues.
- **Prometheus Metrics**: Exposes metrics (like `/metrics`) tracking CPU load, request latency, and Groq API fallback ratios.

---

## 🛠️ Verification & Testing Suite

PolyNexus maintains high reliability via an automated testing pipeline:
1. **Property-Based Testing (`test_scorer_properties.py`)**: Uses `hypothesis` to feed extreme float inputs into the scoring formulas, proving mathematically that scores always stay within logical bounds `[0.0, 100.0]`.
2. **Snapshot Testing (`test_backend.py`)**: Uses `syrupy` to verify API JSON outputs against reference snapshots, preventing regression changes in output keys.
3. **Integration Mocking**: Auto-cleanup fixtures ensure that test suites do not pollute global caches or trip API circuit breakers between consecutive runs.
