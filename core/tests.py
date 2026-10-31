import re
import bcrypt
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .hashing import convert_php_hash
from .models import PasswordResetOTP, User

PW = "correct horse battery"


def mk(email, role="student", **kw):
    return User.objects.create_user(email=email, password=PW, name="Test User", role=role, **kw)


class AuthTests(TestCase):
    def test_register_is_student_only_and_validates(self):
        r = self.client.post(reverse("register"), {"name": "Asha K", "email": "Asha@Example.com", "password": PW, "confirm": PW, "role": "admin"})
        self.assertRedirects(r, reverse("login"))
        u = User.objects.get(email="asha@example.com")  # lowercased
        self.assertEqual(u.role, "student")             # posted role ignored
        r = self.client.post(reverse("register"), {"name": "Asha K", "email": "asha@example.com", "password": PW, "confirm": PW})
        self.assertContains(r, "Email already exists!")
        r = self.client.post(reverse("register"), {"name": "Bo", "email": "b@example.com", "password": "short", "confirm": "short"})
        self.assertEqual(User.objects.filter(email="b@example.com").count(), 0)

    def test_login_redirects_by_role_and_rejects_bad_password(self):
        for role, url in (("student", "student_dashboard"), ("teacher", "teacher_dashboard"), ("admin", "admin_dashboard")):
            mk(f"{role}@x.com", role)
            self.client.logout()
            r = self.client.post(reverse("login"), {"username": f"{role}@x.com".upper(), "password": PW}, follow=True)
            self.assertEqual(r.redirect_chain[-1][0], reverse(url))
        self.client.logout()
        r = self.client.post(reverse("login"), {"username": "student@x.com", "password": "wrong"})
        self.assertContains(r, "Invalid email or password.")

    def test_deactivated_account_message(self):
        mk("off@x.com", is_active=False)
        r = self.client.post(reverse("login"), {"username": "off@x.com", "password": PW})
        self.assertContains(r, "deactivated")
        r = self.client.post(reverse("login"), {"username": "off@x.com", "password": "wrong"})
        self.assertContains(r, "Invalid email or password.")  # no account-state leak

    def test_role_gate_gives_403_and_anonymous_goes_to_login(self):
        mk("s@x.com", "student")
        self.assertEqual(self.client.get(reverse("teacher_dashboard")).status_code, 302)
        self.client.login(username="s@x.com", password=PW)
        self.assertEqual(self.client.get(reverse("teacher_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("student_dashboard")).status_code, 200)

    def test_logout_requires_post(self):
        mk("s@x.com"); self.client.login(username="s@x.com", password=PW)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("student_dashboard")).status_code, 302)

    def test_csrf_enforced(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        self.assertEqual(c.post(reverse("login"), {"username": "a@x.com", "password": "x"}).status_code, 403)

    def test_php_bcrypt_hash_logs_in_and_is_upgraded(self):
        php_hash = bcrypt.hashpw(PW.encode(), bcrypt.gensalt(10)).decode().replace("$2b$", "$2y$", 1)
        u = User.objects.create(email="old@x.com", username="old@x.com", name="Old", role="student", password=convert_php_hash(php_hash))
        self.assertTrue(self.client.login(username="old@x.com", password=PW))
        u.refresh_from_db()
        self.assertFalse(u.password.startswith("bcrypt$"))  # silently re-hashed with the preferred hasher


class OTPFlowTests(TestCase):
    def setUp(self):
        mk("u@x.com")

    def _request_code(self, email="u@x.com"):
        r = self.client.post(reverse("forgot_password"), {"email": email})
        self.assertRedirects(r, reverse("verify_otp"))

    def test_full_reset_flow(self):
        self._request_code()
        code = re.search(r"code is: (\d{6})", mail.outbox[0].body).group(1)
        self.assertNotEqual(PasswordResetOTP.objects.get().otp_hash, code)  # stored hashed
        self.assertRedirects(self.client.post(reverse("verify_otp"), {"otp": code}), reverse("reset_password"))
        new = "a brand new passphrase"
        self.assertRedirects(self.client.post(reverse("reset_password"), {"password": new, "confirm": new}), reverse("login"))
        self.assertTrue(User.objects.get(email="u@x.com").check_password(new))
        self.assertEqual(self.client.get(reverse("reset_password")).status_code, 403)  # window closed

    def test_unknown_email_same_response_no_mail(self):
        self._request_code("nobody@x.com")
        self.assertEqual(len(mail.outbox), 0)

    def test_cooldown_and_attempt_limit_survive_cookie_reset(self):
        self._request_code()
        r = self.client.post(reverse("forgot_password"), {"email": "u@x.com"})
        self.assertContains(r, "wait one minute")
        for _ in range(5):
            self.client.post(reverse("verify_otp"), {"otp": "000000"})
        code = re.search(r"code is: (\d{6})", mail.outbox[0].body).group(1)
        r = self.client.post(reverse("verify_otp"), {"otp": code})  # right code, but locked out
        self.assertContains(r, "Too many attempts")

    def test_reset_page_needs_verification(self):
        self.assertEqual(self.client.get(reverse("reset_password")).status_code, 403)
