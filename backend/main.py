"""Compatibility entrypoint for deployments that still import backend.main."""

from backend.app import app, create_app

__all__ = ["app", "create_app"]
