from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse
from website.forms import ContactForm


def contact_view(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid() and settings.USE_GMAIL:
            data = form.cleaned_data
            subject = f"[Contact] {data['subject']}"
            body = (
                f"Name: {data['name']}\n"
                f"Email: {data['email']}\n"
                f"Phone: {data.get('phone','')}\n\n"
                f"Message:\n{data['message']}"
            )

            to_emails = settings.CONTACT_FORM_TO_ADDRESS

            send_mail(
                subject=subject,
                message=body,
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=to_emails,
                fail_silently=False,
            )

            # Flash success and redirect to the same page (PRG)
            messages.success(request, "Thanks! Your message has been sent.")
            return redirect(reverse("website:contact"))
    else:
        form = ContactForm()

    return render(request, "website/contact.html", {"form": form})
