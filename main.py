import os
import random
import string
import json
import uuid
import shutil
import pandas as pd
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

from graph_db import close_driver
from ai_agent import generate_diagnosis, generate_diagnosis_stream
from neo4j import GraphDatabase

# 加载环境变量
load_dotenv()

# 初始化 Neo4j 驱动
NEO4J_URI = os.getenv('NEO4J_URI', 'neo4j://127.0.0.1:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# 服务监听配置（默认仅本机访问）
API_HOST = os.getenv('API_HOST', '127.0.0.1')
try:
    API_PORT = int(os.getenv('API_PORT', '8000'))
except ValueError:
    API_PORT = 8000

# CORS 配置（默认仅允许本机来源）
ALLOW_ORIGINS = [
    origin.strip() for origin in os.getenv(
        'ALLOW_ORIGINS',
        'http://127.0.0.1:8000,http://localhost:8000,null'
    ).split(',') if origin.strip()
]
PUBLIC_HOST = os.getenv('PUBLIC_HOST', '').strip()
VALIDATE_PUBLIC_URLS = os.getenv('VALIDATE_PUBLIC_URLS', 'false').strip().lower() == 'true'
UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

# 若配置了 PUBLIC_HOST（如 localtunnel 地址），自动加入 CORS 白名单
if PUBLIC_HOST and PUBLIC_HOST not in ALLOW_ORIGINS:
    ALLOW_ORIGINS.append(PUBLIC_HOST)

# 案例配置：前端仅上传学生报告，rating/map 由后端按案例编号读取本地文件
CASE_ID_OPTIONS = tuple(str(i) for i in range(1, 10))
CASE_FILES_DIR = os.getenv('CASE_FILES_DIR', r'C:\Users\84001\Desktop\project\QWEN\课程报告样本')
USER_DATA_XLSX_PATH = os.getenv(
    "USER_DATA_XLSX_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "usr_data.xlsx")
)

def _build_case_file_config():
    config = {}
    for case_id in CASE_ID_OPTIONS:
        rating_path = os.getenv(f'CASE_{case_id}_RATING_PATH')
        map_path = os.getenv(f'CASE_{case_id}_MAP_PATH')
        if rating_path and map_path:
            config[case_id] = {"rating": rating_path, "map": map_path}

    # 提供案例1默认值，方便本地直接试跑；后续可通过 .env 覆盖
    if "1" not in config:
        config["1"] = {
            "rating": os.path.join(CASE_FILES_DIR, "评分标准_细化版.md"),
            "map": os.path.join(CASE_FILES_DIR, "能力映射_无人机.md"),
        }
    return config

CASE_FILE_CONFIG = _build_case_file_config()


def _normalize_score(value):
    """
    兼容空值/字符串评分，统一转换为 0-100 区间内数值。
    """
    if pd.isna(value):
        return 0
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, score))


def _read_user_radar_scores(student_id: str):
    """
    按 student_id 在 usr_data.xlsx 中匹配用户，并读取 F~J 列（5 个能力分数）。
    """
    if not os.path.exists(USER_DATA_XLSX_PATH):
        raise HTTPException(status_code=500, detail=f"用户能力数据文件不存在: {USER_DATA_XLSX_PATH}")

    df = pd.read_excel(USER_DATA_XLSX_PATH)
    if "student_id" not in df.columns:
        raise HTTPException(status_code=500, detail="usr_data.xlsx 缺少 student_id 列")
    if df.shape[1] < 10:
        raise HTTPException(status_code=500, detail="usr_data.xlsx 列数量不足，无法读取 F~J 列")

    student_id_str = str(student_id).strip()
    matched_rows = df[df["student_id"].astype(str).str.strip() == student_id_str]
    if matched_rows.empty:
        raise HTTPException(status_code=404, detail=f"未找到学号为 {student_id_str} 的能力数据")

    scores = matched_rows.iloc[0, 5:10].tolist()
    return [_normalize_score(score) for score in scores]

