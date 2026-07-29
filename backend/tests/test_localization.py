from birdframe.localization import localized_species_name


def test_complete_norwegian_name_database_is_used():
    assert localized_species_name("Turdus merula", "fallback") == "svarttrost"
    assert localized_species_name("Apus apus", "fallback") == "tårnseiler"


def test_localization_falls_back_for_unknown_species():
    assert localized_species_name("Not a real species", "English fallback") == "English fallback"
