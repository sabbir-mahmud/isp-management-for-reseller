"""Sign-in behaviour, including the brute-force throttle."""

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from apps.users.models import Profile, Role


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_valid_credentials_sign_in(client, make_user):
    make_user("alice", Role.OWNER, password="rightpass123")
    response = client.post(reverse("login"), {"username": "alice", "password": "rightpass123"})
    assert response.status_code == 302
    assert response.wsgi_request.user.is_authenticated


def test_bad_credentials_re_render_the_form_with_an_error(client, make_user):
    make_user("bob", Role.OWNER, password="rightpass123")
    response = client.post(reverse("login"), {"username": "bob", "password": "wrong"})
    assert response.status_code == 200
    assert response.context["form"].errors


@override_settings(LOGIN_FAILURE_LIMIT=3)
def test_repeated_failures_lock_the_account_out(client, make_user):
    make_user("carol", Role.OWNER, password="rightpass123")
    for _ in range(3):
        client.post(reverse("login"), {"username": "carol", "password": "wrong"})

    # Even the correct password is refused while the lockout holds.
    response = client.post(reverse("login"), {"username": "carol", "password": "rightpass123"})
    assert response.status_code == 200
    assert not response.wsgi_request.user.is_authenticated
    assert "Too many failed attempts" in response.content.decode()


@override_settings(LOGIN_FAILURE_LIMIT=3)
def test_a_successful_sign_in_clears_the_counter(client, make_user):
    make_user("dave", Role.OWNER, password="rightpass123")
    client.post(reverse("login"), {"username": "dave", "password": "wrong"})
    client.post(reverse("login"), {"username": "dave", "password": "rightpass123"})
    client.logout()

    for _ in range(2):
        client.post(reverse("login"), {"username": "dave", "password": "wrong"})
    response = client.post(reverse("login"), {"username": "dave", "password": "rightpass123"})
    assert response.status_code == 302


def test_logout_requires_post(client, make_user):
    user = make_user("erin", Role.OWNER)
    client.force_login(user)
    assert client.get(reverse("logout")).status_code == 405
    assert client.post(reverse("logout")).status_code == 302


def test_login_does_not_follow_an_off_site_next(client, make_user):
    make_user("frank", Role.OWNER, password="rightpass123")
    response = client.post(
        f"{reverse('login')}?next=https://evil.example.com/steal",
        {"username": "frank", "password": "rightpass123"},
    )
    assert response.status_code == 302
    assert "evil.example.com" not in response["Location"]


def test_a_new_superuser_becomes_an_owner(db):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_superuser("root", "root@example.com", "rootpass123")
    assert user.profile.role == Role.OWNER


def test_a_new_plain_user_starts_at_the_least_privilege(db):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user("plain", password="plainpass123")
    assert Profile.objects.get(user=user).role == Role.SUPPORT
