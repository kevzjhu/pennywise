from django.urls import path
from transactions import views

urlpatterns = [
    path("", views.home, name="home"),
]