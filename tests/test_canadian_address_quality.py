from addressforge.api.server import AddressPlatformService, AddressRequest
from addressforge.core.common import hybrid_canadian_parse_address
from addressforge.core.profiles.factory import get_profile
from addressforge.pipelines.cleaning import _extract_feature_flags


CANADA_PROFILE = get_profile("base_canada")


def test_hybrid_parser_extracts_apartment_unit_and_tail():
    parsed = hybrid_canadian_parse_address(
        "2060 Quingate Place, Apt 1123, Halifax, NS, B3L 4P7, CA",
        profile=CANADA_PROFILE,
    )
    assert parsed["street_number"] == "2060"
    assert parsed["street_name"] == "QUINGATE PLACE"
    assert parsed["unit_number"] == "1123"
    assert parsed["city"] == "Halifax"
    assert parsed["province"] == "NS"


def test_hybrid_parser_handles_dotted_unit_prefix():
    parsed = hybrid_canadian_parse_address("2060 Quingate Place, Apt. 1123, Halifax, NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "2060"
    assert parsed["street_name"] == "QUINGATE PLACE"
    assert parsed["unit_number"] == "1123"


def test_hybrid_parser_strips_inline_city_province_tail():
    parsed = hybrid_canadian_parse_address("RM 201 123 MAIN ST HALIFAX NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "123"
    assert parsed["street_name"] == "MAIN ST"
    assert parsed["unit_number"] == "201"
    assert parsed["city"] == "Halifax"
    assert parsed["province"] == "NS"


def test_validate_plain_house_defaults_to_single_unit():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="14 Mullock Road, Rhodes Corner, NS, B4V 5N5",
            city="Rhodes Corner",
            province="NS",
            postal_code="B4V 5N5",
        )
    )
    assert result["building_type"] == "single_unit"
    assert result["decision"] == "accept"


def test_validate_plain_house_street_address_does_not_drift_to_commercial():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="14 Park Street, Trenton, NS, B0K1X0",
            city="Trenton",
            province="NS",
            postal_code="B0K1X0",
        )
    )
    assert result["building_type"] == "single_unit"
    assert result["decision"] == "accept"


def test_validate_geographic_upper_lower_place_name_remains_single_unit():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="48 Rudolf Road, Upper Lahave, NS, B4V7B7",
            city="Upper Lahave",
            province="NS",
            postal_code="B4V7B7",
        )
    )
    assert result["building_type"] == "single_unit"


def test_validate_true_upper_unit_remains_multi_unit():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="Upper 123 Main St, Halifax, NS",
            city="Halifax",
            province="NS",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["suggested_unit_number"] == "UPPER"


def test_validate_low_confidence_falls_back_to_review_not_reject():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="Tim Hortons Childrens Camp 300Tim Horton Rd TATAMAGOUCHE NS",
            city="Tatamagouche",
            province="NS",
        )
    )
    assert result["decision"] == "review"


def test_validate_marks_suite_address_as_commercial():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="1550 Bedford Highway Suite 301, Bedford, NS",
            city="Bedford",
            province="NS",
        )
    )
    assert result["building_type"] == "commercial"
    assert result["suggested_unit_number"] == "301"
    assert result["decision"] == "accept"


def test_validate_residential_unit_is_multi_unit_not_commercial():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="2060 Quingate Place Unit 1123, Halifax, NS",
            city="Halifax",
            province="NS",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["suggested_unit_number"] == "1123"
    assert result["decision"] == "accept"


def test_hybrid_parser_requires_comma_or_explicit_hint_for_bare_unit_recovery():
    parsed = hybrid_canadian_parse_address("194 Union St 1676 PICTOU NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "194"
    assert parsed["street_name"] == "UNION ST"
    assert parsed["unit_number"] is None


def test_validate_double_number_house_does_not_false_extract_unit():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="194 Union St 1676 PICTOU NS",
            city="Pictou",
            province="NS",
        )
    )
    assert result["building_type"] == "single_unit"
    assert result["suggested_unit_number"] is None


def test_validate_comma_bare_unit_city_pattern_still_recovers_true_apartment_unit():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="1122 Tower Road, 312 Halifax NS",
            city="Halifax",
            province="NS",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["suggested_unit_number"] == "312"


