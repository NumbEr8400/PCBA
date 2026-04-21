# DFM 报告智能诊断系统 - 

## 项目简介

本项目是一个基于 FastAPI 的服务，用于智能分析 DFM 评审报告 (PDF)，提取违规规则 ID，查询 Neo4j 知识图谱获取能力短板，最后调用阿里云百炼工作流应用生成个性化的教学反馈。

## 技术栈

- Web Framework: FastAPI
- PDF Processing: pdfplumber
- Database: Neo4j (via neo4j driver)
- LLM Workflow: Alibaba Cloud DashScope Workflow Application
- Config Management: python-dotenv
- HTTP Client: httpx

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

1. 复制 `.env.example` 文件为 `.env`
2. 填写 `.env` 文件中的配置信息：
   - `DASHSCOPE_API_KEY`: 阿里云 API Key
   - `DASHSCOPE_WORKFLOW_APP_ID`: 阿里云百炼工作流应用 ID（推荐）
   - `DASHSCOPE_APP_ID`: 兼容旧变量名，未设置 `DASHSCOPE_WORKFLOW_APP_ID` 时使用
   - `DASHSCOPE_BASE_ADDRESS`: 百炼 API 地址（默认 `https://dashscope.aliyuncs.com/api/v1/`）
   - `DASHSCOPE_FLOW_STREAM_MODE`: 工作流流式模式（默认 `message_format`）
   - `DASHSCOPE_FILE_PARAM_MODE`: 文件变量传参模式，`url_string`（默认）或 `file_object`
   - `PUBLIC_HOST`: 公网可访问域名（例如 localtunnel 地址 `https://xxx.loca.lt`），用于拼接工作流文件 URL
   - `VALIDATE_PUBLIC_URLS`: 调用工作流前是否校验文件 URL 可达性（默认 `false`）
   - `CASE_FILES_DIR`: 案例文件目录（用于查找本地 rating/map）
   - `CASE_1_RATING_PATH` / `CASE_1_MAP_PATH`: 案例 1 的评分标准与能力映射文件路径
   - `CASE_2_RATING_PATH` / `CASE_2_MAP_PATH` ... `CASE_9_RATING_PATH` / `CASE_9_MAP_PATH`: 预留扩展配置
   - `NEO4J_URI`: Neo4j 数据库连接地址
   - `NEO4J_USER`: Neo4j 数据库用户名
   - `NEO4J_PASSWORD`: Neo4j 数据库密码
   - `API_HOST`: FastAPI 监听地址（默认 `127.0.0.1`，仅本机访问）
   - `API_PORT`: FastAPI 监听端口（默认 `8000`）
   - `ALLOW_ORIGINS`: CORS 允许来源（逗号分隔，默认 `http://127.0.0.1:8000,http://localhost:8000,null`）

### 3. 启动服务

使用一键服务管理脚本（推荐）：

```bash
# 启动所有服务（Neo4j + FastAPI）
python run_service.py start

# 停止所有服务
python run_service.py stop

# 检查服务运行状态
python run_service.py status

# 停止所有服务（包括 Neo4j）
python run_service.py stop --all
```

或者直接启动服务：

```bash
python main.py
```

服务将默认运行在 `http://127.0.0.1:8000`（仅本机可访问）

## API 接口

### 健康检查

- **URL**: `/health`
- **Method**: GET
- **Response**:
  ```json
  {"status": "ok"}
  ```

### 分析 PDF

- **URL**: `/analyze`
- **Method**: POST
- **Form Data**:
  - `file1`: 学生报告文件（工作流开始节点变量）
  - `query`: 用户文字输入（工作流开始节点变量）
  - `case_id`: 案例编号（1~9），由后端按编号读取本地 `rating/map`
- **Response**:
  ```json
  {
    "status": "success",
    "data": {
      "case_id": "1",
      "inputs": ["student_report.pdf", "rating_rule.pdf", "capability_map.xlsx"],
      "diagnosis": "...生成的诊断报告..."
    }
  }
  ```

### 上传文件（生成公网 URL）

- **URL**: `/upload`
- **Method**: POST
- **Form Data**:
  - `file`: 上传文件
  - `variable_name`: 变量名（可选，默认 `file1`，支持 `file1/rating/map`）
- **Response**:
  ```json
  {
    "status": "success",
    "data": {
      "variable_name": "file1",
      "url": "https://your-tunnel-url.loca.lt/uploads/file1_xxx_report.md",
      "file_name": "report.md"
    }
  }
  ```

### 用户登录

- **URL**: `/api/login`
- **Method**: POST
- **Request Body**:
  ```json
  {
    "student_id": "3122002220",
    "password": "3122002220"
  }
  ```
- **Response**:
  ```json
  {
    "token": "45n3s4D69miP2a7ZTo3rhtAPCHnWGTCp",
    "user": {
      "student_name": "陈彦",
      "student_id": "3122002220",
      "class_name": "通信二班"
    }
  }
  ```

### 获取用户信息

- **URL**: `/api/user/info`
- **Method**: GET
- **Headers**:
  - `Authorization`: `Bearer <token>`
- **Response**:
  ```json
  {
    "student_name": "陈彦",
    "student_id": "3122002220",
    "class_name": "通信二班"
  }
  ```

### 获取仪表盘数据

- **URL**: `/api/dashboard/stats`
- **Method**: GET
- **Headers**:
  - `Authorization`: `Bearer <token>`
- **Response**:
  ```json
  {
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
          "value": [85, 78, 90, 75, 82],
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
      {"name": "基础封装规范", "progress": 90},
      {"name": "高速信号布线", "progress": 65},
      {"name": "DFM 规则进阶", "progress": 45},
      {"name": "PCB 设计实践", "progress": 30}
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
  ```

## 项目结构

```
server/
├── main.py         # FastAPI 入口文件
├── parsers.py      # PDF 解析逻辑
├── graph_db.py     # Neo4j 集成
├── ai_agent.py     # 阿里云百炼工作流调用
├── static/         # 前端静态文件
│   └── index.html  # 单页应用入口
├── requirements.txt # 依赖列表
├── .env.example    # 环境变量模板
└── README.md       # 项目说明
```

## 注意事项

1. 确保 Neo4j 数据库已启动并运行
2. 确保已获取有效的阿里云 DashScope API Key，并配置工作流 APP ID
3. 服务运行在校园网环境，CORS 已配置为允许所有来源，方便前端调试
4. 上传的 PDF 文件会被保存为临时文件，处理完成后会自动删除