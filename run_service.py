#!/usr/bin/env python3
"""
PCBA 知识图谱与学习评价系统 - 一键服务管理脚本

功能：
- start: 一键启动所有服务（Neo4j + FastAPI）
- stop: 一键停止所有服务
- status: 检查服务运行状态

优先适配 Windows 系统，同时兼容 Linux/Mac
"""

import os
import sys
import subprocess
import time
import socket
import platform
import psutil
from colorama import Fore, Style, init
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 初始化 colorama
init(autoreset=True)

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# 虚拟环境路径
VENV_PATH = os.path.join(PROJECT_ROOT, '.venv')
# 主脚本路径
MAIN_SCRIPT = os.path.join(PROJECT_ROOT, 'main.py')
# PID 文件路径
PID_FILE = os.path.join(PROJECT_ROOT, 'service.pid')
# 日志文件路径
LOG_FILE = os.path.join(PROJECT_ROOT, 'service.log')
# Neo4j 实例路径
NEO4J_INSTANCE_PATH = os.getenv('NEO4J_INSTANCE_PATH', '')

# 必要的依赖包
REQUIRED_PACKAGES = [
    'fastapi',
    'uvicorn',
    'neo4j',
    'pdfplumber',
    'dashscope',
    'python-dotenv',
    'python-multipart',
    'httpx',
    'colorama',
    'psutil'
]

def print_success(message):
    """打印成功信息"""
    print(f"{Fore.GREEN}[SUCCESS] {message}{Style.RESET_ALL}")

def print_warning(message):
    """打印警告信息"""
    print(f"{Fore.YELLOW}[WARNING] {message}{Style.RESET_ALL}")

def print_error(message):
    """打印错误信息"""
    print(f"{Fore.RED}[ERROR] {message}{Style.RESET_ALL}")

def print_info(message):
    """打印信息"""
    print(f"{Fore.CYAN}[INFO] {message}{Style.RESET_ALL}")

def check_python_version():
    """检查 Python 版本"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print_error(f"Python 版本过低，需要 3.8 或更高版本，当前版本: {version.major}.{version.minor}.{version.micro}")
        return False
    print_info(f"Python 版本: {version.major}.{version.minor}.{version.micro}")
    return True

def check_packages():
    """检查必要的依赖包"""
    try:
        # 简化检查，直接尝试导入关键包
        required_imports = {
            'fastapi': 'fastapi',
            'uvicorn': 'uvicorn',
            'neo4j': 'neo4j',
            'pdfplumber': 'pdfplumber',
            'dashscope': 'dashscope',
            'dotenv': 'dotenv',
            'multipart': 'python_multipart'
        }
        
        missing_packages = []
        for pkg_name, import_name in required_imports.items():
            try:
                __import__(import_name)
            except ImportError:
                missing_packages.append(pkg_name)
        
        if missing_packages:
            print_warning(f"缺少以下依赖包: {', '.join(missing_packages)}")
            print_warning("请运行: pip install -r requirements.txt")
            return False
        print_info("所有必要的依赖包已安装")
        return True
    except Exception as e:
        print_error(f"检查依赖包时出错: {str(e)}")
        return False

def is_port_in_use(port):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def wait_for_port(port, timeout=30):
    """等待端口就绪"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(1)
    return False

