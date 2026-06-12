import pytest
from django.core.management import call_command

from commodities.countries import english_name, french_name
from commodities.models import Country


def test_french_name_overrides_and_cldr():
    assert french_name("USA") == "États-Unis"
    assert french_name("COD") == "République démocratique du Congo"  # override
    assert french_name("CHL") == "Chili"  # CLDR via Babel
    assert french_name("SAU") == "Arabie saoudite"
    assert french_name("ZZZ", "Repli") == "Repli"  # unknown code → fallback


def test_english_name_overrides_and_cldr():
    assert english_name("CHN") == "China"  # CLDR via Babel
    assert english_name("COD") == "Democratic Republic of the Congo"  # override
    assert english_name("AUS") == "Australia"
    assert english_name("ZZZ", "Fallback") == "Fallback"  # unknown code → fallback


@pytest.mark.django_db
def test_relabel_countries_normalises_mixed_language_names():
    Country.objects.create(iso3="CHL", name="Chile")  # English (e.g. from OWID)
    Country.objects.create(iso3="SAU", name="Saudi Arabia")
    Country.objects.create(iso3="FRA", name="France")  # already canonical

    call_command("relabel_countries")

    assert Country.objects.get(iso3="CHL").name == "Chili"
    assert Country.objects.get(iso3="SAU").name == "Arabie saoudite"
    assert Country.objects.get(iso3="FRA").name == "France"
