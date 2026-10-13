from datetime import UTC, datetime

import pytest

from mmscan.baseline import build_baselines
from mmscan.config import Config
from mmscan.deals import ABOVE, GOOD, GREAT, MARGINAL, rank_deals, saving_verdict
from tests.helpers import config, scored

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)  # two hours after scored()'s updated_at


@pytest.fixture
def cfg(default_config_dict) -> Config:
    return config(default_config_dict, relative={"min_samples": 3, "percentile_good": 20})


def history(total=1000, carriers="SQ", cabin="business", n=3, origin="MUC", dest="SIN", month=11):
    return [
        scored(
            total,
            date=f"2026-{month}-0{i}",
            carriers=carriers,
            cabin=cabin,
            origin=origin,
            dest=dest,
        )
        for i in range(1, n + 1)
    ]


def rank(cfg, current, past=None, **kw):
    past = history() if past is None else past
    return rank_deals(current, build_baselines(past, cfg), cfg, NOW, **kw)


@pytest.mark.parametrize(
    "pct,label",
    [
        (35, GREAT),
        (30, GREAT),
        (29.9, GOOD),
        (10, GOOD),
        (9.9, MARGINAL),
        (0, MARGINAL),
        (-0.1, ABOVE),
    ],
)
def test_verdict_edges(cfg, pct, label):
    assert saving_verdict(pct, cfg) == label


def test_thresholds_must_be_ordered(default_config_dict):
    with pytest.raises(ValueError, match="good_pct"):
        config(default_config_dict, savings={"great_pct": 10, "good_pct": 20})


def test_saving_is_measured_against_the_median(cfg):
    out = rank(cfg, [scored(700, date="2026-12-01")])
    d = out["deals"][0]
    assert (d.usual, d.save, round(d.save_pct), d.verdict) == (1000, 300, 30, GREAT)


def test_above_usual_has_negative_saving(cfg):
    d = rank(cfg, [scored(1100, date="2026-12-01")])["deals"][0]
    assert d.save == -100 and d.verdict == ABOVE
    assert rank(cfg, [scored(1100, date="2026-12-01")])["best"] is None


def test_ranked_by_percent_saving_by_default(cfg):
    cur = [
        scored(900, date="2026-12-01"),
        scored(600, date="2026-12-02"),
        scored(800, date="2026-12-03"),
    ]
    assert [d.s.total_eur for d in rank(cfg, cur)["deals"]] == [600, 800, 900]
    assert [d.s.date for d in rank(cfg, cur, sort="date")["deals"]] == [
        "2026-12-01",
        "2026-12-02",
        "2026-12-03",
    ]
    assert [d.s.total_eur for d in rank(cfg, cur, sort="total")["deals"]] == [600, 800, 900]
    assert rank(cfg, cur, sort="nonsense")["deals"][0].s.total_eur == 600


def test_pax_scales_party_figures_and_hides_small_seat_counts(cfg):
    few, plenty = scored(700, date="2026-12-01"), scored(800, date="2026-12-02")
    few.seats = 2
    plenty.seats = 4
    unknown = scored(900, date="2026-12-03")
    unknown.seats = 0
    out = rank(cfg, [few, plenty, unknown], pax=3)
    assert {d.s.date for d in out["deals"]} == {"2026-12-02", "2026-12-03"}
    d = next(d for d in out["deals"] if d.s.date == "2026-12-02")
    assert (d.party_total, d.party_usual, d.party_save) == (2400, 3000, 600)
    assert d.party_miles == 180000


def test_stale_hidden_by_default(cfg):
    old = scored(700, date="2026-12-01")
    old.updated_at = "2026-10-05T08:00:00Z"
    assert rank(cfg, [old])["deals"] == []
    assert len(rank(cfg, [old], hide_stale=False)["deals"]) == 1


def test_thin_history_goes_to_building(cfg):
    out = rank(cfg, [scored(700, date="2026-12-01")], past=history(n=2))
    assert out["deals"] == [] and [(s.total_eur, n) for s, n in out["building"]] == [(700, 2)]


def test_dynamic_is_unverified_and_never_the_banner(cfg):
    past = history(carriers="LH", month=10) + history(total=1000, carriers="SQ")
    out = rank(
        cfg,
        [scored(400, date="2026-12-01", carriers="LH"), scored(800, date="2026-12-02")],
        past=past,
    )
    assert not out["deals"][0].verified and out["deals"][0].s.carriers == "LH"
    assert out["best"].s.carriers == "SQ"
    assert [
        d.s.carriers
        for d in rank(
            cfg, [scored(400, date="2026-12-01", carriers="LH")], past=past, chart_only=True
        )["deals"]
    ] == []


def test_filters_cabin_and_route(cfg):
    past = history() + history(total=500, cabin="economy") + history(origin="FRA", dest="KUL")
    cur = [
        scored(700, date="2026-12-01"),
        scored(300, date="2026-12-02", cabin="economy"),
        scored(700, date="2026-12-03", origin="FRA", dest="KUL"),
    ]
    assert len(rank(cfg, cur, past=past)["deals"]) == 3
    assert [d.s.cabin for d in rank(cfg, cur, past=past, cabin="economy")["deals"]] == ["economy"]
    assert len(rank(cfg, cur, past=past, route="fra → kul")["deals"]) == 1
    assert len(rank(cfg, cur, past=past, route="MUC")["deals"]) == 2


def test_estimated_and_expired_never_show(cfg):
    est, gone = scored(700, date="2026-12-01", estimated=True), scored(700, date="2026-12-02")
    gone.expired = True
    out = rank(cfg, [est, gone])
    assert out["deals"] == [] and out["building"] == []


def test_counts(cfg):
    a, b = scored(600, date="2026-12-01"), scored(950, date="2026-12-02")
    a.change = "New"
    out = rank(cfg, [a, b])
    assert (out["good_count"], out["new_count"]) == (1, 1)
