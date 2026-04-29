from addressforge.api.server import AddressPlatformService, AddressRequest
from addressforge.core.common import hybrid_canadian_parse_address
from addressforge.core.profiles.factory import get_profile


CANADA_PROFILE = get_profile("base_canada")


def test_hybrid_parser_extracts_apartment_unit_and_tail():
    parsed = hybrid_canadian_parse_address(
        "2060 Quingate Place, Apt 1123, Halifax, NS, B3L 4P7, CA",
        profile=CANADA_PROFILE,
    )
    assert parsed["street_number"] == "2060"
    assert parsed["street_name"] == "QUINGATE PL"
    assert parsed["unit_number"] == "1123"
    assert parsed["city"] == "Halifax"
    assert parsed["province"] == "NS"


def test_hybrid_parser_handles_dotted_unit_prefix():
    parsed = hybrid_canadian_parse_address("2060 Quingate Place, Apt. 1123, Halifax, NS", profile=CANADA_PROFILE)
    assert parsed["street_number"] == "2060"
    assert parsed["street_name"] == "QUINGATE PL"
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


def test_hybrid_parser_handles_commercial_premise_without_civic_number():
    parsed = hybrid_canadian_parse_address("Scotia Square Suite 500, Halifax, NS")
    assert parsed["street_number"] is None
    assert parsed["street_name"] is None
    assert parsed["unit_number"] == "500"

    prefixed = hybrid_canadian_parse_address("Suite 500 Scotia Square, Halifax, NS")
    assert prefixed["street_number"] is None
    assert prefixed["street_name"] is None
    assert prefixed["unit_number"] == "500"

    unit_prefixed = hybrid_canadian_parse_address("Unit 210 Park Lane Mall, Halifax, NS")
    assert unit_prefixed["street_number"] is None
    assert unit_prefixed["street_name"] is None
    assert unit_prefixed["unit_number"] == "210"

    kiosk = hybrid_canadian_parse_address("Kiosk 2 Scotia Square, Halifax, NS")
    assert kiosk["street_number"] is None
    assert kiosk["street_name"] is None
    assert kiosk["unit_number"] == "KIOSK 2"


def test_hybrid_parser_handles_abbreviated_and_labeled_prefix_units():
    lower = hybrid_canadian_parse_address("Lwr 123 Main St, Halifax, NS")
    assert lower["street_number"] == "123"
    assert lower["street_name"] == "MAIN ST"
    assert lower["unit_number"] == "LWR"

    upper = hybrid_canadian_parse_address("Upr 123 Main St, Halifax, NS")
    assert upper["street_number"] == "123"
    assert upper["street_name"] == "MAIN ST"
    assert upper["unit_number"] == "UPR"

    door = hybrid_canadian_parse_address("Door 3 123 Main St, Halifax, NS")
    assert door["street_number"] == "123"
    assert door["street_name"] == "MAIN ST"
    assert door["unit_number"] == "DOOR 3"

    lot = hybrid_canadian_parse_address("Lot 12 123 Main St, Halifax, NS")
    assert lot["street_number"] == "123"
    assert lot["street_name"] == "MAIN ST"
    assert lot["unit_number"] == "LOT 12"

    trailing_door = hybrid_canadian_parse_address("123 Main St Door 3, Halifax, NS")
    assert trailing_door["street_number"] == "123"
    assert trailing_door["street_name"] == "MAIN ST"
    assert trailing_door["unit_number"] == "DOOR 3"

    trailing_lot = hybrid_canadian_parse_address("123 Main St Lot 12, Halifax, NS")
    assert trailing_lot["street_number"] == "123"
    assert trailing_lot["street_name"] == "MAIN ST"
    assert trailing_lot["unit_number"] == "LOT 12"
