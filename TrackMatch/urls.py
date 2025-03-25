from django.contrib import admin
from django.urls import path
from .views import AsyncScraperView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', AsyncScraperView.as_view(), name='api')
]
