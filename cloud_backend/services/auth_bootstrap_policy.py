"""Dependency-free first-user bootstrap policy.

Known default accounts are intentionally not supported.  An empty Users
collection requires explicit one-time bootstrap credentials.
"""

from __future__ import annotations

from typing import Any


def resolve_bootstrap_users(username: str, password: str) -> tuple[list[dict[str, Any]], str]:
    username = str(username or "").strip()
    password = str(password or "")
    if bool(username) != bool(password):
        raise RuntimeError(
            "BOOTSTRAP_ADMIN_USERNAME và BOOTSTRAP_ADMIN_PASSWORD phải được cấu hình cùng nhau."
        )
    if not username:
        raise RuntimeError(
            "Users collection đang trống. Hãy cấu hình BOOTSTRAP_ADMIN_USERNAME và "
            "BOOTSTRAP_ADMIN_PASSWORD cho lần khởi động đầu tiên; không tự tạo tài khoản mặc định."
        )
    if len(password) < 12:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD cần tối thiểu 12 ký tự.")
    return ([{"username": username, "password": password, "role": "admin"}], "explicit bootstrap admin")
