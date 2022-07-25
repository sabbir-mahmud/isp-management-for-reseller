from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('months/', views.months, name='months'),
    path('months_add/', views.MonthAddView.as_view(), name='Month-add'),
    path('months/update/<str:pk>',
         views.MonthUpdateView.as_view(), name='Month-Update'),
    path('months/delete/<str:pk>', views.MonthDelete.as_view(), name='Month-Del'),
    path('years/', views.yearView, name='years'),
    path('years/add', views.YearAddView.as_view(), name='years-add'),
    path('years/update/<str:pk>',
         views.YearUpdateView.as_view(), name='years-update'),
    path('years/delete/<str:pk>',
         views.YearDeleteView.as_view(), name='years-delete'),
    path('invests/', views.investView, name='invests'),
    path('invests/add', views.InvestAddView.as_view(), name='invests-add'),
    path('invests/update/<str:pk>',
         views.InvestUpdateView.as_view(), name='invests-update'),
    path('invests/delete/<str:pk>',
         views.InvestDeleteView.as_view(), name='invests-delete'),
    path('earnings/', views.earningView, name='earnings'),
    path('earnings/add', views.EarningAddView.as_view(), name='earnings-add'),
    path('earnings/update/<str:pk>',
         views.EarningUpdateView.as_view(), name='earnings-update'),
    path('earnings/delete/<str:pk>',
         views.EarningDeleteView.as_view(), name='earnings-delete'),
    path('commission/', views.commissionView, name='commission')
]
