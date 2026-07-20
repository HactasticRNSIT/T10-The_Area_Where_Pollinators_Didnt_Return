export interface ZoneSummary {
  zone_id: string;
  name: string;
  lat: number;
  lon: number;
}

export interface HistoryPoint {
  analysed_at: string;
  activity_score: number;
  resilience_score?: number | null;
  overall_stress?: number | null;
}

export interface PhenologyCrop {
  crop: string;
  flowering_start: string;
  flowering_end: string;
  critical_window_days: number;
}

export interface InterventionPlanItem {
  action?: string;
  recommended_action?: string;
  priority?: 'High' | 'Medium' | 'Low' | string;
  cost_tier?: 'Low' | 'Medium' | 'High' | string;
  uplift_range?: string;
  rationale?: string;
  factor?: string;
  variable?: string;
}

export interface LoggedIntervention {
  id: number;
  intervention: string;
  applied_at?: string | null;
  notes?: string | null;
  before_score?: number | null;
  after_score?: number | null;
  delta?: number | null;
}

export interface HivePlacementAdvice {
  crop?: string;
  hives_per_hectare?: number;
  hives_per_ha?: number | string;
  placement_radius_m?: number;
  max_forage_m?: number | string;
  orientation?: string;
  timing?: string;
  timing_note?: string;
  species_recommendation?: string;
  species?: string;
  placement_tip?: string;
}

export interface CropRiskDetail {
  risk_label?: string;
  risk_level?: string;
  value_at_risk_inr?: number | null;
}

export interface Anomaly {
  severity: string;
  factor: string;
  variable: string;
  description?: string;
  observation?: string;
  recommended_action?: string;
}

export interface DecisionBrief {
  data_confidence_score?: number;
  data_confidence_label?: string;
  resilience_score?: number;
  intervention_plan?: InterventionPlanItem[];
  hive_placement?: HivePlacementAdvice[];
  top_risk_drivers?: Array<{ factor: string; label?: string; weighted_impact?: number }>;
  activity_score_margin?: number;
  activity_score_range?: [number, number];
}

export interface AnalysisResponse {
  zone_id: string;
  displayName?: string;
  latitude: number;
  longitude: number;
  analysed_at: string;
  activity_score: number;
  activity_score_margin?: number;
  activity_score_range?: [number, number];
  activity_label: string;
  habitat_suitability_score?: number;
  pollination_stress_index?: string;
  crop_risk?: Record<string, string>;
  crop_risk_details?: Record<string, CropRiskDetail>;
  crop_dependency?: Record<string, number>;
  crop_weighted_stress?: number | null;
  contribution_scores?: Record<string, number>;
  climate?: {
    wind_speed_kmh: number;
    wind_stress_level: "None" | "Moderate" | "High" | "Critical";
  };
  anomalies?: Anomaly[];
  biodiversity_insight?: string;
  top_intervention?: string;
  pollination_boost_actions?: string[];
  decision_brief?: DecisionBrief;
  _meta?: {
    overall_stress?: number;
    raw_factor_stress?: Record<string, number>;
    factor_weights?: Record<string, number>;
    data_quality?: Record<string, string>;
    visitation_summary?: Record<string, unknown>;
    model_limitations?: string;
    data_caveats?: string[];
  };
}

export interface CompareResponse {
  zones: Array<AnalysisResponse & { status?: string; error?: string }>;
  completed: number;
  total: number;
  wall_clock_ms: number;
}

