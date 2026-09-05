from onshape_mcp.onshape_api import m4_profile_payload, verify_profile_feature


def test_m4_payload_is_one_closed_exact_seven_segment_profile():
    payload, expected = m4_profile_payload()
    feature = payload["feature"]
    assert feature["btType"] == "BTMSketch-151"
    assert feature["parameters"][0]["queries"][0]["queryString"].find('makeId("Front")') > 0
    assert len(feature["entities"]) == 7
    assert set(expected) == {
        "m4.headAxis",
        "m4.shaftAxis",
        "m4.tip",
        "m4.shaftTop",
        "m4.shoulder",
        "m4.headTop",
        "m4.headOuter",
    }
    # Every segment ends exactly where the next starts, including closure.
    points = list(expected.values())
    for current, following in zip(points, points[1:] + points[:1]):
        assert current[1] == following[0]


def test_m4_payload_round_trips_through_geometry_verifier():
    payload, expected = m4_profile_payload()
    feature = payload["feature"] | {"featureId": "test-feature"}
    verified = verify_profile_feature(feature, expected)
    assert verified["ok"] is True
    assert verified["closed"] is True
    assert verified["entity_count"] == 7
    assert verified["segments"]["m4.shaftAxis"]["length_mm"] == 20.0
    assert verified["segments"]["m4.tip"]["length_mm"] == 2.0
    assert verified["segments"]["m4.headOuter"]["length_mm"] == 3.5


def test_verifier_rejects_missing_geometry():
    payload, expected = m4_profile_payload()
    feature = payload["feature"]
    feature["entities"] = feature["entities"][:-1]
    verified = verify_profile_feature(feature, expected)
    assert verified["ok"] is False
    assert verified["closed"] is False
    assert "missing segment m4.headOuter" in verified["errors"]
