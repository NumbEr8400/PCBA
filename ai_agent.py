import os
import httpx

def _build_biz_params(workflow_files):
    """基于公网 URL 构建工作流开始节点的 biz_params。"""
    biz_params = {}
    # 兼容不同工作流配置：
    # - url_string: 直接传 URL 字符串（与部分控制台调试 shell 一致）
    # - file_object: 传 {"url": "...", "name": "..."}（文档 File 示例）
    file_param_mode = os.getenv("DASHSCOPE_FILE_PARAM_MODE", "url_string").strip().lower()

    for workflow_file in workflow_files:
        variable_name = workflow_file["variable_name"]
        public_url = workflow_file.get("url", "")
        file_name = workflow_file["file_name"]
        if not public_url.startswith("http://") and not public_url.startswith("https://"):
            raise RuntimeError(
                f"文件 URL 非法（{variable_name}）：{public_url}。"
                "请检查 PUBLIC_HOST 配置和上传接口返回值。"
            )

        if file_param_mode == "file_object":
            biz_params[variable_name] = {
                "url": public_url,
                "name": file_name,
            }
        else:
            biz_params[variable_name] = public_url

    return biz_params

def _call_workflow_http(user_query, biz_params, api_key, app_id, base_address):
    """
    按控制台 curl 同构方式调用工作流应用，避免 SDK 行为差异。
    """
    url = f"{base_address.rstrip('/')}/apps/{app_id}/completion"
    payload = {
        "input": {
            "prompt": user_query,
            "biz_params": biz_params,
        },
        "parameters": {},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = httpx.post(url, headers=headers, json=payload, timeout=600)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP API 调用失败: {response.status_code} {response.text}")
    body = response.json()
    output = body.get("output", {}) if isinstance(body, dict) else {}
    text = output.get("text", "")
    if not text:
        raise RuntimeError(f"HTTP API 返回缺少 output.text: {body}")
    return text

def generate_diagnosis_stream(user_query, workflow_files):
    """
    生成诊断报告（流式输出，工作流应用版本）
    """
    try:
        # 从环境变量获取 API Key 和工作流 APP_ID（禁止硬编码）
        api_key = os.getenv('DASHSCOPE_API_KEY')
        app_id = os.getenv('DASHSCOPE_WORKFLOW_APP_ID') or os.getenv('DASHSCOPE_APP_ID')
        base_address = os.getenv('DASHSCOPE_BASE_ADDRESS', 'https://dashscope.aliyuncs.com/api/v1/')
        
        if not api_key:
            yield "生成诊断报告失败: 未设置 DASHSCOPE_API_KEY 环境变量"
            return
        
        if not app_id:
            yield "生成诊断报告失败: 未设置 DASHSCOPE_WORKFLOW_APP_ID（或 DASHSCOPE_APP_ID）环境变量"
            return
        
        # 基于公网 URL 构建工作流入参
        biz_params = _build_biz_params(workflow_files)
        
        text = _call_workflow_http(
            user_query=user_query,
            biz_params=biz_params,
            api_key=api_key,
            app_id=app_id,
            base_address=base_address,
        )
        # 以单次输出兼容现有流式前端逻辑
        yield text
    except Exception as e:
        yield f"生成诊断报告失败: {str(e)}"

def generate_diagnosis(user_query, workflow_files):
    """
    生成诊断报告（非流式，工作流应用版本）
    """
    full_text = ""
    for chunk in generate_diagnosis_stream(user_query, workflow_files):
        full_text += chunk
    return full_text