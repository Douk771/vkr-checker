from vkr_checker.config import Settings
from vkr_checker.layout.soffice import SofficeInfo
from vkr_checker.main import create_app


def test_create_app_keeps_settings():
    s = Settings(_env_file=None)
    assert create_app(s, layout_info=SofficeInfo(None, None)).state.settings is s
