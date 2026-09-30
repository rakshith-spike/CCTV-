"""Normalization contract; vendor labels are operator declarations, not detection."""
from dataclasses import dataclass


@dataclass(frozen=True)
class VendorAdapter:
    name: str

    def identify(self):
        return {
            "vendor": self.name,
            "vendor_basis": "UNKNOWN" if self.name == "UNKNOWN" else "Operator declared (not automatically detected)",
            "parser_status": "Generic evidence ingestion mode" if self.name in ("UNKNOWN", "Generic DVR/NVR") else "Vendor declared — proprietary parser unavailable in prototype",
        }


ADAPTERS = {name: VendorAdapter(name) for name in (
    "UNKNOWN", "Hikvision", "Dahua", "CP Plus", "Honeywell", "TP-Link",
    "Godrej", "Uniview", "Matrix", "Generic DVR/NVR",
)}
