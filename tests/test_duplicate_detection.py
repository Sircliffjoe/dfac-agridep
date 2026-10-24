import pytest
from decimal import Decimal
from agridep.apps.registry.models import Farmer, Farm, VerificationStatus
from agridep.apps.registry.services import check_farmer_duplicates

@pytest.mark.django_db
def test_exact_phone_duplicate():
    Farmer.objects.create(
        first_name="Tari",
        last_name="Ebi",
        phone_normalized="+2348035550001",
        state="Bayelsa",
        lga="Yenagoa"
    )

    is_dup, status_rec, reasons, matched = check_farmer_duplicates(
        first_name="Tari",
        last_name="Ebi",
        phone="+2348035550001"
    )

    assert is_dup is True
    assert status_rec == VerificationStatus.FLAGGED_DUPLICATE
    assert any("Exact phone number match" in r for r in reasons)
    assert matched is not None

@pytest.mark.django_db
def test_exact_nin_duplicate():
    f1 = Farmer.objects.create(
        first_name="Godspower",
        last_name="Akpan",
        phone_normalized="+2348035550002",
        state="Delta",
        lga="Ughelli North"
    )
    f1.set_nin("99887766554")
    f1.save()

    is_dup, status_rec, reasons, matched = check_farmer_duplicates(
        first_name="Godspower Different",
        last_name="Akpan",
        phone="+2348039999999",
        nin="99887766554"
    )

    assert is_dup is True
    assert status_rec == VerificationStatus.FLAGGED_DUPLICATE
    assert any("NIN" in r for r in reasons)
    assert matched.id == f1.id

@pytest.mark.django_db
def test_fuzzy_name_and_spatial_proximity_duplicate():
    f1 = Farmer.objects.create(
        first_name="Chukwudi",
        last_name="Nwosu",
        phone_normalized="+2348035550003",
        state="Delta",
        lga="Warri South"
    )
    Farm.objects.create(
        farmer=f1,
        name="Nwosu Fish Farm",
        latitude=Decimal('5.544200'),
        longitude=Decimal('5.760200')
    )

    # Candidate with slight typo (e.g. "Chukwudy Nwosu") within 100 meters
    is_dup, status_rec, reasons, matched = check_farmer_duplicates(
        first_name="Chukwudy",
        last_name="Nwosu",
        phone="+2348037778888",
        lat=5.544300,
        lon=5.760250
    )

    assert is_dup is True
    assert status_rec == VerificationStatus.FLAGGED_DUPLICATE
    assert any("High name similarity" in r for r in reasons)
    assert matched.id == f1.id
