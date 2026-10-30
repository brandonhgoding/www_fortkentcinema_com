"""The public unsubscribe page, reached from the email's footer link and from
mail clients' List-Unsubscribe buttons."""

from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from audience.models import Subscriber, SubscriberStatus
from newsletter.links import mask_email


@method_decorator(csrf_exempt, name="dispatch")
class UnsubscribeView(View):
    """GET asks, POST unsubscribes. Both end on a 200 page.

    The token in the URL is the authorisation, as with the confirm link, so
    the view is csrf_exempt: a mail client's one-click POST carries no
    token. An unknown or already-unsubscribed token shows the done page
    too, so the link never reveals whether an address is on the list.
    """

    def get(self, request, token):
        return self._respond(request, token, leave=False)

    def post(self, request, token):
        return self._respond(request, token, leave=True)

    def _respond(self, request, token, leave):
        ctx = {"state": "done"}
        subscriber = Subscriber.objects.filter(unsubscribe_token=token).first()
        active = (
            subscriber is not None
            and subscriber.status != SubscriberStatus.UNSUBSCRIBED
        )
        if active:
            if leave:
                subscriber.unsubscribe()
            else:
                ctx = {"state": "ask", "masked": mask_email(subscriber.email)}
        response = render(request, "newsletter/unsubscribe.html", ctx)
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response