def test_validate_no_comma_bare_trailing_unit_city_pattern_recovers_true_apartment_unit():
    service = AddressPlatformService()

    result = service.validate(
        AddressRequest(
            raw_address_text="241 Broad Street 105 Bedford NS",
            city="Bedford",
            province="NS",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["suggested_unit_number"] == "105"

    result = service.validate(
        AddressRequest(
            raw_address_text="5633 Fenwick St 305 HALIFAX NS",
            city="Halifax",
            province="NS",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["suggested_unit_number"] == "305"


def test_validate_repeated_leading_unit_before_known_city_recovers_true_apartment_unit():
    service = AddressPlatformService()

    result = service.validate(
        AddressRequest(
            raw_address_text="505-1000 micmac boulevard 505 Dartmouth NS",
            city="Dartmouth",
            province="NS",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["suggested_unit_number"] == "505"
    assert result["decision"] == "accept"

    result = service.validate(
        AddressRequest(
            raw_address_text="308-542 Herring Cove Rd 308 Halifax NS",
            city="Halifax",
            province="NS",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["suggested_unit_number"] == "308"
    assert result["decision"] == "accept"


def test_hybrid_parser_recovers_no_comma_bare_trailing_unit_city_without_fallback():
    parsed = hybrid_canadian_parse_address("241 Broad Street 105 Bedford NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "241"
    assert parsed["street_name"] == "BROAD STREET"
    assert parsed["unit_number"] == "105"
    assert parsed["city"] == "Bedford"
    assert parsed["province"] == "NS"

    parsed = hybrid_canadian_parse_address("5633 Fenwick St 305 HALIFAX NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "5633"
    assert parsed["street_name"] == "FENWICK ST"
    assert parsed["unit_number"] == "305"
    assert parsed["city"] == "Halifax"
    assert parsed["province"] == "NS"


def test_validate_hash_unit_and_dotted_apartment_pattern_are_multi_unit():
    service = AddressPlatformService()

    hash_result = service.validate(
        AddressRequest(
            raw_address_text="1407 St Margarets Bay Rd #101, Lakeside, NS, B3T",
            city="Lakeside",
            province="NS",
            postal_code="B3T",
        )
    )
    assert hash_result["building_type"] == "multi_unit"
    assert hash_result["suggested_unit_number"] == "101"

    dotted_result = service.validate(
        AddressRequest(
            raw_address_text="6957 Mumford Rd. Apt.27, Halifax, NS, B3L2H7, CA",
            city="Halifax",
            province="NS",
            postal_code="B3L2H7",
        )
    )
    assert dotted_result["building_type"] == "multi_unit"
    assert dotted_result["suggested_unit_number"] == "27"


def test_validate_ordinal_street_with_trailing_garage_apartment_preserves_street_and_unit_keyword():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="58 14th Street garage apt TRENTON NS",
            city="Trenton",
            province="NS",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["canonical"]["street_number"] == "58"
    assert result["canonical"]["street_name"] == "14TH STREET"
    assert result["canonical"]["city"] == "Trenton"
    assert result["canonical"]["province"] == "NS"
    assert result["suggested_unit_number"] == "GARAGE APT"


def test_validate_ordinal_street_with_compound_residential_unit_keywords():
    service = AddressPlatformService()

    basement = service.validate(
        AddressRequest(
            raw_address_text="58 14th Street basement apt TRENTON NS",
            city="Trenton",
            province="NS",
        )
    )
    assert basement["building_type"] == "multi_unit"
    assert basement["canonical"]["street_name"] == "14TH STREET"
    assert basement["suggested_unit_number"] == "BASEMENT APT"

    rear = service.validate(
        AddressRequest(
            raw_address_text="58 14th Street rear apt TRENTON NS",
            city="Trenton",
            province="NS",
        )
    )
    assert rear["building_type"] == "multi_unit"
    assert rear["canonical"]["street_name"] == "14TH STREET"
    assert rear["suggested_unit_number"] == "REAR APT"


def test_validate_comma_bare_unit_with_comma_separated_city_province_is_multi_unit():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="5870 Demone Street, 602,HALIFAX,NS,B3K 0G9",
            city="Halifax",
            province="NS",
            postal_code="B3K 0G9",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["suggested_unit_number"] == "602"


def test_validate_route_name_and_place_name_do_not_false_extract_unit():
    service = AddressPlatformService()

    route_result = service.validate(
        AddressRequest(
            raw_address_text="6886 NS-325 West Clifford NS",
            city="West Clifford",
            province="NS",
        )
    )
    assert route_result["building_type"] == "single_unit"
    assert route_result["suggested_unit_number"] is None

    highway_result = service.validate(
        AddressRequest(
            raw_address_text="3960 HIGHWAY 2, FLETCHERS LAKE, NS, CA, B2T 1A3",
            city="Fletchers Lake",
            province="NS",
            postal_code="B2T 1A3",
        )
    )
    assert highway_result["building_type"] == "single_unit"
    assert highway_result["suggested_unit_number"] is None

    noisy_tail_result = service.validate(
        AddressRequest(
            raw_address_text="3 Autumn Dr Halifax NS B3R 1H2 Canada 15 Halifax NS",
            city="Halifax",
            province="NS",
            postal_code="B3R 1H2",
        )
    )
    assert noisy_tail_result["building_type"] == "single_unit"
    assert noisy_tail_result["suggested_unit_number"] is None

    plain_house_result = service.validate(
        AddressRequest(
            raw_address_text="137 Mackay St STELLARTON",
            city="Stellarton",
            province="NS",
        )
    )
    assert plain_house_result["building_type"] == "single_unit"
    assert plain_house_result["suggested_unit_number"] is None


def test_validate_repeated_civic_single_unit_pattern_can_accept():
    service = AddressPlatformService()

    mountain_maple = service.validate(
        AddressRequest(
            raw_address_text="33 Mountain Maple Dr 33 TIMBERLEA NS",
            city="Timberlea",
            province="NS",
        )
    )
    assert mountain_maple["building_type"] == "single_unit"
    assert mountain_maple["suggested_unit_number"] is None
    assert mountain_maple["decision"] == "accept"

    west_long_island = service.validate(
        AddressRequest(
            raw_address_text="307 West Long Island Rd 307 GRAND PRE NS",
            city="Grand Pre",
            province="NS",
        )
    )
    assert west_long_island["building_type"] == "single_unit"
    assert west_long_island["suggested_unit_number"] is None
    assert west_long_island["decision"] == "accept"


def test_validate_glued_token_spacing_repair_recovers_low_confidence_review_patterns():
    service = AddressPlatformService()

    apt_result = service.validate(
        AddressRequest(
            raw_address_text="295MAIN Ave Apt 105 Halifax NS",
            city="Halifax",
            province="NS",
        )
    )
    assert apt_result["building_type"] == "multi_unit"
    assert apt_result["suggested_unit_number"] == "105"
    assert apt_result["decision"] == "accept"

    single_result = service.validate(
        AddressRequest(
            raw_address_text="1795Beaver Bank Rd BEAVER BANK NS",
            city="Beaver Bank",
            province="NS",
        )
    )
    assert single_result["building_type"] == "single_unit"
    assert single_result["suggested_unit_number"] is None
    assert single_result["decision"] == "accept"

    unit_glue_result = service.validate(
        AddressRequest(
            raw_address_text="72PRIMROSE 304UNIT Dartmouth NS",
            city="Dartmouth",
            province="NS",
        )
    )
    assert unit_glue_result["building_type"] == "multi_unit"
    assert unit_glue_result["suggested_unit_number"] == "304"


def test_validate_malformed_explicit_unit_prefix_recovery():
    service = AddressPlatformService()

    walter = service.validate(
        AddressRequest(
            raw_address_text="Apt.901-56 Walter Havill Drive Apt.901, Halifax, NS, B3N0C3, CA",
            city="Halifax",
            province="NS",
            postal_code="B3N0C3",
        )
    )
    assert walter["building_type"] == "multi_unit"
    assert walter["suggested_unit_number"] == "901"

    lucknow = service.validate(
        AddressRequest(
            raw_address_text="Unit 11 11-1097 Lucknow St, , Halifax, NS B3H 2T7",
            city="Halifax",
            province="NS",
            postal_code="B3H 2T7",
        )
    )
    assert lucknow["building_type"] == "multi_unit"
    assert lucknow["suggested_unit_number"] == "11"

    cow_bay = service.validate(
        AddressRequest(
            raw_address_text="#102-386 COW BAY RD, , HALIFAX, NS B3G 1J4",
            city="Halifax",
            province="NS",
            postal_code="B3G 1J4",
        )
    )
    assert cow_bay["building_type"] == "multi_unit"
    assert cow_bay["suggested_unit_number"] == "102"

    parkland = service.validate(
        AddressRequest(
            raw_address_text="Halifax 334 Parkland Dr apt 209 Halifax NS",
            city="Halifax",
            province="NS",
        )
    )
    assert parkland["building_type"] == "multi_unit"
    assert parkland["suggested_unit_number"] == "209"

    caxton = service.validate(
        AddressRequest(
            raw_address_text="4-Caxton Close Unit 411 Halifax NS",
            city="Halifax",
            province="NS",
        )
    )
    assert caxton["building_type"] == "multi_unit"
    assert caxton["suggested_unit_number"] == "411"


def test_validate_leading_explicit_unit_and_residential_keyword_before_civic():
    service = AddressPlatformService()

    apt3 = service.validate(
        AddressRequest(
            raw_address_text="apt3 129 main st truro NS",
            city="Truro",
            province="NS",
        )
    )
    assert apt3["building_type"] == "multi_unit"
    assert apt3["suggested_unit_number"] == "3"
    assert apt3["decision"] == "accept"

    apt1108 = service.validate(
        AddressRequest(
            raw_address_text="Apt1108 16 Rooksview Lane Bedford NS",
            city="Bedford",
            province="NS",
        )
    )
    assert apt1108["building_type"] == "multi_unit"
    assert apt1108["suggested_unit_number"] == "1108"
    assert apt1108["decision"] == "accept"

    lower509 = service.validate(
        AddressRequest(
            raw_address_text="Lower509 old sackville road Lower Sackville NS",
            city="Lower Sackville",
            province="NS",
        )
    )
    assert lower509["building_type"] == "multi_unit"
    assert lower509["suggested_unit_number"] == "LOWER"
    assert lower509["decision"] == "accept"


def test_validate_single_unit_parser_disagreement_can_still_accept_clean_house_patterns():
    service = AddressPlatformService()

    eagle = service.validate(
        AddressRequest(
            raw_address_text="N/A 11 EAGLE RD, Bible Hill, NS",
            city="Bible Hill",
            province="NS",
        )
    )
    assert eagle["building_type"] == "single_unit"
    assert eagle["decision"] == "accept"

    medjuck = service.validate(
        AddressRequest(
            raw_address_text="MEDJUCK 5410 SPRING GARDEN RD, HALIFAX, NS",
            city="Halifax",
            province="NS",
        )
    )
    assert medjuck["building_type"] == "single_unit"
    assert medjuck["decision"] == "accept"

    terrace = service.validate(
        AddressRequest(
            raw_address_text="Terrace Street 264 New Glasgow NS",
            city="New Glasgow",
            province="NS",
        )
    )
    assert terrace["building_type"] == "single_unit"
    assert terrace["decision"] == "accept"


def test_feature_flags_ignore_postal_noise_but_keep_double_number_boundary_signal():
    flags = _extract_feature_flags(
        "14 Park Street, Trenton, NS, B0K1X0",
        "single_unit",
        {"street_name": "PARK STREET"},
    )
    assert flags["has_double_number"] == 0

    flags = _extract_feature_flags(
        "194 Union St 1676 PICTOU NS",
        "single_unit",
        {"street_name": "UNION ST"},
    )
    assert flags["has_double_number"] == 1


def test_hybrid_parser_recovers_route_only_before_city_pattern():
    parsed = hybrid_canadian_parse_address("HIGHWAY 376 Lyons Brook NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] is None
    assert parsed["street_name"] == "HIGHWAY 376"
    assert parsed["unit_number"] is None
    assert parsed["city"] == "Lyons Brook"
    assert parsed["province"] == "NS"


def test_hybrid_parser_recovers_reversed_civic_before_city_pattern():
    parsed = hybrid_canadian_parse_address("Terrace Street 264 New Glasgow NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "264"
    assert parsed["street_name"] == "TERRACE STREET"
    assert parsed["unit_number"] is None
    assert parsed["city"] == "New Glasgow"
    assert parsed["province"] == "NS"

    parsed = hybrid_canadian_parse_address("Braemar Drive 11 Dartmouth NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "11"
    assert parsed["street_name"] == "BRAEMAR DRIVE"
    assert parsed["unit_number"] is None
    assert parsed["city"] == "Dartmouth"
    assert parsed["province"] == "NS"


def test_hybrid_parser_does_not_default_missing_city_to_halifax():
    parsed = hybrid_canadian_parse_address(
        "Granville Street 285, New Glasgow, NS, B2H4Y8, CA",
        profile=CANADA_PROFILE,
    )
    assert parsed["street_number"] is None
    assert parsed["street_name"] is None
    assert parsed["city"] == "New Glasgow"
    assert parsed["province"] == "NS"
    assert parsed["postal_code"] == "B2H 4Y8"


def test_hybrid_parser_recovers_prefixed_civic_before_city_pattern():
    parsed = hybrid_canadian_parse_address("N/A 11 EAGLE RD, Bible Hill, NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "11"
    assert parsed["street_name"] == "EAGLE RD"
    assert parsed["unit_number"] is None
    assert parsed["city"] == "Bible Hill"
    assert parsed["province"] == "NS"

    parsed = hybrid_canadian_parse_address("MEDJUCK 5410 SPRING GARDEN RD, HALIFAX, NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "5410"
    assert parsed["street_name"] == "SPRING GARDEN RD"
    assert parsed["unit_number"] is None
    assert parsed["city"] == "Halifax"
    assert parsed["province"] == "NS"


def test_hybrid_parser_recovers_prefixed_unit_civic_before_city_pattern():
    parsed = hybrid_canadian_parse_address("SOUTH END 709-1530 BIRMINGHAM ST HALIFAX NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "1530"
    assert parsed["street_name"] == "BIRMINGHAM ST"
    assert parsed["unit_number"] == "709"
    assert parsed["city"] == "Halifax"
    assert parsed["province"] == "NS"


def test_hybrid_parser_handles_basement_prefix_as_unit():
    parsed = hybrid_canadian_parse_address("Basement 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "123"
    assert parsed["street_name"] == "MAIN ST"
    assert parsed["unit_number"] == "BASEMENT"


def test_hybrid_parser_handles_unit_hash_suffix():
    parsed = hybrid_canadian_parse_address("123 Main St Unit #5, Halifax, NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "123"
    assert parsed["street_name"] == "MAIN ST"
    assert parsed["unit_number"] == "5"


def test_hybrid_parser_handles_penthouse_and_main_floor_variants():
    penthouse = hybrid_canadian_parse_address("Penthouse 2 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert penthouse["street_number"] == "123"
    assert penthouse["street_name"] == "MAIN ST"
    assert penthouse["unit_number"] == "PH 2"

    trailing = hybrid_canadian_parse_address("123 Main St Penthouse 2, Halifax, NS", profile=CANADA_PROFILE)
    assert trailing["street_number"] == "123"
    assert trailing["street_name"] == "MAIN ST"
    assert trailing["unit_number"] == "PH 2"

    main_floor = hybrid_canadian_parse_address("Main Floor 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert main_floor["street_number"] == "123"
    assert main_floor["street_name"] == "MAIN ST"
    assert main_floor["unit_number"] == "MAIN FLOOR"


def test_hybrid_parser_handles_positional_and_ordinal_floor_variants():
    rear = hybrid_canadian_parse_address("Rear 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert rear["street_number"] == "123"
    assert rear["street_name"] == "MAIN ST"
    assert rear["unit_number"] == "REAR"

    front = hybrid_canadian_parse_address("Front 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert front["street_number"] == "123"
    assert front["street_name"] == "MAIN ST"
    assert front["unit_number"] == "FRONT"

    second_floor = hybrid_canadian_parse_address("2nd Floor 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert second_floor["street_number"] == "123"
    assert second_floor["street_name"] == "MAIN ST"
    assert second_floor["unit_number"] == "2ND FLOOR"

    trailing_floor = hybrid_canadian_parse_address("123 Main St 2nd Floor, Halifax, NS", profile=CANADA_PROFILE)
    assert trailing_floor["street_number"] == "123"
    assert trailing_floor["street_name"] == "MAIN ST"
    assert trailing_floor["unit_number"] == "2ND FLOOR"


def test_hybrid_parser_handles_ground_floor_variants():
    ground = hybrid_canadian_parse_address("Ground Floor 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert ground["street_number"] == "123"
    assert ground["street_name"] == "MAIN ST"
    assert ground["unit_number"] == "GROUND FLOOR"

    gf = hybrid_canadian_parse_address("123 Main St GF, Halifax, NS", profile=CANADA_PROFILE)
    assert gf["street_number"] == "123"
    assert gf["street_name"] == "MAIN ST"
    assert gf["unit_number"] == "GF"

    main_flr = hybrid_canadian_parse_address("Main Flr 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert main_flr["street_number"] == "123"
    assert main_flr["street_name"] == "MAIN ST"
    assert main_flr["unit_number"] == "MAIN FLOOR"


def test_hybrid_parser_handles_level_variants():
    level = hybrid_canadian_parse_address("Level 2 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert level["street_number"] == "123"
    assert level["street_name"] == "MAIN ST"
    assert level["unit_number"] == "LEVEL 2"

    lvl = hybrid_canadian_parse_address("Lvl 2 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert lvl["street_number"] == "123"
    assert lvl["street_name"] == "MAIN ST"
    assert lvl["unit_number"] == "LEVEL 2"

    trailing = hybrid_canadian_parse_address("123 Main St Level 2, Halifax, NS", profile=CANADA_PROFILE)
    assert trailing["street_number"] == "123"
    assert trailing["street_name"] == "MAIN ST"
    assert trailing["unit_number"] == "LEVEL 2"


def test_hybrid_parser_handles_building_prefix_variants():
    building = hybrid_canadian_parse_address("Building A 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert building["street_number"] == "123"
    assert building["street_name"] == "MAIN ST"
    assert building["unit_number"] == "A"

    building_unit = hybrid_canadian_parse_address("Building A Unit 5 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert building_unit["street_number"] == "123"
    assert building_unit["street_name"] == "MAIN ST"
    assert building_unit["unit_number"] == "A-5"

    trailing = hybrid_canadian_parse_address("123 Main St Bldg A, Halifax, NS", profile=CANADA_PROFILE)
    assert trailing["street_number"] == "123"
    assert trailing["street_name"] == "MAIN ST"
    assert trailing["unit_number"] == "A"


def test_validate_exposes_parser_disagreement_hint():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="1550 Bedford Highway Suite 301, Bedford, NS",
            city="Bedford",
            province="NS",
        )
    )
    assert "parser_disagreement" in result["hints"]
    assert "alternate_unit_candidates" in result["hints"]


def test_validate_floor_variants_remain_multi_unit():
    service = AddressPlatformService()

    second_floor = service.validate(
        AddressRequest(
            raw_address_text="2nd Floor 123 Main St, Halifax, NS",
            city="Halifax",
            province="NS",
        )
    )
    assert second_floor["building_type"] == "multi_unit"
    assert second_floor["decision"] == "accept"

    ground_floor = service.validate(
        AddressRequest(
            raw_address_text="Ground Floor 123 Main St, Halifax, NS",
            city="Halifax",
            province="NS",
        )
    )
    assert ground_floor["building_type"] == "multi_unit"
    assert ground_floor["decision"] == "accept"


def test_validate_building_prefix_with_unit_remains_multi_unit():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="Building A Unit 5 123 Main St, Halifax, NS",
            city="Halifax",
            province="NS",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["decision"] == "accept"


def test_hybrid_parser_handles_trailing_bare_unit_before_city():
    parsed = hybrid_canadian_parse_address("1122 Tower Road, 312 Halifax NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "1122"
    assert parsed["street_name"] == "TOWER ROAD"
    assert parsed["unit_number"] == "312"
    assert parsed["city"] == "Halifax"
    assert parsed["province"] == "NS"


def test_validate_trailing_bare_unit_before_city_is_multi_unit():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="1122 Tower Road, 312 Halifax NS",
            city="Halifax",
            province="NS",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["suggested_unit_number"] == "312"
    assert result["decision"] == "accept"


def test_validate_inline_unit_with_repeated_street_tail_is_multi_unit():
    service = AddressPlatformService()
    result = service.validate(
        AddressRequest(
            raw_address_text="1119 Tower Rd unit 706 Tower Road Halifax NS",
            city="Halifax",
            province="NS",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["suggested_unit_number"] == "706"
    assert result["decision"] == "accept"


def test_validate_strong_commercial_premise_names_remain_commercial():
    service = AddressPlatformService()

    square = service.validate(
        AddressRequest(
            raw_address_text="Scotia Square Suite 500, Halifax, NS",
            city="Halifax",
            province="NS",
        )
    )
    assert square["building_type"] == "commercial"
    assert square["suggested_unit_number"] == "500"

    mall = service.validate(
        AddressRequest(
            raw_address_text="Park Lane Mall Unit 210, Halifax, NS",
            city="Halifax",
            province="NS",
        )
    )
    assert mall["building_type"] == "commercial"
    assert mall["suggested_unit_number"] == "210"


def test_validate_unit_keyword_glued_to_street_or_number_is_recovered():
    service = AddressPlatformService()

    apt_glued = service.validate(
        AddressRequest(
            raw_address_text="67 KINGS WHARF PLACEAPT 308, DARTMOUTH, NS, CA, B2Y 0C6",
            city="Dartmouth",
            province="NS",
            postal_code="B2Y 0C6",
        )
    )
    assert apt_glued["building_type"] == "multi_unit"
    assert apt_glued["suggested_unit_number"] == "308"
    assert apt_glued["decision"] == "accept"

    room_glued = service.validate(
        AddressRequest(
            raw_address_text="660 FRANCKLYN STROOM 216, HALIFAX, NS, CA, B3H 3B5",
            city="Halifax",
            province="NS",
            postal_code="B3H 3B5",
        )
    )
    assert room_glued["building_type"] == "multi_unit"
    assert room_glued["suggested_unit_number"] == "216"
    assert room_glued["decision"] == "accept"

    unit_glued = service.validate(
        AddressRequest(
            raw_address_text="1094 WELLINGTON STREET UNIT1302 Halifax NS",
            city="Halifax",
            province="NS",
        )
    )
    assert unit_glued["building_type"] == "multi_unit"
    assert unit_glued["suggested_unit_number"] == "1302"
    assert unit_glued["decision"] == "accept"


def test_validate_leading_bare_unit_comma_before_civic_is_recovered():
    service = AddressPlatformService()

    result = service.validate(
        AddressRequest(
            raw_address_text="404, 26 Jacob Lane, Bedford, Halifax, Halifax, NS, B3M0H6, CA",
            city="Halifax",
            province="NS",
            postal_code="B3M0H6",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["suggested_unit_number"] == "404"
    assert result["decision"] == "accept"


def test_validate_leading_explicit_unit_glued_to_civic_is_recovered():
    service = AddressPlatformService()

    result = service.validate(
        AddressRequest(
            raw_address_text="Unit13071545 South Park Street Halifax NS",
            city="Halifax",
            province="NS",
        )
    )
    assert result["building_type"] == "multi_unit"
    assert result["suggested_unit_number"] == "1307"
    assert result["canonical"]["street_number"] == "1545"
    assert result["canonical"]["street_name"] == "SOUTH PARK ST"
    assert result["decision"] == "accept"


def test_validate_prefixed_noise_civic_street_with_unit_repeated_tail_is_recovered():
    service = AddressPlatformService()

    result = service.validate(
        AddressRequest(
            raw_address_text="SUSHI ON BROAD INC226 BROAD ST UNIT107BEDFORD NS B4B 2M9CANADA Bedford NS",
            city="Bedford",
            province="NS",
            postal_code="B4B 2M9",
        )
    )
    assert result["building_type"] in {"multi_unit", "commercial"}
    assert result["suggested_unit_number"] == "107"
    assert result["canonical"]["street_number"] == "226"
    assert result["canonical"]["street_name"] == "BROAD ST"
    assert result["decision"] == "accept"


def test_validate_trailing_bare_unit_without_comma_before_city_is_recovered():
    service = AddressPlatformService()

    windmill = service.validate(
        AddressRequest(
            raw_address_text="275 Windmill Rd 128 DARTMOUTH",
            city="Dartmouth",
            province="NS",
        )
    )
    assert windmill["building_type"] == "multi_unit"
    assert windmill["suggested_unit_number"] == "128"
    assert windmill["decision"] == "accept"

    norma = service.validate(
        AddressRequest(
            raw_address_text="195 Norma St 6 NEW GLASGOW NS",
            city="New Glasgow",
            province="NS",
        )
    )
    assert norma["building_type"] == "multi_unit"
    assert norma["suggested_unit_number"] == "6"
    assert norma["decision"] == "accept"

    uteck = service.validate(
        AddressRequest(
            raw_address_text="20 LARRY UTECK BLVD 203 UNIT Halifax NS",
            city="Halifax",
            province="NS",
        )
    )
    assert uteck["building_type"] == "multi_unit"
    assert uteck["suggested_unit_number"] == "203"
    assert uteck["decision"] == "accept"


def test_hybrid_parser_handles_commercial_premise_without_civic_number():
    parsed = hybrid_canadian_parse_address("Scotia Square Suite 500, Halifax, NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] is None
    assert parsed["street_name"] is None
    assert parsed["unit_number"] == "500"

    prefixed = hybrid_canadian_parse_address("Suite 500 Scotia Square, Halifax, NS", profile=CANADA_PROFILE)
    assert prefixed["street_number"] is None
    assert prefixed["street_name"] is None
    assert prefixed["unit_number"] == "500"

    unit_prefixed = hybrid_canadian_parse_address("Unit 210 Park Lane Mall, Halifax, NS", profile=CANADA_PROFILE)
    assert unit_prefixed["street_number"] is None
    assert unit_prefixed["street_name"] is None
    assert unit_prefixed["unit_number"] == "210"

    kiosk = hybrid_canadian_parse_address("Kiosk 2 Scotia Square, Halifax, NS", profile=CANADA_PROFILE)
    assert kiosk["street_number"] is None
    assert kiosk["street_name"] is None
    assert kiosk["unit_number"] == "KIOSK 2"


def test_hybrid_parser_handles_abbreviated_and_labeled_prefix_units():
    lower = hybrid_canadian_parse_address("Lwr 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert lower["street_number"] == "123"
    assert lower["street_name"] == "MAIN ST"
    assert lower["unit_number"] == "LWR"

    upper = hybrid_canadian_parse_address("Upr 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert upper["street_number"] == "123"
    assert upper["street_name"] == "MAIN ST"
    assert upper["unit_number"] == "UPR"

    door = hybrid_canadian_parse_address("Door 3 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert door["street_number"] == "123"
    assert door["street_name"] == "MAIN ST"
    assert door["unit_number"] == "DOOR 3"

    lot = hybrid_canadian_parse_address("Lot 12 123 Main St, Halifax, NS", profile=CANADA_PROFILE)
    assert lot["street_number"] == "123"
    assert lot["street_name"] == "MAIN ST"
    assert lot["unit_number"] == "LOT 12"

    trailing_door = hybrid_canadian_parse_address("123 Main St Door 3, Halifax, NS", profile=CANADA_PROFILE)
    assert trailing_door["street_number"] == "123"
    assert trailing_door["street_name"] == "MAIN ST"
    assert trailing_door["unit_number"] == "DOOR 3"

    trailing_lot = hybrid_canadian_parse_address("123 Main St Lot 12, Halifax, NS", profile=CANADA_PROFILE)
    assert trailing_lot["street_number"] == "123"
    assert trailing_lot["street_name"] == "MAIN ST"
    assert trailing_lot["unit_number"] == "LOT 12"

