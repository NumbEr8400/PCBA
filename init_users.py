#!/usr/bin/env python3
"""
初始化用户数据库脚本

通过读取 xlsx 表格创建用户节点数据
"""

import os
import sys
import pandas as pd
from neo4j import GraphDatabase
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 初始化 Neo4j 驱动
NEO4J_URI = os.getenv('NEO4J_URI', 'neo4j://127.0.0.1:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def init_users_from_excel(excel_path):
    """
    从 Excel 文件初始化用户数据
    
    Args:
        excel_path: Excel 文件路径
    """
    try:
        # 读取 Excel 文件
        df = pd.read_excel(excel_path)
        
        # 检查必要的列
        required_columns = ['password', 'student_name', 'student_id', 'class_name']
        for col in required_columns:
            if col not in df.columns:
                raise ValueError(f"Excel 文件缺少必要的列: {col}")
        
        # 连接数据库并创建用户节点
        with driver.session() as session:
            for index, row in df.iterrows():
                password = row['password']
                student_name = row['student_name']
                student_id = row['student_id']
                class_name = row['class_name']
                
                # 创建或更新用户节点
                query = """
                MERGE (u:User {student_id: $student_id})
                SET u.password = $password,
                    u.student_name = $student_name,
                    u.class_name = $class_name
                RETURN u
                """
                
                session.run(query,
                           password=password,
                           student_name=student_name,
                           student_id=student_id,
                           class_name=class_name)
                
                print(f"创建/更新用户: {student_id} - {student_name}")
        
        print(f"\n成功初始化 {len(df)} 个用户")
    except Exception as e:
        print(f"初始化用户失败: {str(e)}")
        return False
    finally:
        if driver:
            driver.close()
    
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python init_users.py <excel_file_path>")
        sys.exit(1)
    
    excel_path = sys.argv[1]
    if not os.path.exists(excel_path):
        print(f"Excel 文件不存在: {excel_path}")
        sys.exit(1)
    
    init_users_from_excel(excel_path)