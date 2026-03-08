#!/usr/bin/env python
"""Django 管理命令入口。"""
import os
import sys


def main():
    """执行管理命令。"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "无法导入 Django。请确认 Django 已安装，且当前 Python 环境可用。"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
