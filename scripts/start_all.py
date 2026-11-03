"""
一键启动：PostgreSQL 服务 + FastAPI 后端 + Vite 前端 + 自动打开浏览器
用法: python scripts/start_all.py
"""
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY312 = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
PY = PY312 if os.path.exists(PY312) else sys.executable


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)


def port_alive(url, timeout=2):
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False


def main():
    print("[1/4] 检查 PostgreSQL 服务 (ynmine-pg15) ...")
    st = run('powershell -Command "(Get-Service ynmine-pg15 -ErrorAction SilentlyContinue).Status"')
    if "Running" not in st.stdout:
        run("powershell -Command \"Start-Service ynmine-pg15\"")
        time.sleep(3)
    print("      " + (run('powershell -Command "(Get-Service ynmine-pg15).Status"').stdout.strip() or "未知"))

    if port_alive("http://localhost:8001/api/v1/health"):
        print("[2/4] 后端已在运行，跳过")
    else:
        print("[2/4] 启动 FastAPI 后端 (8001) ...")
        subprocess.Popen([PY, "-m", "uvicorn", "main:app", "--port", "8001"],
                         cwd=os.path.join(ROOT, "backend"),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(20):
            if port_alive("http://localhost:8001/api/v1/health"):
                break
            time.sleep(0.5)

    if port_alive("http://localhost:5174/"):
        print("[3/4] 前端已在运行，跳过")
    else:
        print("[3/4] 启动前端 Vite (5174) ...")
        subprocess.Popen("npm run dev", cwd=os.path.join(ROOT, "frontend"), shell=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            if port_alive("http://localhost:5174/"):
                break
            time.sleep(0.5)

    print("[4/4] 打开浏览器 http://localhost:5174")
    webbrowser.open("http://localhost:5174/")
    print("完成。后端文档: http://localhost:8001/docs")


if __name__ == "__main__":
    main()