def _resolve_case_files(case_id: str):
    normalized_case_id = str(case_id).strip()
    if normalized_case_id not in CASE_ID_OPTIONS:
        raise HTTPException(status_code=400, detail=f"无效案例编号: {case_id}，仅支持 1-9")

    case_files = CASE_FILE_CONFIG.get(normalized_case_id)
    if not case_files:
        raise HTTPException(status_code=400, detail=f"案例 {normalized_case_id} 尚未配置 rating/map 文件")

    for key in ("rating", "map"):
        file_path = case_files.get(key)
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(
                status_code=500,
                detail=f"案例 {normalized_case_id} 的 {key} 文件不存在: {file_path}"
            )
    return normalized_case_id, case_files

def _build_public_host_from_request(request: Request):
    # 优先使用 .env 中配置的公网域名（例如 localtunnel 地址）
    if PUBLIC_HOST:
        return PUBLIC_HOST.rstrip("/")
    return str(request.base_url).rstrip("/")

def _to_utf8_text_bytes(raw_bytes: bytes):
    """
    将文本字节尽量转成 UTF-8，提升文档解析节点兼容性。
    """
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5"):
        try:
            text = raw_bytes.decode(enc)
            return text.encode("utf-8")
        except Exception:
            continue
    return raw_bytes

def _save_upload_to_public(upload: UploadFile, variable_name: str, request: Request):
    original_name = upload.filename or f"{variable_name}.bin"
    file_name_only = os.path.basename(original_name)
    _, ext = os.path.splitext(file_name_only)
    ext = (ext or ".bin").lower()
    # 保留原始扩展名，和百炼控制台可用请求保持一致（如 .md）
    saved_name = f"{variable_name}_{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOADS_DIR, saved_name)

    file_bytes = upload.file.read()
    if ext in (".md", ".txt"):
        file_bytes = _to_utf8_text_bytes(file_bytes)
    with open(save_path, "wb") as out:
        out.write(file_bytes)

    public_host = _build_public_host_from_request(request)
    public_url = f"{public_host}/uploads/{saved_name}"
    return {
        "variable_name": variable_name,
        "url": public_url,
        "file_name": file_name_only,
    }

def _save_local_case_file_to_public(variable_name: str, source_path: str, request: Request):
    original_name = os.path.basename(source_path) or f"{variable_name}.bin"
    _, ext = os.path.splitext(original_name)
    ext = (ext or ".bin").lower()
    # 保留原始扩展名，和百炼控制台可用请求保持一致（如 .md）
    saved_name = f"{variable_name}_{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOADS_DIR, saved_name)
    if ext in (".md", ".txt"):
        with open(source_path, "rb") as source:
            content = source.read()
        with open(save_path, "wb") as target:
            target.write(_to_utf8_text_bytes(content))
    else:
        shutil.copyfile(source_path, save_path)

    public_host = _build_public_host_from_request(request)
    public_url = f"{public_host}/uploads/{saved_name}"
    return {
        "variable_name": variable_name,
        "url": public_url,
        "file_name": original_name,
    }

def _validate_public_file_urls(workflow_files):
    """
    在调用工作流前校验文件 URL 是否可达，避免工作流内出现不透明的 PARSE_FAILED。
    """
    if not VALIDATE_PUBLIC_URLS:
        return

    for item in workflow_files:
        url = item.get("url")
        var_name = item.get("variable_name", "unknown")
        if not url:
            raise HTTPException(status_code=500, detail=f"{var_name} 缺少文件 URL")
        try:
            resp = httpx.get(url, timeout=15)
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"公网文件 URL 访问失败（{var_name}）：{url}，错误：{str(e)}"
            )
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"公网文件 URL 不可用（{var_name}）：{url}，HTTP {resp.status_code}。"
                    "请确认 localtunnel 在线且 PUBLIC_HOST 使用当前有效地址。"
                ),
            )

# 用于存储 token 和用户信息的内存存储（生产环境应该使用 Redis 或数据库）
token_store = {}

# 生成随机 token
def generate_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=32))

# 知识图谱模式配置
GRAPH_MODES = {
    "mode_scene": {
        "root_label": "LearningObjective",  #default:DFM_Scene
        "relation_depth": 1
    },
    "mode_defect": {
        "root_label": "RuleClass",  #default:Defect_Case
        "relation_depth": 1
    },
    "mode_competency": {
        "root_label": "Capability",  #default:Competency_Goal  
        "relation_depth": 1
    }
}

