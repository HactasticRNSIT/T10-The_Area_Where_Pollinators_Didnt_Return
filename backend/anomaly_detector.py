

from typing import Any

from config import ANOMALY_THRESHOLDS as T


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _anomaly(
    factor: str,
    variable: str,
    severity: str,
    observed: float,
    threshold: float,
    description: str,
    action: str,
) -> dict[str, Any]:
    return {
        "factor":             factor,
        "variable":           variable,
        "severity":           severity,
        "observed_value":     round(observed, 3),
        "threshold":          threshold,
        "description":        description,
        "recommended_action": action,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Factor-specific checkers
# ──────────────────────────────────────────────────────────────────────────────

def _check_pesticide(pesticide: dict[str, Any]) -> list[dict]:
    anomalies = []
    ppm   = pesticide.get("usage_ppm", 0)
    freq  = pesticide.get("applications_per_month", 0)
    days  = pesticide.get("days_since_last_application", 30)
    ptype = pesticide.get("pesticide_type", "unknown")

    # ppm concentration
    if ppm >= T["pesticide_ppm_critical"]:
        anomalies.append(_anomaly(
            "pesticide_exposure", "usage_ppm", "CRITICAL",
            ppm, T["pesticide_ppm_critical"],
            f"Pesticide concentration of {ppm:.1f} ppm is critically high and likely lethal to bees on contact.",
            f"Immediately suspend all {ptype} applications; switch to a Bee Hazard Class II-rated alternative "
            f"and allow a minimum 21-day clearance period before next application.",
        ))
    elif ppm >= T["pesticide_ppm_warning"]:
        anomalies.append(_anomaly(
            "pesticide_exposure", "usage_ppm", "WARNING",
            ppm, T["pesticide_ppm_warning"],
            f"Pesticide concentration of {ppm:.1f} ppm exceeds the safe pollinator threshold of "
            f"{T['pesticide_ppm_warning']} ppm.",
            f"Reduce {ptype} dosage by 40% and apply only after sunset (18:00–22:00) when bees are inactive.",
        ))

    # Application frequency
    if freq >= T["pesticide_freq_critical"]:
        anomalies.append(_anomaly(
            "pesticide_exposure", "applications_per_month", "CRITICAL",
            freq, T["pesticide_freq_critical"],
            f"{freq} applications per month far exceeds safe practice and creates chronic sub-lethal exposure "
            f"that impairs bee navigation and queen fertility.",
            "Adopt an Integrated Pest Management (IPM) protocol limiting applications to ≤2 per month "
            "and introduce biological controls (e.g. lacewings, parasitic wasps) as a buffer.",
        ))
    elif freq >= T["pesticide_freq_warning"]:
        anomalies.append(_anomaly(
            "pesticide_exposure", "applications_per_month", "WARNING",
            freq, T["pesticide_freq_warning"],
            f"{freq} applications per month is above the recommended maximum of {T['pesticide_freq_warning']}.",
            "Extend inter-application intervals to at least 14 days; consider introducing a flowering cover "
            "crop strip to attract beneficial insects and reduce pest pressure naturally.",
        ))

    # Recency (days since last spray)
    if days <= 3 and ppm >= T["pesticide_ppm_warning"]:
        anomalies.append(_anomaly(
            "pesticide_exposure", "days_since_last_application", "WARNING",
            days, 3,
            f"Pesticides were applied only {days} day(s) ago with residue still at {ppm:.1f} ppm – "
            f"peak acute toxicity window for foraging bees.",
            "Post warning signs at field boundaries; notify neighboring beekeepers within 2 km "
            "and avoid any mechanical soil disturbance until 7 days post-application.",
        ))

    # Type-specific alert
    if ptype == "neonicotinoid" and ppm > 2.0:
        anomalies.append(_anomaly(
            "pesticide_exposure", "pesticide_type", "WARNING",
            ppm, 2.0,
            f"Neonicotinoids are systemic and persist in soil and pollen for 200–1,000+ days. "
            f"Current use at {ppm:.1f} ppm poses long-term hive health risk.",
            "Replace neonicotinoid treatments with pyrethrin-based or kaolin clay sprays; "
            "plant phacelia or borage buffer strips to dilute pollen toxin concentration.",
        ))

    return anomalies


def _check_soil(
    soil: dict[str, Any],
    nasa: dict[str, Any],
) -> list[dict]:
    anomalies = []
    ph         = soil.get("ph", 6.5)
    soc        = soil.get("organic_carbon_g_per_kg", 1.8)
    nitrogen   = soil.get("nitrogen_g_per_kg", 1.2)
    moisture   = nasa.get("root_zone_wetness", 0.45)

    # pH
    if ph <= T["ph_critical_low"] or ph >= T["ph_critical_high"]:
        sev = "CRITICAL"
        action = (
            f"Apply 2–3 t/ha of agricultural lime to raise pH toward 6.5"
            if ph < 6.5 else
            f"Apply elemental sulphur at 200 kg/ha and re-test pH in 6 weeks."
        )
        anomalies.append(_anomaly(
            "soil_fertility", "ph", sev, ph,
            T["ph_critical_low"] if ph < 6.5 else T["ph_critical_high"],
            f"Soil pH of {ph:.2f} is at a critical level; most soluble nutrients become unavailable "
            f"and flowering plant diversity collapses below pH 5.0 or above pH 8.0.",
            action,
        ))
    elif ph <= T["ph_low_warning"] or ph >= T["ph_high_warning"]:
        action = (
            "Apply 1 t/ha ground limestone and incorporate with shallow tillage."
            if ph < 6.5 else
            "Incorporate 150 kg/ha sulphur powder or acidifying fertiliser such as ammonium sulphate."
        )
        anomalies.append(_anomaly(
            "soil_fertility", "ph", "WARNING", ph,
            T["ph_low_warning"] if ph < 6.5 else T["ph_high_warning"],
            f"Soil pH of {ph:.2f} is outside the optimal range for pollinator-supporting wildflowers (6.0–7.0).",
            action,
        ))

    # Organic carbon
    if soc <= T["organic_carbon_critical"]:
        anomalies.append(_anomaly(
            "soil_fertility", "organic_carbon_g_per_kg", "CRITICAL",
            soc, T["organic_carbon_critical"],
            f"Organic carbon of {soc:.2f} g/kg is critically depleted; soil food web and moisture "
            f"retention have collapsed, making plant establishment for pollinators extremely difficult.",
            "Apply 5 t/ha of well-rotted farmyard manure or biochar immediately; "
            "plant a mixed legume-grass cover crop and leave undisturbed for 18 months.",
        ))
    elif soc <= T["organic_carbon_low_warning"]:
        anomalies.append(_anomaly(
            "soil_fertility", "organic_carbon_g_per_kg", "WARNING",
            soc, T["organic_carbon_low_warning"],
            f"Organic carbon of {soc:.2f} g/kg is below the 1.5 g/kg threshold for productive soils.",
            "Incorporate green manure crops (mustard, phacelia) at their flowering stage; "
            "reduce tillage depth by 30% to preserve existing organic matter.",
        ))

    # Nitrogen
    if nitrogen <= T["nitrogen_critical"]:
        anomalies.append(_anomaly(
            "soil_fertility", "nitrogen_g_per_kg", "CRITICAL",
            nitrogen, T["nitrogen_critical"],
            f"Soil nitrogen of {nitrogen:.2f} g/kg is critically low; flowering plants cannot sustain "
            f"nectar production, directly reducing bee foraging reward.",
            "Establish a nitrogen-fixing cover crop mix (clover + vetch) across 20% of bare field margins "
            "and apply 30 kg/ha slow-release organic nitrogen fertiliser.",
        ))
    elif nitrogen <= T["nitrogen_low_warning"]:
        anomalies.append(_anomaly(
            "soil_fertility", "nitrogen_g_per_kg", "WARNING",
            nitrogen, T["nitrogen_low_warning"],
            f"Nitrogen at {nitrogen:.2f} g/kg is below the 1.0 g/kg threshold for supporting nectar-rich crops.",
            "Sow red clover or lucerne as under-sown crops in spring; "
            "target 25 kg/ha of organic nitrogen input before flowering season.",
        ))

    # Soil moisture
    if moisture < 0.15:
        anomalies.append(_anomaly(
            "soil_fertility", "root_zone_wetness", "CRITICAL",
            moisture, 0.15,
            f"Root-zone soil moisture fraction of {moisture:.2f} indicates severe drought stress; "
            f"wildflowers and forage plants will wilt and cease flowering.",
            "Activate drip irrigation at field margins at 3–4 mm/day until wetness exceeds 0.35; "
            "install moisture retention swales perpendicular to slope.",
        ))
    elif moisture < 0.25:
        anomalies.append(_anomaly(
            "soil_fertility", "root_zone_wetness", "WARNING",
            moisture, 0.25,
            f"Root-zone moisture of {moisture:.2f} is in the drought-stress zone for most flowering forbs.",
            "Apply mulch (straw or wood chip, 5 cm depth) to field-margin plantings "
            "to reduce evaporation and maintain moisture above 0.30.",
        ))

    return anomalies


def _check_climate(climate: dict[str, Any]) -> list[dict]:
    anomalies = []
    temp_std     = climate.get("temp_std_c", 4.0)
    total_precip = climate.get("total_precipitation_mm", 48.0)
    drought_idx  = climate.get("drought_index", 0.35)

    # Temperature variance
    if temp_std >= T["temp_variance_critical"]:
        anomalies.append(_anomaly(
            "climate_variability", "temp_std_c", "CRITICAL",
            temp_std, T["temp_variance_critical"],
            f"Temperature swings of ±{temp_std:.1f}°C (SD) over 30 days disrupt bee thermoregulation "
            f"and cause mass die-off of pupae when hives cannot maintain 34–36°C brood temperature.",
            "Identify south-facing hedgerow corridors as thermal refugia; contact local beekeepers "
            "to relocate hives to sheltered positions (tree lines, barn sides) during extreme swing events.",
        ))
    elif temp_std >= T["temp_variance_warning"]:
        anomalies.append(_anomaly(
            "climate_variability", "temp_std_c", "WARNING",
            temp_std, T["temp_variance_warning"],
            f"Temperature variability (SD {temp_std:.1f}°C) is above the warning threshold of "
            f"{T['temp_variance_warning']}°C – bees reduce foraging when daily swings exceed 8°C.",
            "Plant a 3–5 m wide mixed shrub belt on the north-west boundary to buffer wind-chill; "
            "provide supplementary syrup feed to affected colonies during cold snaps below 10°C.",
        ))

    # Rainfall deficit
    precip_deficit = 30.0 - total_precip
    if precip_deficit >= T["rainfall_deficit_critical"]:
        anomalies.append(_anomaly(
            "climate_variability", "total_precipitation_mm", "CRITICAL",
            total_precip, T["rainfall_deficit_critical"],
            f"Only {total_precip:.1f} mm of rainfall in 30 days – a deficit of {precip_deficit:.1f} mm "
            f"from the minimum threshold; nectar secretion in most flowers drops by >70% under this drought.",
            "Install supplementary water stations (shallow dishes with pebbles) at 50 m intervals "
            "across the zone; apply emergency irrigation to wildflower margin strips at 5 mm/day.",
        ))
    elif precip_deficit >= T["rainfall_deficit_warning"]:
        anomalies.append(_anomaly(
            "climate_variability", "total_precipitation_mm", "WARNING",
            total_precip, T["rainfall_deficit_warning"],
            f"Rainfall of {total_precip:.1f} mm over 30 days is {precip_deficit:.1f} mm below "
            f"the recommended minimum – expect reduced nectar concentration.",
            "Check field-margin flowering plant health weekly; prepare drip-irrigation lines "
            "for wildflower strips and activate if the 7-day forecast shows less than 10 mm.",
        ))

    # Drought index
    if drought_idx >= T["drought_index_critical"]:
        anomalies.append(_anomaly(
            "climate_variability", "drought_index", "CRITICAL",
            drought_idx, T["drought_index_critical"],
            f"Drought index of {drought_idx:.2f} (scale 0–1) indicates severe moisture deficit; "
            f"evapotranspiration is drastically exceeding rainfall over the past 30 days.",
            "Activate all available irrigation systems on pollinator habitat areas; "
            "report drought conditions to the regional agricultural extension office for emergency support.",
        ))
    elif drought_idx >= T["drought_index_warning"]:
        anomalies.append(_anomaly(
            "climate_variability", "drought_index", "WARNING",
            drought_idx, T["drought_index_warning"],
            f"Drought index of {drought_idx:.2f} shows moisture demand outpacing supply – "
            f"flowering duration will shorten and nectar sugar content will drop.",
            "Prioritise supplemental water for high-value pollinator plants (borage, phacelia, clover); "
            "delay mowing of grass margins to preserve moisture-retaining biomass.",
        ))

    return anomalies


def _check_floral(
    ndvi: dict[str, Any],
    gbif: dict[str, Any],
) -> list[dict]:
    anomalies = []
    ndvi_val      = ndvi.get("ndvi", 0.50)
    species_count = gbif.get("species_count", 5)

    # NDVI
    if ndvi_val <= T["ndvi_low_critical"]:
        anomalies.append(_anomaly(
            "floral_diversity", "ndvi", "CRITICAL",
            ndvi_val, T["ndvi_low_critical"],
            f"NDVI of {ndvi_val:.3f} indicates near-bare or dead vegetation cover. "
            f"Virtually no floral resources remain in the zone.",
            "Urgently establish a fast-germinating wildflower seed mix (phacelia, buckwheat, "
            "crimson clover) on all margins; cover at least 5% of zone area within 4 weeks.",
        ))
    elif ndvi_val <= T["ndvi_low_warning"]:
        anomalies.append(_anomaly(
            "floral_diversity", "ndvi", "WARNING",
            ndvi_val, T["ndvi_low_warning"],
            f"NDVI of {ndvi_val:.3f} signals sparse vegetation. Floral forage is likely insufficient "
            f"to sustain productive pollinator colonies.",
            "Oversow 2–3 m wide wildflower strips along all field boundaries using a "
            "regional native wildflower mix; target ≥3 species flowering simultaneously.",
        ))

    # Species richness
    if species_count <= T["species_count_critical"]:
        anomalies.append(_anomaly(
            "floral_diversity", "species_count", "CRITICAL",
            species_count, T["species_count_critical"],
            f"Only {species_count} pollinator species observed within {10} km – catastrophic biodiversity "
            f"collapse. Local extinctions may be underway.",
            "Contact county wildlife trust to establish a habitat corridor plan; "
            "immediately cease mowing all field margins and ditch banks for 12 months to allow recovery.",
        ))
    elif species_count <= T["species_count_warning"]:
        anomalies.append(_anomaly(
            "floral_diversity", "species_count", "WARNING",
            species_count, T["species_count_warning"],
            f"Only {species_count} pollinator species recorded near the zone – well below the target "
            f"of ≥10 species for resilient ecosystem function.",
            "Install 5+ bee hotels (mixed apertures 2–10 mm) along south-facing hedgerows; "
            "plant native pollen-rich shrubs (hawthorn, blackthorn, dog rose) at field corners.",
        ))

    return anomalies


def _check_nesting(ndvi: dict[str, Any]) -> list[dict]:
    anomalies = []
    bare_soil   = ndvi.get("bare_soil_fraction", 0.25)
    disturbance = ndvi.get("disturbance_score", 0.35)

    # Bare soil excess
    if bare_soil >= T["bare_soil_critical"]:
        anomalies.append(_anomaly(
            "nesting_availability", "bare_soil_fraction", "CRITICAL",
            bare_soil, T["bare_soil_critical"],
            f"{bare_soil*100:.0f}% bare soil across the zone creates extreme exposure to temperature "
            f"extremes, destroying ground-nesting bee egg chambers.",
            "Establish a permanent non-mowed grass-forb cover over at least 30% of bare areas; "
            "use a native grass-flower mix and exclude livestock from nesting zones for 24 months.",
        ))
    elif bare_soil >= T["bare_soil_warning"]:
        anomalies.append(_anomaly(
            "nesting_availability", "bare_soil_fraction", "WARNING",
            bare_soil, T["bare_soil_warning"],
            f"{bare_soil*100:.0f}% bare soil is above the warning threshold; ground-nesting bees "
            f"(70% of UK bee species) require stable, undisturbed soil structure.",
            "Reduce tillage in field margins by 50%; maintain at least 1 m wide no-till grass "
            "strips along all hedgerows and ditch edges.",
        ))

    # Disturbance
    if disturbance >= T["disturbance_critical"]:
        anomalies.append(_anomaly(
            "nesting_availability", "disturbance_score", "CRITICAL",
            disturbance, T["disturbance_critical"],
            f"Disturbance index of {disturbance:.2f} indicates severe mechanical disruption (heavy traffic, "
            f"frequent tillage) that destroys all ground-level nesting infrastructure.",
            "Immediately designate and fence off a 10 m × 10 m undisturbed refugia at each "
            "field corner; apply zero-till across all conservation headlands starting this season.",
        ))
    elif disturbance >= T["disturbance_warning"]:
        anomalies.append(_anomaly(
            "nesting_availability", "disturbance_score", "WARNING",
            disturbance, T["disturbance_warning"],
            f"Disturbance index of {disturbance:.2f} is high; field operations are fragmenting nesting "
            f"habitat and disrupting overwintering queen emergence.",
            "Shift any spring cultivation to post-May (after ground-nesting queen emergence); "
            "install 'bee rough' sandy/gravel patches (1 m²) in south-facing locations.",
        ))

    return anomalies


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def detect_anomalies(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Run all rule-based checks against the raw data bundle.

    Returns a list of anomaly dicts, sorted by severity (CRITICAL first).
    """
    anomalies: list[dict] = []

    anomalies.extend(_check_pesticide(raw["pesticide"]))
    anomalies.extend(_check_soil(raw["soil"], raw["nasa"]))
    anomalies.extend(_check_climate(raw["climate"]))
    anomalies.extend(_check_floral(raw["ndvi"], raw["gbif"]))
    anomalies.extend(_check_nesting(raw["ndvi"]))

    # Sort: CRITICAL → WARNING → INFO
    severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    anomalies.sort(key=lambda a: severity_order.get(a["severity"], 3))

    return anomalies


def has_ai_trigger_anomaly(anomalies: list[dict[str, Any]]) -> bool:
    """Return True if any anomaly has severity WARNING or CRITICAL."""
    return any(a["severity"] in ("WARNING", "CRITICAL") for a in anomalies)
