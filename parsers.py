import re
import pdfplumber

def parse_pdf(pdf_path):
    """
    解析 PDF 文件，提取规则 ID 和上下文信息
    
    Args:
        pdf_path: PDF 文件路径
    
    Returns:
        list: 包含规则 ID 和上下文的结构化列表
    
    Raises:
        Exception: PDF 损坏或无法提取任何 ID 时抛出
    """
    try:
        results = []
        rule_id_pattern = r'(DFX-[A-Z0-9-]+)'
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if not text:
                    continue
                
                # 提取规则 ID
                matches = re.findall(rule_id_pattern, text)
                
                for match in matches:
                    # 尝试提取上下文信息
                    context = extract_context(text, match)
                    results.append({
                        "rule_id": match,
                        "context": context,
                        "page": page_num
                    })
        
        if not results:
            raise Exception("PDF 中未提取到任何规则 ID")
        
        return results
    except Exception as e:
        raise Exception(f"PDF 解析失败: {str(e)}")

def extract_context(text, rule_id):
    """
    提取规则 ID 的上下文信息
    
    Args:
        text: 页面文本
        rule_id: 规则 ID
    
    Returns:
        str: 上下文信息
    """
    # 简单实现：提取规则 ID 前后的文本作为上下文
    start_idx = max(0, text.find(rule_id) - 200)
    end_idx = min(len(text), text.find(rule_id) + len(rule_id) + 200)
    return text[start_idx:end_idx].strip()