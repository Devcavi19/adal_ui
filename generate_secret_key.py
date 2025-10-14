#!/usr/bin/env python3
"""
Generate a secure SECRET_KEY for Flask application
Run this and copy the output to your Railway environment variables
"""

import secrets

print("=" * 60)
print("🔐 FLASK SECRET KEY GENERATOR")
print("=" * 60)
print()
print("Copy this SECRET_KEY to your Railway environment variables:")
print()
print(secrets.token_hex(32))
print()
print("=" * 60)
