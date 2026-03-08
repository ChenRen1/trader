"""项目路由入口。"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('', include('trader.web.urls')),
    path('admin/', admin.site.urls),
]
