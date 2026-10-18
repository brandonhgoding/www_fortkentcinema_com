"""Placeholders so the URL names reverse; Task 9 replaces them."""

from django.http import Http404


def buy(request, pk):
    raise Http404


def order(request, token):
    raise Http404
