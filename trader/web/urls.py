"""Web 路由。"""

from django.urls import path

from trader.web import views

urlpatterns = [
    path('', views.home, name='home'),
]

