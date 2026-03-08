"""Web 路由。"""

from django.urls import path

from trader.web import views

urlpatterns = [
    path('', views.home, name='home'),
    path('market/chart/', views.market_chart_index, name='market-chart-index'),
    path('market/chart/<str:market>/<str:symbol>/', views.market_chart_page, name='market-chart-page'),
    path('market/chart-data/<str:market>/<str:symbol>/', views.market_chart_data, name='market-chart-data'),
]
