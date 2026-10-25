"""Evaluate settings.py afresh, as production would see it."""

import importlib.util
import os
import sys
from pathlib import Path
from unittest import mock

SETTINGS = Path(__file__).resolve().parents[1] / "settings.py"


def load_settings(argv=("gunicorn",), **env):
    """settings.py under this environment and command line. The default argv
    has no "test" in it, so the module's TESTING switches are off."""
    base = {"SECRET_KEY": "test", "ALLOWED_HOSTS": "www.fortkentcinema.com"}
    with (
        mock.patch.dict(os.environ, {**base, **env}),
        mock.patch.object(sys, "argv", list(argv)),
    ):
        spec = importlib.util.spec_from_file_location("fkc_settings_probe", SETTINGS)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module
