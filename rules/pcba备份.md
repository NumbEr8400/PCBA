---
alwaysApply: false
---
# 项目背景
- **项目名称**：PCBA 知识图谱构建与学习评价系统
- **核心目标**：基于 PCBA 工业软件数据构建 DFM 知识图谱，利用 LLM 实现配套的学生学习自动评价
- **关键实体**：Rule(规则), Defect(缺陷), Component(元器件), Process(工艺), Student_Report(学生报告)

# 架构约束
- **前后端分离**：
  - 后端 (`server/`)：负责 API 逻辑、Neo4j 查询、LLM 调用
  - 前端 (`static/`)：负责 UI 渲染和用户交互
  - **禁止**在后端代码中混入 HTML/CSS，**禁止**在前端代码中硬编码敏感密钥
- **数据流向**：用户上传文件 → 后端解析 → 匹配 Neo4j 规则 → LLM 生成分析/评价 → 返回 JSON → 前端渲染

# 编码规范
- **Python**：
  - 严格遵循 PEP 8 规范，使用 4 空格缩进
  - 所有函数必须有 Type Hints (类型提示) 和文档字符串
  - 变量和函数命名使用 snake_case，类名使用 PascalCase
  - 数据库操作必须使用参数化查询，防止 Cypher 注入
  - 异步编程：IO 密集型任务（如 LLM 调用、文件读取）必须使用 `async/await`
  - 错误处理：使用 try-except 捕获异常，提供明确的错误信息
  - 日志记录：关键操作需添加日志，便于调试和监控
  - 模块导入：按标准库、第三方库、本地模块的顺序组织
- **JavaScript**：
  - 使用 ES6+ 语法 (const/let, arrow functions, template literals)
  - DOM 操作需封装，避免全局变量污染
  - 所有 AJAX/Fetch 请求必须包含 `try...catch` 错误处理
  - 代码缩进使用 2 空格
  - 变量和函数命名使用 camelCase
- **Neo4j**：
  - Cypher 语句需格式化，使用一致的缩进和换行
  - 节点标签使用 PascalCase (如 `:DFM_Rule`)
  - 属性使用 snake_case (如 `rule_id`)
  - 关系类型使用 UPPER_SNAKE_CASE (如 `:RELATES_TO`)

# 业务逻辑
- **DFM 分析逻辑**：必须严格基于 Neo4j 中的规则进行匹配，LLM 仅用于润色和推理，**严禁**让 LLM 凭空捏造不存在的 DFM 规则
- **评价系统逻辑**：
  - 采用“双维度评价”：语言统计 (Python 计算) + 内容质量 (LLM 少样本思维链)
  - 评分必须可解释，需返回具体的扣分点和改进建议
- **安全合规**：
  - 所有上传的文件必须限制后缀名 (.pdf)
  - API Key 必须从 `.env` 文件读取，严禁硬编码在代码中
  - 临时文件必须在处理完成后删除，避免磁盘空间占用

# 文件结构参考
- `server/main.py`: FastAPI 入口，包含路由和 Lifespan 事件
- `server/parsers.py`：PDF 解析逻辑，使用 pdfplumber 读取 PDF 文件并提取内容
- `server/graph_db.py`：Neo4j 数据库集成，实现图数据库的查询
- `server/ai_agent.py`：Qwen API 调用逻辑，构建 prompt 并生成诊断报告
- `server/static/index.html`：单页应用入口，包含所有前端逻辑
- `server/.env`: 存储 DASHSCOPE_API_KEY, NEO4J_URI 等敏感信息