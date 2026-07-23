from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('income/', views.income, name='income'),
    path('analytics/', views.analytics, name='analytics'),
    path('settings/', views.settings, name='settings'),
    
    # 💡 Auth Routes
    path('accounts/', include('django.contrib.auth.urls')), 
    path('accounts/signup/', views.signup, name='signup'),
    path('demo/', views.demo_login, name='demo_login'),
]