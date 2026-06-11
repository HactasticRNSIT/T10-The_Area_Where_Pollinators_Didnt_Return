from typing import Any
from scorer import compute_crop_risk_details

class _CropRiskLabel(str):
    """String risk label with read-only dict-like access for transitional callers."""

    def __new__(cls, label: str, detail: dict[str, Any]):
        obj = str.__new__(cls, label)
        obj._detail = detail
        return obj

    def __contains__(self, key: object) -> bool:
        return key in self._detail

    def get(self, key: str, default: Any = None) -> Any:
        return self._detail.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._detail[key]


def compute_crop_risks(
    overall_stress: float,
    zone_id: str = "",
    geo_profile: dict | None = None,
) -> dict[str, Any]:
    """Return the legacy crop->risk-label mapping used by existing callers."""
    return {
        crop: _CropRiskLabel(detail["risk_label"], detail)
        for crop, detail in compute_crop_risk_details(overall_stress, zone_id, geo_profile).items()
    }
