"""测试 console.clear() 在 VM 终端上的行为"""
import sys
sys.path.insert(0, "/root/devops-agent/src")

from rich.console import Console

console = Console()
print(f"is_terminal: {console.is_terminal}")
print(f"color_system: {console.color_system}")
print(f"legacy_windows: {console.legacy_windows}")

console.print("[red]=== 清屏前 ===[/red]")
console.print("Line 1: 这行应该在清屏后消失")
console.print("Line 2: 这行也应该消失")
console.clear()
console.print("[green]=== 清屏后 ===[/green]")
console.print("如果只看到这两行，说明 clear() 生效")
