#!/usr/bin/env python3
"""
Quick Status Checker — run this from ANY terminal to see what the iBank is doing.

Usage:
    python check_status.py         # Show dashboard
    python check_status.py log     # Show recent log
    python check_status.py watch   # Auto-refresh every 10 seconds
"""

import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from heartbeat import print_status_dashboard, print_recent_log, read_status


def watch_mode(interval=10):
    """Auto-refresh status every N seconds (like `watch` command)."""
    print("🔄 Watching iBank status (Ctrl+C to stop)...")
    try:
        while True:
            # Clear screen
            os.system('cls' if os.name == 'nt' else 'clear')
            print_status_dashboard()

            # Also show if next scheduled events are coming
            status = read_status()
            if status.get("status") == "IDLE":
                print("  💡 System is idle, waiting for next scheduled event.")
                print("     Schedule: 09:35, 12:00, 15:30 (full cycles)")
            elif status.get("status") == "STOPPED":
                print("  ⛔ System is STOPPED. Run 'python main.py --mode auto' to restart.")

            print(f"\n  🔄 Refreshing every {interval}s... (Ctrl+C to stop)")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped watching.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "log":
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            print_recent_log(n)
        elif cmd == "watch":
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            watch_mode(interval)
        elif cmd == "raw":
            import json
            print(json.dumps(read_status(), indent=2))
        else:
            print("Usage: python check_status.py [log|watch|raw]")
    else:
        print_status_dashboard()
