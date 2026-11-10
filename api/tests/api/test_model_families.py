"""Model family categorization for analytics."""

import pytest

from routers.analytics import _categorize_model


@pytest.mark.parametrize("model", ["claude-fable-5-1", "claude-fable-5"])
def test_fable_is_its_own_family(model):
    assert _categorize_model(model) == "Fable"
