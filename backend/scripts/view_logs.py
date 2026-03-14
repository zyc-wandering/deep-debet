#!/usr/bin/env python3
"""
日志查看和分析工具

用法:
    python view_logs.py --session <session_id>     # 查看特定会话的日志
    python view_logs.py --today                    # 查看今天的所有日志
    python view_logs.py --errors                   # 查看今天的错误日志
    python view_logs.py --session <session_id> --errors  # 查看特定会话的错误
    python view_logs.py --tail 50                  # 查看最新50行日志
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def get_logs_dir() -> Path:
    """获取日志目录"""
    return Path("data/logs")


def format_log_line(line: str) -> str:
    """格式化单行日志输出"""
    try:
        data = json.loads(line)
        timestamp = data.get("timestamp", "?")
        level = data.get("level", "INFO")
        event_type = data.get("event_type", "-")
        message = data.get("message", "")
        session_id = data.get("session_id", "")[:8]  # 只显示前8个字符
        stage = data.get("stage", "")

        # 根据级别使用不同颜色
        color = {
            "DEBUG": "\033[36m",  # 青色
            "INFO": "\033[32m",   # 绿色
            "WARNING": "\033[33m", # 黄色
            "ERROR": "\033[31m",  # 红色
        }.get(level, "")
        reset = "\033[0m"

        stage_str = f"[{stage}]" if stage else ""
        session_str = f"[{session_id}]" if session_id else ""

        return f"{color}[{timestamp}] [{level:8}] {event_type:30} {session_str:10} {stage_str:12} {message}{reset}"
    except json.JSONDecodeError:
        return line.strip()


def view_session_logs(session_id: str, errors_only: bool = False):
    """查看特定会话的日志"""
    log_file = get_logs_dir() / "sessions" / f"{session_id}.log"

    if not log_file.exists():
        print(f"未找到会话日志: {log_file}")
        return

    print(f"=== 会话日志: {session_id} ===\n")

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            if errors_only and '"level":' in line and '"ERROR"' not in line:
                continue
            print(format_log_line(line))


def view_today_logs(errors_only: bool = False, tail: int = None):
    """查看今天的日志"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")

    if errors_only:
        log_file = get_logs_dir() / f"errors_{today}.log"
        print(f"=== 今日错误日志 ===\n")
    else:
        log_file = get_logs_dir() / f"debate_{today}.log"
        print(f"=== 今日辩论日志 ===\n")

    if not log_file.exists():
        print(f"未找到日志文件: {log_file}")
        return

    lines = []
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if tail:
        lines = lines[-tail:]

    for line in lines:
        print(format_log_line(line))


def analyze_session(session_id: str):
    """分析会话的执行情况"""
    log_file = get_logs_dir() / "sessions" / f"{session_id}.log"

    if not log_file.exists():
        print(f"未找到会话日志: {log_file}")
        return

    print(f"=== 会话分析: {session_id} ===\n")

    events = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
                events.append(data)
            except json.JSONDecodeError:
                continue

    # 统计信息
    stages = {}
    errors = []
    llm_calls = []

    for event in events:
        event_type = event.get("event_type", "")

        if "stage" in event and event.get("duration_sec"):
            stage = event.get("stage", "")
            stages[stage] = event.get("duration_sec", 0)

        if event.get("level") == "ERROR":
            errors.append(event)

        if event_type in ("llm_request", "llm_response"):
            llm_calls.append(event)

    print("阶段耗时:")
    for stage, duration in stages.items():
        print(f"  {stage:20} {duration:8.2f}s")

    print(f"\n错误数量: {len(errors)}")
    for error in errors:
        print(f"  - {error.get('timestamp', '?')}: {error.get('message', '')}")

    print(f"\nLLM调用数量: {len(llm_calls) // 2}")  # 请求和响应成对


def main():
    parser = argparse.ArgumentParser(description="辩论日志查看工具")
    parser.add_argument("--session", help="查看特定会话的日志")
    parser.add_argument("--today", action="store_true", help="查看今天的日志")
    parser.add_argument("--errors", action="store_true", help="只显示错误")
    parser.add_argument("--tail", type=int, help="显示最后N行")
    parser.add_argument("--analyze", help="分析特定会话")

    args = parser.parse_args()

    if args.session:
        view_session_logs(args.session, errors_only=args.errors)
    elif args.analyze:
        analyze_session(args.analyze)
    else:
        view_today_logs(errors_only=args.errors, tail=args.tail)


if __name__ == "__main__":
    main()
