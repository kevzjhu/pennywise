# transactions/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),                      # Transactions Page
    path('income/', views.income, name='income'),           # Income Page
    path('budget/', views.budget, name='budget'),           # Budget Page
    path('analytics/', views.analytics, name='analytics'),  # Analytics Page
    path('settings/', views.settings, name='settings'),     # Settings Page
]