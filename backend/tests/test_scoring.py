"""The execution-risk model."""

from __future__ import annotations

from app.core.scoring import assess

BASE = {
    "deplane_index": 0,
    "total_segments": 2,
    "layover_minutes": 120,
    "savings_percent": 30.0,
    "bookable_seats": 5,
    "is_one_way": True,
    "deplane_city": "Istanbul",
    "ticketed_city": "Skopje",
}


def flag_codes(assessment) -> set[str]:
    return {flag.code for flag in assessment.flags}


def test_ideal_itinerary_scores_high() -> None:
    assessment = assess(**BASE)

    assert assessment.confidence >= 90
    assert assessment.band == "high"
    assert "DIRECT_FIRST_LEG" in flag_codes(assessment)


def test_the_universal_warnings_are_always_present() -> None:
    """Baggage and one-way rules apply to every hidden-city itinerary."""
    assessment = assess(**BASE)

    assert {"CARRY_ON_ONLY", "ONE_WAY_ONLY", "CONTRACT_OF_CARRIAGE", "IMMIGRATION"} <= flag_codes(
        assessment
    )


def test_a_connection_before_the_target_dominates_the_score() -> None:
    direct = assess(**BASE)
    connecting = assess(**{**BASE, "deplane_index": 1, "total_segments": 3})

    assert connecting.confidence < direct.confidence - 30
    assert "REROUTE_RISK" in flag_codes(connecting)


def test_two_connections_before_the_target_score_lower_still() -> None:
    one = assess(**{**BASE, "deplane_index": 1, "total_segments": 3})
    two = assess(**{**BASE, "deplane_index": 2, "total_segments": 4})

    assert two.confidence < one.confidence
    assert two.band == "low"


def test_scoring_does_not_consider_baggage() -> None:
    """This tool compares prices; bag allowances are out of scope by design."""
    codes = flag_codes(assess(**BASE))

    assert "CHECKED_BAG_INCLUDED" not in codes
    assert "GATE_CHECK_RISK" not in codes


def test_marginal_savings_are_penalised() -> None:
    assessment = assess(**{**BASE, "savings_percent": 6.0})

    assert "MARGINAL_SAVINGS" in flag_codes(assessment)
    assert assessment.confidence < assess(**BASE).confidence


def test_tight_and_long_layovers_are_annotated_differently() -> None:
    assert "TIGHT_CONNECTION" in flag_codes(assess(**{**BASE, "layover_minutes": 35}))
    assert "LONG_LAYOVER" in flag_codes(assess(**{**BASE, "layover_minutes": 400}))


def test_round_trip_is_scored_as_unusable() -> None:
    assessment = assess(**{**BASE, "is_one_way": False})

    assert "NOT_ONE_WAY" in flag_codes(assessment)
    assert assessment.band == "low"


def test_confidence_never_leaves_the_zero_to_hundred_range() -> None:
    worst = assess(
        **{
            **BASE,
            "deplane_index": 3,
            "total_segments": 5,
            "is_one_way": False,
            "savings_percent": 1.0,
            "bookable_seats": 1,
            "layover_minutes": 20,
        }
    )
    best = assess(**BASE)

    assert 0 <= worst.confidence <= 100
    assert 0 <= best.confidence <= 100
    assert worst.confidence == 0


def test_messages_name_the_actual_cities() -> None:
    assessment = assess(**BASE)
    bag_flag = next(flag for flag in assessment.flags if flag.code == "CARRY_ON_ONLY")

    assert "Skopje" in bag_flag.message("en")
    assert "Istanbul" in bag_flag.message("en")


def test_flags_render_in_arabic_with_the_same_values() -> None:
    """Scoring is language-free; only rendering differs."""
    assessment = assess(**BASE)
    bag_flag = next(flag for flag in assessment.flags if flag.code == "CARRY_ON_ONLY")

    arabic = bag_flag.message("ar")
    assert arabic != bag_flag.message("en")
    # City names stay in Latin script -- the dataset has no Arabic names.
    assert "Skopje" in arabic
    assert "Istanbul" in arabic


def test_confidence_is_identical_across_languages() -> None:
    english = assess(**BASE).to_dict("en")
    arabic = assess(**BASE).to_dict("ar")

    assert english["confidence"] == arabic["confidence"]
    assert [f["code"] for f in english["flags"]] == [f["code"] for f in arabic["flags"]]
