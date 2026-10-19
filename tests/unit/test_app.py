from vkr_checker.config import Settings
from vkr_checker.main import create_app


def test_create_app_keeps_settings():
    s = Settings(_env_file=None)
    assert create_app(s).state.settings is s
