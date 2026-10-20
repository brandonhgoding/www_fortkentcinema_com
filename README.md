API FILES GO HERE
Does this effect the othe

# api_fortkentcinema_com
##


https://django-tailwind.readthedocs.io/en/latest/installation.html


npx @tailwindcss/cli -i theme/static/src/input.css -o theme/static/src/output.css --watch

## Python

The site runs on Python 3.12 (the black and mypy targets in `pyproject.toml`
and `mypy.ini`); 3.11 is the floor, because `boxoffice.gateway.parse_timestamp`
relies on `fromisoformat` reading Square's trailing `Z`. The deploy's
interpreter must match; `.python-version` is gitignored here, so set it locally.

## Online tickets

Online ticket sales (the `tickets` app) need one nightly job beside the Square
sales pull (`python manage.py pull_square_sales`): `python manage.py
expire_ticket_orders`, which asks Square about every order still pending past the
hold and expires the unpaid ones (an order Square could not be asked about stays
pending for the next run). Set `TICKETS_BASE_URL` (for example
`https://www.fortkentcinema.com`) so Square's checkout returns buyers to this
site; when it is empty the scheme and host of `SQUARE_WEBHOOK_URL` are used. The
confirmation page and ticket email draw a QR code with the `qrcode` package,
which is in `requirements.txt`.