def start_neo4j():
    """启动 Neo4j 服务"""
    system = platform.system()
    
    # 检查 Neo4j 是否已运行
    if is_port_in_use(7687):
        print_info("Neo4j 服务已经在运行")
        return True
    
    print_info("启动 Neo4j 服务...")
    
    try:
        # 首先尝试使用 NEO4J_INSTANCE_PATH
        if NEO4J_INSTANCE_PATH and os.path.exists(NEO4J_INSTANCE_PATH):
            print_info(f"使用指定的 Neo4j 实例路径: {NEO4J_INSTANCE_PATH}")
            # 构建 neo4j-admin 命令路径
            if system == 'Windows':
                neo4j_admin_path = os.path.join(NEO4J_INSTANCE_PATH, 'bin', 'neo4j-admin.bat')
            else:
                neo4j_admin_path = os.path.join(NEO4J_INSTANCE_PATH, 'bin', 'neo4j-admin')
            
            if os.path.exists(neo4j_admin_path):
                # 准备日志文件
                with open(LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 启动 Neo4j 服务...\n")
                
                # 启动 Neo4j
                cmd = [neo4j_admin_path, 'server', 'console']
                # 打开日志文件用于写入
                log_file = open(LOG_FILE, 'a', encoding='utf-8')
                # 在后台运行
                process = subprocess.Popen(
                    cmd,
                    cwd=NEO4J_INSTANCE_PATH,
                    stdout=log_file,
                    stderr=log_file
                )
                print_success(f"Neo4j 服务已启动 (使用实例路径: {NEO4J_INSTANCE_PATH})")
                print_info(f"Neo4j 日志已记录到: {LOG_FILE}")
            else:
                print_error(f"未找到 neo4j-admin 命令: {neo4j_admin_path}")
                return False
        else:
            # 尝试使用系统命令
            if system == 'Windows':
                # 尝试使用 net start 命令
                try:
                    subprocess.run(['net', 'start', 'neo4j'], check=True, capture_output=True, text=True)
                    print_success("Neo4j 服务已启动")
                except subprocess.CalledProcessError:
                    # 尝试使用 neo4j console 命令
                    try:
                        # 这里需要在后台运行，否则会阻塞
                        subprocess.Popen(['neo4j', 'console'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        print_success("Neo4j 服务已启动 (console 模式)")
                    except FileNotFoundError:
                        print_error("未找到 neo4j 命令，请确保 Neo4j 已安装并添加到环境变量")
                        return False
            elif system == 'Linux':
                # 尝试使用 systemctl
                try:
                    subprocess.run(['sudo', 'systemctl', 'start', 'neo4j'], check=True, capture_output=True, text=True)
                    print_success("Neo4j 服务已启动")
                except subprocess.CalledProcessError:
                    print_error("启动 Neo4j 服务失败")
                    return False
            else:  # macOS
                # 尝试使用 brew services
                try:
                    subprocess.run(['brew', 'services', 'start', 'neo4j'], check=True, capture_output=True, text=True)
                    print_success("Neo4j 服务已启动")
                except subprocess.CalledProcessError:
                    print_error("启动 Neo4j 服务失败")
                    return False
        
        # 等待 Neo4j 完全就绪
        print_info("等待 Neo4j 服务就绪...")
        if wait_for_port(7687):
            print_success("Neo4j 服务已就绪")
            # 记录到日志
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Neo4j 服务已就绪\n")
            return True
        else:
            print_error("Neo4j 服务启动超时")
            # 记录到日志
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Neo4j 服务启动超时\n")
            return False
    except Exception as e:
        print_error(f"启动 Neo4j 时出错: {str(e)}")
        # 记录到日志
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 启动 Neo4j 时出错: {str(e)}\n")
        return False

def activate_venv():
    """激活虚拟环境"""
    if os.path.exists(VENV_PATH):
        print_info("激活虚拟环境...")
        if platform.system() == 'Windows':
            activate_script = os.path.join(VENV_PATH, 'Scripts', 'activate.bat')
        else:
            activate_script = os.path.join(VENV_PATH, 'bin', 'activate')
        
        if os.path.exists(activate_script):
            return activate_script
        else:
            print_warning("虚拟环境存在但激活脚本不存在")
    return None

def start_backend():
    """启动后端服务"""
    # 检查端口是否被占用
    if is_port_in_use(8000):
        print_error("端口 8000 已被占用")
        print_info("可以使用以下命令查看并杀死占用进程:")
        if platform.system() == 'Windows':
            print_info("netstat -ano | findstr :8000")
            print_info("taskkill /PID <PID> /F")
        else:
            print_info("lsof -i :8000")
            print_info("kill -9 <PID>")
        return False
    
    print_info("启动后端服务...")
    
    try:
        # 构建启动命令
        cmd = [sys.executable, MAIN_SCRIPT]
        
        # 启动进程
        process = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # 保存 PID
        with open(PID_FILE, 'w') as f:
            f.write(str(process.pid))
        
        # 实时打印日志
        print_info("后端服务启动中，日志输出:")
        for line in iter(process.stdout.readline, ''):
            if line:
                print(line.strip())
                # 检查服务是否成功启动
                if "Uvicorn running on" in line:
                    print_success(f"后端服务已成功启动: {line.strip()}")
                    return True
        
        return False
    except Exception as e:
        print_error(f"启动后端服务时出错: {str(e)}")
        return False

def stop_backend():
    """停止后端服务"""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            
            print_info(f"停止后端服务 (PID: {pid})...")
            
            # 终止进程
            if platform.system() == 'Windows':
                subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True)
            else:
                subprocess.run(['kill', '-9', str(pid)], capture_output=True)
            
            # 清理 PID 文件
            os.remove(PID_FILE)
            print_success("后端服务已停止")
            return True
        except Exception as e:
            print_error(f"停止后端服务时出错: {str(e)}")
            # 尝试清理 PID 文件
            if os.path.exists(PID_FILE):
                try:
                    os.remove(PID_FILE)
                except:
                    pass
            return False
    else:
        # 尝试通过进程名查找并停止
        print_info("未找到 PID 文件，尝试通过进程名停止...")
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                if 'main.py' in ' '.join(proc.info['cmdline']):
                    print_info(f"找到后端进程 (PID: {proc.info['pid']})，正在停止...")
                    proc.terminate()
                    proc.wait(timeout=5)
                    print_success("后端服务已停止")
                    return True
            except:
                pass
        
        print_warning("未找到后端服务进程")
        return False

def stop_neo4j():
    """停止 Neo4j 服务"""
    system = platform.system()
    
    print_info("停止 Neo4j 服务...")
    
    try:
        if system == 'Windows':
            # 尝试使用 net stop 命令
            try:
                subprocess.run(['net', 'stop', 'neo4j'], check=True, capture_output=True, text=True)
                print_success("Neo4j 服务已停止")
            except subprocess.CalledProcessError:
                # 尝试通过端口查找并终止进程
                print_info("正在通过端口查找并终止 Neo4j 进程...")
                try:
                    # 查找占用 7474 和 7687 端口的进程
                    result = subprocess.run(
                        ['netstat', '-ano'],
                        capture_output=True,
                        text=True
                    )
                    
                    # 解析输出，查找占用端口的进程
                    pids = set()
                    for line in result.stdout.split('\n'):
                        if '7474' in line or '7687' in line:
                            parts = line.strip().split()
                            if len(parts) >= 5:
                                pids.add(parts[4])
                    
                    # 终止找到的进程
                    for pid in pids:
                        if pid and pid.isdigit():
                            print_info(f"终止 Neo4j 进程 (PID: {pid})...")
                            subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)
                            print_success(f"Neo4j 进程 (PID: {pid}) 已终止")
                    
                    # 验证停止
                    time.sleep(2)
                    if not is_port_in_use(7687):
                        print_success("Neo4j 服务已成功停止")
                    else:
                        print_warning("停止 Neo4j 服务失败，可能需要手动停止")
                except Exception as e:
                    print_error(f"通过端口终止 Neo4j 进程时出错: {str(e)}")
        elif system == 'Linux':
            # 尝试使用 systemctl
            try:
                subprocess.run(['sudo', 'systemctl', 'stop', 'neo4j'], check=True, capture_output=True, text=True)
                print_success("Neo4j 服务已停止")
            except subprocess.CalledProcessError:
                # 尝试通过端口查找并终止进程
                print_info("尝试通过端口查找并终止 Neo4j 进程...")
                try:
                    # 查找占用 7474 和 7687 端口的进程
                    result = subprocess.run(
                        ['lsof', '-i', ':7474,:7687'],
                        capture_output=True,
                        text=True
                    )
                    
                    # 解析输出，查找占用端口的进程
                    pids = set()
                    for line in result.stdout.split('\n')[1:]:  # 跳过表头
                        if line:
                            parts = line.strip().split()
                            if len(parts) >= 2:
                                pids.add(parts[1])
                    
                    # 终止找到的进程
                    for pid in pids:
                        if pid and pid.isdigit():
                            print_info(f"终止 Neo4j 进程 (PID: {pid})...")
                            subprocess.run(['kill', '-9', pid], capture_output=True)
                            print_success(f"Neo4j 进程 (PID: {pid}) 已终止")
                    
                    # 验证停止
                    time.sleep(2)
                    if not is_port_in_use(7687):
                        print_success("Neo4j 服务已成功停止")
                    else:
                        print_warning("停止 Neo4j 服务失败，可能需要手动停止")
                except Exception as e:
                    print_error(f"通过端口终止 Neo4j 进程时出错: {str(e)}")
        else:  # macOS
            # 尝试使用 brew services
            try:
                subprocess.run(['brew', 'services', 'stop', 'neo4j'], check=True, capture_output=True, text=True)
                print_success("Neo4j 服务已停止")
            except subprocess.CalledProcessError:
                # 尝试通过端口查找并终止进程
                print_info("尝试通过端口查找并终止 Neo4j 进程...")
                try:
                    # 查找占用 7474 和 7687 端口的进程
                    result = subprocess.run(
                        ['lsof', '-i', ':7474,:7687'],
                        capture_output=True,
                        text=True
                    )
                    
                    # 解析输出，查找占用端口的进程
                    pids = set()
                    for line in result.stdout.split('\n')[1:]:  # 跳过表头
                        if line:
                            parts = line.strip().split()
                            if len(parts) >= 2:
                                pids.add(parts[1])
                    
                    # 终止找到的进程
                    for pid in pids:
                        if pid and pid.isdigit():
                            print_info(f"终止 Neo4j 进程 (PID: {pid})...")
                            subprocess.run(['kill', '-9', pid], capture_output=True)
                            print_success(f"Neo4j 进程 (PID: {pid}) 已终止")
                    
                    # 验证停止
                    time.sleep(2)
                    if not is_port_in_use(7687):
                        print_success("Neo4j 服务已成功停止")
                    else:
                        print_warning("停止 Neo4j 服务失败，可能需要手动停止")
                except Exception as e:
                    print_error(f"通过端口终止 Neo4j 进程时出错: {str(e)}")
        return True
    except Exception as e:
        print_error(f"停止 Neo4j 时出错: {str(e)}")
        return False

def check_status():
    """检查服务运行状态"""
    print_info("检查服务运行状态...")
    
    # 检查 Neo4j
    neo4j_running = is_port_in_use(7687)
    if neo4j_running:
        print_success("Neo4j 服务: 运行中")
    else:
        print_error("Neo4j 服务: 未运行")
    
    # 检查后端服务
    backend_running = is_port_in_use(8000)
    if backend_running:
        print_success("后端服务: 运行中")
        print_info("访问地址: http://127.0.0.1:8000/docs")
    else:
        print_error("后端服务: 未运行")
    
    return neo4j_running and backend_running

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python run_service.py start    # 启动所有服务")
        print("  python run_service.py stop     # 停止所有服务")
        print("  python run_service.py status   # 检查服务状态")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'start':
        print_info("===== 启动服务 =====")
        
        # 步骤 1: 环境检查
        if not check_python_version():
            sys.exit(1)
        if not check_packages():
            sys.exit(1)
        
        # 步骤 2: 启动 Neo4j
        if not start_neo4j():
            sys.exit(1)
        
        # 步骤 3: 启动后端
        if not start_backend():
            sys.exit(1)
        
        # 步骤 4: 成功反馈
        print_success("===== 所有服务启动成功 =====")
        print_success("访问地址: http://127.0.0.1:8000/docs")
        
    elif command == 'stop':
        print_info("===== 停止服务 =====")
        
        # 步骤 1: 停止后端
        stop_backend()
        
        # 步骤 2: 询问是否停止 Neo4j
        if len(sys.argv) > 2 and sys.argv[2] == '--all':
            stop_neo4j()
        else:
            print_info("默认不停止 Neo4j 服务，如需同时停止，请使用 --all 参数")
        
        # 步骤 3: 清理
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except:
                pass
        
        print_success("===== 服务停止完成 =====")
        
    elif command == 'status':
        check_status()
        
    else:
        print_error(f"未知命令: {command}")
        print("用法:")
        print("  python run_service.py start    # 启动所有服务")
        print("  python run_service.py stop     # 停止所有服务")
        print("  python run_service.py status   # 检查服务状态")
        sys.exit(1)

if __name__ == '__main__':
    main()