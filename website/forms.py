from django import forms
from django.core.validators import validate_email
from django_recaptcha.fields import ReCaptchaField


class ContactForm(forms.Form):
    name = forms.CharField(max_length=120)
    email = forms.EmailField(validators=[validate_email])
    # Optional phone: template already guards with `{% if form.phone %}`
    phone = forms.CharField(max_length=30, required=False)
    subject = forms.CharField(max_length=150)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}))
    captcha = ReCaptchaField()
