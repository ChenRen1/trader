from django.apps import AppConfig


class TraderConfig(AppConfig):
    """交易应用配置。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'trader'

    def ready(self) -> None:
        """显式加载非默认目录下的管理后台注册。"""
        from trader.web import admin  # noqa: F401