# 节点类型到类别的映射
NODE_TYPE_TO_CATEGORY = {
    #"DFM_Scene": 0,           # 场景
    "LearningObjective": 0,    # 学习目标
    #"DesignRule": 1,             # 规则
    "RuleClass": 1,            # 规则类
    #"Defect_Case": 2,           # 缺陷
    #"Competency_Goal": 3,      # 能力目标
    "Capability": 3             # 能力
}

# 验证 token
def verify_token(token: str):
    return token_store.get(token)

# 安全方案
security = HTTPBearer()

# 获取当前用户
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="无效的 token")
    return user

# 定义 lifespan 函数
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行的代码（如果有）
    yield
    # 关闭时执行的代码
    close_driver()
    if driver:
        driver.close()

# 创建 FastAPI 应用实例
app = FastAPI(lifespan=lifespan)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    # 当前前端使用 Bearer Token，不依赖 Cookie，关闭 credentials 可减少跨域失败概率。
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# 根路径路由，返回前端页面
@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.get("/health")
def health_check():
    """
    健康检查端点
    """
    return {"status": "ok"}

@app.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    variable_name: str = Form("file1"),
):
    """
    接收单文件上传并返回可供工作流访问的公网 URL
    """
    if not file:
        raise HTTPException(status_code=400, detail="未接收到文件")
    if variable_name not in ("file1", "rating", "map"):
        raise HTTPException(status_code=400, detail="variable_name 仅支持 file1/rating/map")

    upload_meta = _save_upload_to_public(file, variable_name, request)
    return {
        "status": "success",
        "data": upload_meta,
    }

@app.post("/analyze")
async def analyze_pdf(
    request: Request,
    file1: UploadFile = File(...),
    query: str = Form(...),
    case_id: str = Form("1")
):
    """
    基于工作流输入（query + file1 + case_id）生成诊断报告
    """
    resolved_case_id, case_files = _resolve_case_files(case_id)
    workflow_files = [
        _save_upload_to_public(file1, "file1", request),
        _save_local_case_file_to_public("rating", case_files["rating"], request),
        _save_local_case_file_to_public("map", case_files["map"], request),
    ]
    _validate_public_file_urls(workflow_files)

    diagnosis = generate_diagnosis(query, workflow_files)
    
    # 返回结果
    return {
        "status": "success",
        "data": {
            "case_id": resolved_case_id,
            "inputs": [item["file_name"] for item in workflow_files],
            "file_urls": {item["variable_name"]: item["url"] for item in workflow_files},
            "diagnosis": diagnosis
        }
    }

@app.post("/analyze/stream")
async def analyze_pdf_stream(
    request: Request,
    file1: UploadFile = File(...),
    query: str = Form(...),
    case_id: str = Form("1")
):
    """
    基于工作流输入（query + file1 + case_id）流式生成诊断报告
    """
    resolved_case_id, case_files = _resolve_case_files(case_id)
    workflow_files = [
        _save_upload_to_public(file1, "file1", request),
        _save_local_case_file_to_public("rating", case_files["rating"], request),
        _save_local_case_file_to_public("map", case_files["map"], request),
    ]
    _validate_public_file_urls(workflow_files)
    
    # 生成流式响应
    async def stream_response():
        # 先发送输入文件信息
        input_names = [item["file_name"] for item in workflow_files]
        yield json.dumps({"type": "inputs", "data": input_names}, ensure_ascii=False) + "\n"
        yield json.dumps({"type": "case_id", "data": resolved_case_id}, ensure_ascii=False) + "\n"
        
        # 然后发送诊断报告流
        for chunk in generate_diagnosis_stream(query, workflow_files):
            yield json.dumps({"type": "diagnosis", "data": chunk}, ensure_ascii=False) + "\n"
    
    # 返回流式响应
    return StreamingResponse(
        stream_response(),
        media_type="application/json"
    )

