"""Thin re-export so ingestion has one import surface.

The real logic lives in pdf_parser.parse_email; this keeps the package API stable
if we later add .msg or API-based ingestion (Gmail/Outlook) without touching callers.
"""
from __future__ import annotations

from .pdf_parser import parse_email

__all__ = ["parse_email"]
