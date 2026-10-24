def lockout_username(request, credentials: dict | None) -> str:
    """The name django-axes counts failed sign-ins against: the email as
    typed, stripped and lowercased, so "A@x.com" and "a@x.com" share one
    count. Matches how User stores and looks up emails."""
    if credentials and credentials.get("username"):
        raw = credentials["username"]
    else:
        raw = request.POST.get("username", "") if request is not None else ""
    return str(raw).strip().lower()
