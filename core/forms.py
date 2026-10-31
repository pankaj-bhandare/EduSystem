from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import User


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "username", "class": "form-control mb-2", "placeholder": "Email"}))
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "class": "form-control mb-3", "placeholder": "Password"}))
    error_messages = {
        "invalid_login": "Invalid email or password.",
        "inactive": "This account has been deactivated. Please contact an administrator.",
    }

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()

    def confirm_login_allowed(self, user):
        # ModelBackend already refuses inactive users; reproduce login.php's friendlier message
        if not user.is_active:
            raise forms.ValidationError(self.error_messages["inactive"], code="inactive")

    def clean(self):
        # Show the 'deactivated' message only when the password was right (as in the PHP).
        email = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if email and password:
            user = User.objects.filter(email=email).first()
            if user and not user.is_active and user.check_password(password):
                raise forms.ValidationError(self.error_messages["inactive"], code="inactive")
        return super().clean()


class StudentRegisterForm(forms.Form):
    """register.php + signup.php (duplicates) merged. Public sign-up is students only."""
    name = forms.CharField(min_length=3, max_length=150, widget=forms.TextInput(attrs={"class": "form-control mb-2", "placeholder": "Full name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control mb-2", "placeholder": "Email"}))
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"class": "form-control mb-2", "placeholder": "Password (12+ characters)"}))
    confirm = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"class": "form-control mb-2", "placeholder": "Confirm password"}))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email already exists!")
        return email

    def clean(self):
        data = super().clean()
        if data.get("password") and data["password"] != data.get("confirm"):
            self.add_error("confirm", "Passwords do not match!")
        elif data.get("password"):
            password_validation.validate_password(data["password"])
        return data

    def save(self):
        d = self.cleaned_data
        return User.objects.create_user(email=d["email"], password=d["password"], name=d["name"], role=User.Role.STUDENT)


class ForgotForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control mb-3", "placeholder": "Enter your email"}))


class OTPForm(forms.Form):
    otp = forms.RegexField(r"^\d{6}$", error_messages={"invalid": "Invalid OTP format!"},
                           widget=forms.TextInput(attrs={"class": "form-control mb-3", "placeholder": "Enter 6-digit OTP", "inputmode": "numeric", "autocomplete": "one-time-code"}))


class ResetForm(forms.Form):
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"class": "form-control mb-3", "placeholder": "New password"}))
    confirm = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"class": "form-control mb-3", "placeholder": "Confirm new password"}))

    def clean(self):
        data = super().clean()
        if data.get("password"):
            if data["password"] != data.get("confirm"):
                self.add_error("confirm", "Passwords do not match.")
            else:
                password_validation.validate_password(data["password"])
        return data
