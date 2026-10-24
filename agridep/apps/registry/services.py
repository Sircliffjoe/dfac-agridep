import difflib
from typing import Tuple, List, Optional
from agridep.apps.common.encryption import hash_deterministic, encrypt_value
from agridep.apps.common.spatial import haversine_distance_km
from .models import Farmer, Farm, VerificationStatus

def check_farmer_duplicates(
    first_name: str,
    last_name: str,
    phone: str,
    nin: str = "",
    lat: Optional[float] = None,
    lon: Optional[float] = None
) -> Tuple[bool, str, List[str], Optional[Farmer]]:
    """
    Evaluates new farmer registration against existing records.
    Returns:
        (is_duplicate_or_flagged, recommended_status, reason_list, matched_farmer)
    """
    reasons = []
    norm_phone = phone.strip().replace(" ", "").replace("-", "")
    
    # 1. Exact phone match
    if norm_phone:
        existing_phone = Farmer.objects.filter(phone_normalized=norm_phone).first()
        if existing_phone:
            reasons.append(f"Exact phone number match with {existing_phone.reference_code}")
            return True, VerificationStatus.FLAGGED_DUPLICATE, reasons, existing_phone

    # 2. Exact deterministic NIN match
    if nin:
        nin_h = hash_deterministic(nin)
        existing_nin = Farmer.objects.filter(nin_hash=nin_h).first()
        if existing_nin:
            reasons.append(f"Exact National Identification Number (NIN) match with {existing_nin.reference_code}")
            return True, VerificationStatus.FLAGGED_DUPLICATE, reasons, existing_nin

    # 3. Fuzzy name + spatial proximity check
    full_name_candidate = f"{first_name} {last_name}".strip().lower()
    
    # Check existing farmers in the system
    for candidate in Farmer.objects.all()[:200]:
        cand_name = candidate.full_name.lower()
        matcher = difflib.SequenceMatcher(None, full_name_candidate, cand_name)
        ratio = matcher.ratio()

        if ratio >= 0.85:
            # High name similarity, check location if coordinates provided
            if lat is not None and lon is not None:
                farm = candidate.farms.first()
                if farm:
                    dist_km = haversine_distance_km(lat, lon, float(farm.latitude), float(farm.longitude))
                    if dist_km <= 0.50:  # Within 500 metres
                        reasons.append(
                            f"High name similarity ({ratio:.0%}) and spatial proximity ({dist_km * 1000:.0f}m) to {candidate.reference_code}"
                        )
                        return True, VerificationStatus.FLAGGED_DUPLICATE, reasons, candidate
            else:
                reasons.append(f"High name similarity ({ratio:.0%}) to {candidate.reference_code}")
                return True, VerificationStatus.PENDING_REVIEW, reasons, candidate

    return False, VerificationStatus.VERIFIED, [], None
