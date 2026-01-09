"""URL configuration for payouts app."""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.create_payout, name='create_payout'),
    path('<uuid:payout_id>/', views.get_payout, name='get_payout'),
]




