from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.ThrottledLoginView.as_view(), name="login"),
    path("logout/", views.SignOutView.as_view(), name="logout"),
    path("password/", views.ChangePasswordView.as_view(), name="password_change"),
    path("password/done/", views.PasswordChangedView.as_view(), name="password_change_done"),
    path("staff/", views.StaffListView.as_view(), name="staff_list"),
    path("staff/add/", views.StaffCreateView.as_view(), name="staff_add"),
    path("staff/<int:pk>/edit/", views.StaffUpdateView.as_view(), name="staff_edit"),
]
