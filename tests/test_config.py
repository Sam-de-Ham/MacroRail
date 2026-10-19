from pathlib import Path

from macrorail.config import Config, load_config

EXAMPLE = Path(__file__).parents[1] / "deploy" / "config.example.toml"


def test_example_config_matches_defaults() -> None:
    assert load_config(EXAMPLE) == Config()
