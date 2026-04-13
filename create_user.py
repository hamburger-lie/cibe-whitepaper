#!/usr/bin/env python3
"""
CIBE 白皮书系统 — 管理员创建用户脚本
用法: python create_user.py
"""

import os
import sys
import sqlite3
from getpass import getpass

try:
    from passlib.hash import bcrypt
except ImportError:
    print("错误: 请先安装依赖  pip install passlib[bcrypt]")
    sys.exit(1)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.db")


def create_user():
    # 初始化数据库（如果不存在）
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)
    conn.commit()

    print("=" * 40)
    print("  CIBE 白皮书系统 — 创建用户")
    print("=" * 40)

    username = input("请输入用户名: ").strip()
    if not username or len(username) < 2:
        print("错误: 用户名至少 2 个字符")
        return

    # 检查是否已存在
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        print(f"错误: 用户名 '{username}' 已存在")
        conn.close()
        return

    password = getpass("请输入密码（至少6位，输入时不显示）: ")
    if len(password) < 6:
        print("错误: 密码至少 6 个字符")
        return

    password_confirm = getpass("请再次输入密码: ")
    if password != password_confirm:
        print("错误: 两次输入的密码不一致")
        return

    password_hash = bcrypt.hash(password)
    conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                  (username, password_hash))
    conn.commit()
    conn.close()

    print(f"\n用户 '{username}' 创建成功！")


if __name__ == "__main__":
    create_user()
