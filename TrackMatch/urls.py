from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from .views import AsyncScraperView

def home_view(request):
    return JsonResponse({"status": "API running"})

urlpatterns = [
    path('', home_view),
    path('admin/', admin.site.urls),
    path('api/', AsyncScraperView.as_view(), name='api')
]
