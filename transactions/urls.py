from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('income/', views.income, name='income'),
    path('analytics/', views.analytics, name='analytics'),
    path('budgets/', views.budgets, name='budgets'),
    path('settings/', views.settings, name='settings'),
    path('export/transactions/', views.export_transactions_csv, name='export_transactions_csv'),
    path('export/income/', views.export_income_csv, name='export_income_csv'),
    
    # 💡 Auth Routes
    path('accounts/', include('django.contrib.auth.urls')), 
    path('accounts/signup/', views.signup, name='signup'),
]