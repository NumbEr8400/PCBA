import os
from neo4j import GraphDatabase

# 从环境变量获取 Neo4j 连接信息
NEO4J_URI = os.getenv('NEO4J_URI', 'neo4j://127.0.0.1:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

# 初始化 Neo4j 驱动
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def get_capability_gap(rule_ids):
    """
    查询规则 ID 对应的能力短板
    
    Args:
        rule_ids: 规则 ID 列表
    
    Returns:
        dict: 每个规则 ID 对应的能力短板和教学目标
    """
    result = {}
    
    with driver.session() as session:
        for rule_id in rule_ids:
            query = """
            MATCH (r:DFM_Rule {id: $rule_id})-[:RELATES_TO]->(g:Capability_Gap)
            RETURN g.description AS gap, g.teaching_goal AS teaching_goal
            """
            
            try:
                records = session.run(query, rule_id=rule_id)
                record_list = list(records)
                
                if record_list:
                    record = record_list[0]
                    result[rule_id] = {
                        "gap": record.get("gap", ""),
                        "teaching_goal": record.get("teaching_goal", "")
                    }
                else:
                    result[rule_id] = {
                        "gap": "未知规则",
                        "teaching_goal": ""
                    }
            except Exception as e:
                result[rule_id] = {
                    "gap": f"查询失败: {str(e)}",
                    "teaching_goal": ""
                }
    
    return result

def close_driver():
    """
    关闭 Neo4j 驱动连接
    """
    if driver:
        driver.close()