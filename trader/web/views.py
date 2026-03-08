"""Web 视图。"""

from django.http import HttpRequest, HttpResponse


def home(request: HttpRequest) -> HttpResponse:
    """首页视图。"""
    return HttpResponse("trader project is ready")

