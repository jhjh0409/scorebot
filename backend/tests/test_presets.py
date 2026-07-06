import pytest
from pydantic import ValidationError

from backend.pipeline.presets import (
    PRESETS_BY_ID,
    SEED_PRESETS,
    EnrichmentToggles,
    Preset,
    RubricDimension,
    get_preset,
)


def make_dimension(**overrides) -> RubricDimension:
    base = dict(key="depth", name="Depth", weight=50, guidance="Look for depth.")
    base.update(overrides)
    return RubricDimension(**base)


class TestPresetValidation:
    def test_duplicate_dimension_keys_rejected(self):
        with pytest.raises(ValidationError, match="Duplicate dimension keys"):
            Preset(
                id="x",
                name="X",
                role_description="role",
                dimensions=[make_dimension(), make_dimension(name="Other")],
            )

    def test_zero_weight_rejected(self):
        with pytest.raises(ValidationError):
            make_dimension(weight=0)

    def test_negative_weight_rejected(self):
        with pytest.raises(ValidationError):
            make_dimension(weight=-1)

    def test_empty_dimensions_rejected(self):
        with pytest.raises(ValidationError):
            Preset(id="x", name="X", role_description="role", dimensions=[])

    def test_dimension_key_must_be_snake_case(self):
        with pytest.raises(ValidationError):
            make_dimension(key="Not Snake")

    def test_normalized_weights_sum_to_one(self):
        preset = Preset(
            id="x",
            name="X",
            role_description="role",
            dimensions=[
                make_dimension(key="a", weight=30),
                make_dimension(key="b", weight=45),
                make_dimension(key="c", weight=25),
            ],
        )
        weights = preset.normalized_weights()
        assert weights == {"a": 0.30, "b": 0.45, "c": 0.25}
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_normalized_weights_handle_non_100_totals(self):
        preset = Preset(
            id="x",
            name="X",
            role_description="role",
            dimensions=[
                make_dimension(key="a", weight=2),
                make_dimension(key="b", weight=6),
            ],
        )
        assert preset.normalized_weights() == {"a": 0.25, "b": 0.75}


class TestSeedPresets:
    def test_three_seed_presets(self):
        assert sorted(PRESETS_BY_ID) == [
            "bd-intern",
            "marketing-intern",
            "software-engineer",
        ]

    def test_seed_weights_each_sum_to_100(self):
        for preset in SEED_PRESETS:
            assert sum(d.weight for d in preset.dimensions) == 100, preset.id

    def test_only_engineer_preset_has_github_enrichment(self):
        assert get_preset("software-engineer").enrichments.github is True
        assert get_preset("bd-intern").enrichments.github is False
        assert get_preset("marketing-intern").enrichments.github is False

    def test_unknown_preset_lists_valid_ids(self):
        with pytest.raises(KeyError, match="software-engineer"):
            get_preset("does-not-exist")


class TestEnrichmentToggles:
    def test_defaults_off(self):
        assert EnrichmentToggles().github is False
