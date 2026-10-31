import secrets
import time
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.views import LoginView
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.utils import timezone
from django.contrib.auth.decorators import login_required

from .forms import ForgotForm, LoginForm, OTPForm, ResetForm, StudentRegisterForm
from .models import PasswordResetOTP, User

OTP_TTL = timedelta(minutes=5)
OTP_MAX_ATTEMPTS = 5
OTP_COOLDOWN_SECONDS = 60
RESET_WINDOW_SECONDS = 600
HOME_BY_ROLE = {"admin": "admin_dashboard", "teacher": "teacher_dashboard", "student": "student_dashboard"}


class RoleLoginView(LoginView):
    form_class = LoginForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or "/"  # '/' sends each role to its own dashboard


@login_required
def home(request):
    return redirect(HOME_BY_ROLE[request.user.role])


def register(request):
    form = StudentRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Registration successful! You can log in now.")
        return redirect("login")
    return render(request, "registration/register.html", {"form": form})


# ---- OTP password reset (forgot_password.php / verify_otp.php / reset_password.php) ----
def forgot_password(request):
    form = ForgotForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        last = request.session.get("otp_last_sent", 0)
        if time.time() - last < OTP_COOLDOWN_SECONDS:
            form.add_error(None, "Please wait one minute before requesting another code.")
        else:
            email = form.cleaned_data["email"].strip().lower()
            request.session["otp_last_sent"] = time.time()
            request.session["otp_email"] = email  # same flow for existing and unknown emails
            user = User.objects.filter(email=email, is_active=True).first()
            if user:
                code = f"{secrets.randbelow(900000) + 100000}"
                PasswordResetOTP.objects.filter(email=email).delete()  # one active code per account
                PasswordResetOTP.objects.create(email=email, otp_hash=make_password(code))
                send_mail("Edu System password reset code",
                          f"Your password reset code is: {code}\n\nThis code expires in five minutes. "
                          "If you did not request this, you can ignore this email.",
                          None, [email], fail_silently=True)
            return redirect("verify_otp")
    return render(request, "registration/forgot_password.html", {"form": form})


def verify_otp(request):
    email = request.session.get("otp_email")
    if not email:
        return redirect("forgot_password")
    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        record = PasswordResetOTP.objects.filter(email=email, created_at__gte=timezone.now() - OTP_TTL).order_by("-created_at").first()
        if record and record.attempts >= OTP_MAX_ATTEMPTS:
            form.add_error(None, "Too many attempts. Request a new code.")
        elif record and check_password(form.cleaned_data["otp"], record.otp_hash):
            PasswordResetOTP.objects.filter(email=email).delete()  # single use
            request.session.cycle_key()
            request.session["otp_verified_at"] = time.time()
            return redirect("reset_password")
        else:
            if record:
                PasswordResetOTP.objects.filter(pk=record.pk).update(attempts=record.attempts + 1)
            form.add_error(None, "Invalid or expired OTP!")
    return render(request, "registration/verify_otp.html", {"form": form})


def reset_password(request):
    email = request.session.get("otp_email")
    verified_at = request.session.get("otp_verified_at")
    if not email or not verified_at or time.time() - verified_at > RESET_WINDOW_SECONDS:
        for k in ("otp_email", "otp_verified_at"):
            request.session.pop(k, None)
        return render(request, "registration/reset_expired.html", status=403)
    form = ResetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.filter(email=email, is_active=True).first()
        if user:
            user.set_password(form.cleaned_data["password"])
            user.save(update_fields=["password"])
        for k in ("otp_email", "otp_verified_at"):
            request.session.pop(k, None)
        request.session.cycle_key()
        messages.success(request, "Password updated successfully! Log in now.")
        return redirect("login")
    return render(request, "registration/reset_password.html", {"form": form})