@app.post("/api/login")
async def login(student_id: str = Body(...), password: str = Body(...)):
    """
    用户登录
    
    Args:
        student_id: 学号
        password: 密码
    
    Returns:
        dict: 包含 token 和用户信息
    """
    try:
        with driver.session() as session:
            # 尝试将参数转换为字符串，确保类型匹配
            student_id_str = str(student_id)
            password_str = str(password)
            
            # 获取所有用户，然后在Python中进行比较（避免类型转换问题）
            query = "MATCH (u:User) RETURN u"
            result = session.run(query)
            
            found = False
            user_info = None
            
            for r in result:
                user = r['u']
                db_student_id = user.get('student_id')
                db_password = user.get('password')
                
                # 将数据库中的值转换为字符串进行比较
                if str(db_student_id) == student_id_str and str(db_password) == password_str:
                    user_info = {
                        "student_name": user.get('student_name'),
                        "student_id": str(db_student_id),  # 转换为字符串返回
                        "class_name": user.get('class_name')
                    }
                    found = True
                    break
            
            if not found:
                raise HTTPException(status_code=401, detail="学号或密码错误")
            
            # 生成 token
            token = generate_token()
            
            # 存储 token 和用户信息
            token_store[token] = user_info
            
            return {
                "token": token,
                "user": user_info
            }
    except HTTPException:
        raise
    except Exception as e:
        print(f"登录异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"登录失败: {str(e)}")

@app.get("/api/user/info")
async def get_user_info(current_user: dict = Depends(get_current_user)):
    """
    获取当前用户信息
    
    Args:
        current_user: 当前用户信息
    
    Returns:
        dict: 用户信息
    """
    return current_user

@app.get("/api/dashboard/stats")
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    """
    获取仪表盘统计数据
    
    Args:
        current_user: 当前用户信息
    
    Returns:
        dict: 包含雷达图数据、进度列表和最近动态的统计数据
    """
    try:
        ability_scores = _read_user_radar_scores(current_user["student_id"])
        radar_data = {
            "indicators": [
                {"name": "规则掌握度", "max": 100},
                {"name": "缺陷识别率", "max": 100},
                {"name": "工艺规范性", "max": 100},
                {"name": "设计优化能力", "max": 100},
                {"name": "报告质量", "max": 100}
            ],
            "data": [
                {
                    "value": ability_scores,
                    "name": "综合能力",
                    "areaStyle": {
                        "color": "rgba(59, 130, 246, 0.2)"
                    },
                    "lineStyle": {
                        "color": "#3b82f6"
                    },
                    "itemStyle": {
                        "color": "#3b82f6"
                    }
                }
            ]
        }

        progress_list = [
            {"name": "基础封装规范", "progress": 90},
            {"name": "高速信号布线", "progress": 65},
            {"name": "DFM 规则进阶", "progress": 45},
            {"name": "PCB 设计实践", "progress": 30}
        ]

        recent_activities = [
            {
                "time": "2026-03-15 14:30",
                "content": "完成了 \"基础封装规范\" 模块的学习",
                "type": "success"
            },
            {
                "time": "2026-03-14 09:15",
                "content": "提交了 DFM 分析报告",
                "type": "info"
            },
            {
                "time": "2026-03-13 16:45",
                "content": "系统更新了新的 DFM 规则库",
                "type": "warning"
            }
        ]

        return {
            "radar_data": radar_data,
            "progress_list": progress_list,
            "recent_activities": recent_activities
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取仪表盘数据异常: {str(e)}")
        # 发生异常时，返回模拟数据
        return {
            "radar_data": {
                "indicators": [
                    {"name": "规则掌握度", "max": 100},
                    {"name": "缺陷识别率", "max": 100},
                    {"name": "工艺规范性", "max": 100},
                    {"name": "设计优化能力", "max": 100},
                    {"name": "报告质量", "max": 100}
                ],
                "data": [
                    {
                        "value": [80, 75, 85, 70, 78],
                        "name": "综合能力",
                        "areaStyle": {
                            "color": "rgba(59, 130, 246, 0.2)"
                        },
                        "lineStyle": {
                            "color": "#3b82f6"
                        },
                        "itemStyle": {
                            "color": "#3b82f6"
                        }
                    }
                ]
            },
            "progress_list": [
                {"name": "基础封装规范", "progress": 85},
                {"name": "高速信号布线", "progress": 60},
                {"name": "DFM 规则进阶", "progress": 40},
                {"name": "PCB 设计实践", "progress": 25}
            ],
            "recent_activities": [
                {
                    "time": "2026-03-15 14:30",
                    "content": "完成了 \"基础封装规范\" 模块的学习",
                    "type": "success"
                },
                {
                    "time": "2026-03-14 09:15",
                    "content": "提交了 DFM 分析报告",
                    "type": "info"
                },
                {
                    "time": "2026-03-13 16:45",
                    "content": "系统更新了新的 DFM 规则库",
                    "type": "warning"
                }
            ]
        }

@app.get("/api/graph/global")
async def get_global_graph(mode: str = "mode_scene", current_user: dict = Depends(get_current_user)):
    """
    获取全局知识图谱数据
    
    Args:
        mode: 图谱模式，可选值：mode_scene, mode_defect, mode_competency
        current_user: 当前用户信息
    
    Returns:
        dict: ECharts 格式的图谱数据
    """
    try:
        # 验证模式是否有效
        if mode not in GRAPH_MODES:
            raise HTTPException(status_code=400, detail="无效的模式参数")
        
        # 获取模式配置
        mode_config = GRAPH_MODES[mode]
        root_label = mode_config["root_label"]
        relation_depth = mode_config["relation_depth"]
        
        with driver.session() as session:
            # 1. 查询所有 root_label 节点
            nodes_query = f"""
            MATCH (n:{root_label})
            RETURN id(n) AS node_id, labels(n)[0] AS label, 
                   COALESCE(n.name, n.title, n.label, toString(id(n))) AS name
            """
            
            # 2. 查询所有与 root_label 节点相连的关系（双向）
            rels_query = f"""
            MATCH (n:{root_label})-[r]-(m)
            RETURN id(n) AS source_id, id(m) AS target_id, 
                   labels(n)[0] AS source_label, labels(m)[0] AS target_label,
                   COALESCE(n.name, n.title, n.label, toString(id(n))) AS source_name,
                   COALESCE(m.name, m.title, m.label, toString(id(m))) AS target_name,
                   type(r) AS relation_type
            """
            
            # 执行查询
            nodes_result = session.run(nodes_query)
            rels_result = session.run(rels_query)
            
            # 3. 先构建完整节点字典（初始 value=0）
            nodes = {}
            
            # 处理根节点
            for record in nodes_result:
                node_id = record["node_id"]
                label = record["label"]
                name = record["name"]
                
                nodes[node_id] = {
                    "id": node_id,
                    "name": name,
                    "category": NODE_TYPE_TO_CATEGORY.get(label, 0),
                    "value": 0,  # 初始度数为0
                    "type": label
                }
            
            # 4. 遍历关系，更新 source/target 的 value 并添加边
            links = []
            
            for record in rels_result:
                source_id = record["source_id"]
                target_id = record["target_id"]
                source_label = record["source_label"]
                target_label = record["target_label"]
                source_name = record["source_name"]
                target_name = record["target_name"]
                
                # 确保目标节点也在节点字典中
                if target_id not in nodes:
                    nodes[target_id] = {
                        "id": target_id,
                        "name": target_name,
                        "category": NODE_TYPE_TO_CATEGORY.get(target_label, 0),
                        "value": 0,
                        "type": target_label
                    }
                
                # 更新度数
                nodes[source_id]["value"] += 1
                nodes[target_id]["value"] += 1
                
                # 添加边
                links.append({
                    "source": source_id,
                    "target": target_id,
                    "value": 1
                })
            
            # 5. 最后按需截断（>200 时）
            node_list = list(nodes.values())
            if len(node_list) > 200:
                # 按度数排序
                node_list.sort(key=lambda x: x["value"], reverse=True)
                # 取前200个
                top_nodes = node_list[:200]
                top_node_ids = set(node["id"] for node in top_nodes)
                
                # 过滤边，只保留涉及前200个节点的边
                filtered_links = [link for link in links if link["source"] in top_node_ids and link["target"] in top_node_ids]
                
                return {
                    "nodes": top_nodes,
                    "links": filtered_links
                }
            
            # 打印统计信息
            print(f"Mode {mode}: 返回 {len(node_list)} 个节点, {len(links)} 条边")
            
            # 如果节点数量不超过200，返回所有节点和边
            return {
                "nodes": node_list,
                "links": links
            }
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取全局图谱数据异常: {str(e)}")
        # 发生异常时，返回空数据
        return {
            "nodes": [],
            "links": []
        }

@app.post("/api/graph/subgraph")
async def get_subgraph(node_id: int = Body(...), node_type: str = Body(...), current_user: dict = Depends(get_current_user)):
    """
    获取节点的子图数据（直接邻居）
    
    Args:
        node_id: 节点ID
        node_type: 节点类型
        current_user: 当前用户信息
    
    Returns:
        dict: ECharts 格式的图谱数据
    """
    try:
        with driver.session() as session:
            # 构建查询，获取节点及其所有直接邻居
            query = """
            MATCH (n)
            WHERE id(n) = $node_id
            OPTIONAL MATCH (n)-[r]-(m)
            RETURN id(n) as center_id, labels(n)[0] as center_label, 
                   COALESCE(n.name, n.title, n.label, n.id) as center_name,
                   id(m) as neighbor_id, labels(m)[0] as neighbor_label, 
                   COALESCE(m.name, m.title, m.label, m.id) as neighbor_name,
                   type(r) as relation_type
            """
            
            result = session.run(query, node_id=node_id)
            
            # 处理节点和边
            nodes = {}
            links = []
            
            # 添加中心节点
            center_node = None
            for record in result:
                if center_node is None:
                    center_id = record["center_id"]
                    center_label = record["center_label"]
                    center_name = record["center_name"] or f"{center_label} {center_id}"
                    center_node = {
                        "id": center_id,
                        "name": center_name,
                        "category": NODE_TYPE_TO_CATEGORY.get(center_label, 0),
                        "value": 1,
                        "type": center_label
                    }
                    nodes[center_id] = center_node
                
                # 处理邻居节点和边（如果存在关系）
                neighbor_id = record["neighbor_id"]
                if neighbor_id is not None:
                    if neighbor_id not in nodes:
                        neighbor_label = record["neighbor_label"]
                        neighbor_name = record["neighbor_name"] or f"{neighbor_label} {neighbor_id}"
                        nodes[neighbor_id] = {
                            "id": neighbor_id,
                            "name": neighbor_name,
                            "category": NODE_TYPE_TO_CATEGORY.get(neighbor_label, 0),
                            "value": 1,
                            "type": neighbor_label
                        }
                    
                    # 处理边
                    links.append({
                        "source": record["center_id"],
                        "target": neighbor_id,
                        "value": 1
                    })
            
            # 如果没有找到中心节点，返回空数据
            if center_node is None:
                return {
                    "nodes": [],
                    "links": []
                }
            
            # 返回子图数据
            return {
                "nodes": list(nodes.values()),
                "links": links
            }
    except Exception as e:
        print(f"获取子图数据异常: {str(e)}")
        # 发生异常时，返回空数据
        return {
            "nodes": [],
            "links": []
        }

@app.get("/api/graph/node_detail")
async def get_node_detail(id: int, type: str, current_user: dict = Depends(get_current_user)):
    """
    获取节点的详细信息
    
    Args:
        id: 节点ID
        type: 节点类型
        current_user: 当前用户信息
    
    Returns:
        dict: 节点的完整属性信息
    """
    try:
        with driver.session() as session:
            # 构建查询，获取节点的所有属性
            query = """
            MATCH (n)
            WHERE id(n) = $node_id
            RETURN n
            """
            
            result = session.run(query, node_id=id)
            record = result.single()
            
            if not record:
                return {}
            
            # 获取节点属性
            node = record["n"]
            node_properties = dict(node)
            node_properties["id"] = id
            node_properties["type"] = type
            
            return node_properties
    except Exception as e:
        print(f"获取节点详情异常: {str(e)}")
        # 发生异常时，返回空数据
        return {}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)