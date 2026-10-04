"""Staff surface for the membership catalogue: tiers and the perks they list.

Until now this lived only in /admin/, which meant changing a price or
retiring a tier needed a second login and a different mental model. The
catalogue is small and rarely edited, so these views are deliberately plain
— the one piece of real behaviour is that a tier with terms against it
cannot be deleted, only retired, because those terms are revenue records.
"""

import json

from audience.models import MembershipBenefit, MembershipTier
from django.db.models import Count, ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View

from .forms import MembershipBenefitForm, MembershipTierForm
from .mixins import StaffRequiredMixin


def catalogue_context() -> dict:
    """Both lists, with the counts the tables print.

    `term_count` decides whether Delete is offered at all, so it is
    annotated rather than counted per row in the template. The annotations
    make these GROUP BY queries, from which Django drops `Meta.ordering`,
    so each list restates its model's Meta.ordering.
    """
    return {
        "tiers": MembershipTier.objects.annotate(
            term_count=Count("terms", distinct=True)
        )
        .order_by("sort_order", "price")
        .prefetch_related("benefits"),
        "benefits": MembershipBenefit.objects.annotate(
            tier_count=Count("membershiptier", distinct=True)
        ).order_by("sort_order", "name"),
    }


class TierListView(StaffRequiredMixin, View):
    def get(self, request):
        return render(request, "dashboard/tiers.html", catalogue_context())


def _oob(html: str, container_id: str) -> str:
    return html.replace(
        f'<div id="{container_id}">',
        f'<div id="{container_id}" hx-swap-oob="true">',
        1,
    )


def _catalogue_response(request, toast_message, kind="success", close=True):
    """OOB-swap both catalogue lists, close the drawer, and toast.

    Both lists swap on every change, not just the one that was edited:
    renaming a benefit changes the perk column of every tier that carries
    it, and retiring a tier changes the benefit rows' tier counts.
    """
    ctx = catalogue_context()
    html = _oob(
        render(request, "dashboard/_tier_list.html", ctx).content.decode(),
        "tier-list",
    ) + _oob(
        render(request, "dashboard/_benefit_list.html", ctx).content.decode(),
        "benefit-list",
    )
    resp = HttpResponse(html)
    triggers: dict = {"dashboard-toast": {"kind": kind, "message": toast_message}}
    if close:
        triggers["close-drawer"] = True
    resp["HX-Trigger"] = json.dumps(triggers)
    return resp


def _render_tier_form(request, form, action_url, submit_label):
    return render(
        request,
        "dashboard/_tier_form.html",
        {"form": form, "form_action": action_url, "submit_label": submit_label},
    )


class TierCreateView(StaffRequiredMixin, View):
    def get(self, request):
        return _render_tier_form(
            request,
            MembershipTierForm(),
            reverse("dashboard:tier_create"),
            "Create Tier",
        )

    def post(self, request):
        form = MembershipTierForm(request.POST)
        if form.is_valid():
            form.save()
            return _catalogue_response(request, "Tier created")
        return _render_tier_form(
            request, form, reverse("dashboard:tier_create"), "Create Tier"
        )


class TierEditView(StaffRequiredMixin, View):
    def get(self, request, pk):
        tier = get_object_or_404(MembershipTier, pk=pk)
        return _render_tier_form(
            request,
            MembershipTierForm(instance=tier),
            reverse("dashboard:tier_edit", args=[pk]),
            "Save Changes",
        )

    def post(self, request, pk):
        tier = get_object_or_404(MembershipTier, pk=pk)
        form = MembershipTierForm(request.POST, instance=tier)
        if form.is_valid():
            form.save()
            return _catalogue_response(request, "Tier updated")
        return _render_tier_form(
            request, form, reverse("dashboard:tier_edit", args=[pk]), "Save Changes"
        )


class TierListingView(StaffRequiredMixin, View):
    """Retire or restore a tier — the supported alternative to deleting one.

    A retired tier drops off the public membership page and out of the tier
    dropdown for new terms, while every term already pointing at it keeps
    working and keeps its price history.
    """

    def post(self, request, pk):
        tier = get_object_or_404(MembershipTier, pk=pk)
        if not tier.show_on_membership_page and not tier.checkout_url:
            # Restoring would list a card whose Join button goes nowhere —
            # the rule MembershipTier.clean() enforces on the forms.
            return _catalogue_response(
                request,
                f'Add a Square payment link to "{tier.name}" before restoring it.',
                kind="error",
                close=False,
            )
        tier.show_on_membership_page = not tier.show_on_membership_page
        # updated_at too: auto_now only reaches the columns being written,
        # and retiring or restoring a tier changes the public page.
        tier.save(update_fields=["show_on_membership_page", "updated_at"])
        verb = "restored" if tier.show_on_membership_page else "retired"
        return _catalogue_response(request, f"{tier.name} {verb}", close=False)


class TierDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        tier = get_object_or_404(MembershipTier, pk=pk)
        name = tier.name
        try:
            tier.delete()
        except ProtectedError:
            # MembershipTerm.tier is PROTECT: a tier someone bought is part
            # of a revenue record, so the answer is to retire it.
            count = tier.terms.count()
            return _catalogue_response(
                request,
                f'Can\'t delete "{name}" — {count} membership term'
                f'{"" if count == 1 else "s"} point at it. Retire it instead.',
                kind="error",
                close=False,
            )
        return _catalogue_response(request, "Tier deleted")


def _render_benefit_form(request, form, action_url, submit_label):
    return render(
        request,
        "dashboard/_benefit_form.html",
        {"form": form, "form_action": action_url, "submit_label": submit_label},
    )


class BenefitCreateView(StaffRequiredMixin, View):
    def get(self, request):
        return _render_benefit_form(
            request,
            MembershipBenefitForm(),
            reverse("dashboard:benefit_create"),
            "Create Perk",
        )

    def post(self, request):
        form = MembershipBenefitForm(request.POST)
        if form.is_valid():
            form.save()
            return _catalogue_response(request, "Perk created")
        return _render_benefit_form(
            request, form, reverse("dashboard:benefit_create"), "Create Perk"
        )


class BenefitEditView(StaffRequiredMixin, View):
    def get(self, request, pk):
        benefit = get_object_or_404(MembershipBenefit, pk=pk)
        return _render_benefit_form(
            request,
            MembershipBenefitForm(instance=benefit),
            reverse("dashboard:benefit_edit", args=[pk]),
            "Save Changes",
        )

    def post(self, request, pk):
        benefit = get_object_or_404(MembershipBenefit, pk=pk)
        form = MembershipBenefitForm(request.POST, instance=benefit)
        if form.is_valid():
            form.save()
            return _catalogue_response(request, "Perk updated")
        return _render_benefit_form(
            request,
            form,
            reverse("dashboard:benefit_edit", args=[pk]),
            "Save Changes",
        )


class BenefitDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        # benefits is a ManyToMany, so this cannot raise ProtectedError —
        # deleting a perk just drops it from the tiers that listed it. The
        # confirm dialog says how many, which is the whole safeguard.
        get_object_or_404(MembershipBenefit, pk=pk).delete()
        return _catalogue_response(request, "Perk deleted")
