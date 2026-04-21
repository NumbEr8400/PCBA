#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Neo4j 知识图谱数据初始化脚本

该脚本用于读取 Excel 文件并将数据导入本地 Neo4j 数据库。
支持三个 Sheet："场景与规则"、"缺陷与方案"、"能力目标"。

依赖库：
- pandas
- openpyxl
- neo4j
- python-dotenv

使用方法：
1. 安装依赖：pip install pandas openpyxl neo4j python-dotenv
2. 确保 Neo4j 数据库已启动
3. 确保 .env 文件中配置了 Neo4j 连接信息
4. 运行脚本：python init_graph_data.py
"""

import os
import pandas as pd
from neo4j import GraphDatabase
from dotenv import load_dotenv
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# Neo4j 连接信息
NEO4J_URI = os.getenv('NEO4J_URI', 'neo4j://127.0.0.1:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

# Excel 文件路径
EXCEL_FILE = '大纲案例.xlsx'

class GraphDataInitializer:
    def __init__(self):
        """初始化 Neo4j 驱动"""
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.scene_cache = {}
        self.rule_cache = {}
        self.defect_cache = {}
        self.competency_cache = {}
    
    def close(self):
        """关闭数据库连接"""
        if self.driver:
            self.driver.close()
    
    def load_excel(self):
        """加载 Excel 文件"""
        try:
            excel_data = pd.ExcelFile(EXCEL_FILE)
            logger.info(f"成功加载 Excel 文件: {EXCEL_FILE}")
            return excel_data
        except Exception as e:
            logger.error(f"加载 Excel 文件失败: {str(e)}")
            raise
    
    def process_scene_rule_sheet(self, excel_data):
        """处理"场景与规则"Sheet"""
        try:
            df = excel_data.parse('场景与规则')
            logger.info(f"开始处理 '场景与规则' Sheet，共 {len(df)} 行数据")
            
            # 过滤空行
            df = df.dropna(how='all')
            logger.info(f"过滤后剩余 {len(df)} 行有效数据")
            
            with self.driver.session() as session:
                for idx, row in df.iterrows():
                    try:
                        # 提取数据
                        scene_name = str(row.get('场景名称', '')).strip()
                        scene_category = str(row.get('场景分类', '')).strip()
                        rule_content = str(row.get('规则内容', '')).strip()
                        ipc_standard = str(row.get('IPC标准', '')).strip()
                        difficulty_level = str(row.get('难度等级', '')).strip()
                        
                        # 跳过空数据
                        if not scene_name or not rule_content:
                            logger.warning(f"第 {idx+1} 行数据不完整，跳过")
                            continue
                        
                        # 处理场景节点
                        scene_id = self._get_or_create_scene(session, scene_name, scene_category)
                        
                        # 处理规则节点
                        rule_id = self._get_or_create_rule(session, rule_content, ipc_standard, difficulty_level)
                        
                        # 建立关系
                        self._create_scene_rule_relation(session, scene_id, rule_id)
                        
                        logger.info(f"成功处理第 {idx+1} 行：场景 '{scene_name}' -> 规则 '{rule_content[:20]}...'")
                    except Exception as e:
                        logger.error(f"处理第 {idx+1} 行失败: {str(e)}")
        except Exception as e:
            logger.error(f"处理 '场景与规则' Sheet 失败: {str(e)}")
            raise
    
    def process_defect_sheet(self, excel_data):
        """处理"缺陷与方案"Sheet"""
        try:
            df = excel_data.parse('缺陷与方案')
            logger.info(f"开始处理 '缺陷与方案' Sheet，共 {len(df)} 行数据")
            
            # 过滤空行
            df = df.dropna(how='all')
            logger.info(f"过滤后剩余 {len(df)} 行有效数据")
            
            with self.driver.session() as session:
                for idx, row in df.iterrows():
                    try:
                        # 提取数据
                        defect_name = str(row.get('缺陷名称', '')).strip()
                        cause_description = str(row.get('成因描述', '')).strip()
                        solution = str(row.get('解决方案', '')).strip()
                        related_rule_content = str(row.get('关联规则内容', '')).strip()
                        
                        # 跳过空数据
                        if not defect_name:
                            logger.warning(f"第 {idx+1} 行数据不完整，跳过")
                            continue
                        
                        # 查找关联规则
                        rule_id = None
                        if related_rule_content:
                            rule_id = self._find_rule_by_content(session, related_rule_content)
                        
                        # 创建缺陷节点
                        defect_id = self._get_or_create_defect(session, defect_name, cause_description, solution)
                        
                        # 建立关系
                        if rule_id:
                            self._create_rule_defect_relation(session, rule_id, defect_id)
                            logger.info(f"成功处理第 {idx+1} 行：规则 -> 缺陷 '{defect_name}'")
                        else:
                            logger.warning(f"第 {idx+1} 行：未找到关联规则 '{related_rule_content[:20]}...'，仅创建缺陷节点")
                    except Exception as e:
                        logger.error(f"处理第 {idx+1} 行失败: {str(e)}")
        except Exception as e:
            logger.error(f"处理 '缺陷与方案' Sheet 失败: {str(e)}")
            raise
    
    def process_competency_sheet(self, excel_data):
        """处理"能力目标"Sheet"""
        try:
            df = excel_data.parse('能力目标')
            logger.info(f"开始处理 '能力目标' Sheet，共 {len(df)} 行数据")
            
            # 过滤空行
            df = df.dropna(how='all')
            logger.info(f"过滤后剩余 {len(df)} 行有效数据")
            
            with self.driver.session() as session:
                for idx, row in df.iterrows():
                    try:
                        # 提取数据
                        goal_name = str(row.get('目标名称', '')).strip()
                        skill_level = str(row.get('技能等级', '')).strip()
                        certification_standard = str(row.get('认证标准', '')).strip()
                        required_scenes = str(row.get('所需场景', '')).strip()
                        required_rule_keywords = str(row.get('所需规则关键词', '')).strip()
                        
                        # 跳过空数据
                        if not goal_name:
                            logger.warning(f"第 {idx+1} 行数据不完整，跳过")
                            continue
                        
                        # 创建能力目标节点
                        competency_id = self._get_or_create_competency(session, goal_name, skill_level, certification_standard)
                        
                        # 处理所需场景
                        if required_scenes:
                            scene_names = [s.strip() for s in required_scenes.split(',')]
                            for scene_name in scene_names:
                                if scene_name:
                                    scene_id = self._find_scene_by_name(session, scene_name)
                                    if scene_id:
                                        self._create_competency_scene_relation(session, competency_id, scene_id)
                        
                        # 处理所需规则关键词
                        if required_rule_keywords:
                            keywords = [k.strip() for k in required_rule_keywords.split(',')]
                            for keyword in keywords:
                                if keyword:
                                    rule_ids = self._find_rules_by_keyword(session, keyword)
                                    for rule_id in rule_ids:
                                        self._create_competency_rule_relation(session, competency_id, rule_id)
                        
                        logger.info(f"成功处理第 {idx+1} 行：能力目标 '{goal_name}'")
                    except Exception as e:
                        logger.error(f"处理第 {idx+1} 行失败: {str(e)}")
        except Exception as e:
            logger.error(f"处理 '能力目标' Sheet 失败: {str(e)}")
            raise
    
    def _get_or_create_scene(self, session, scene_name, scene_category):
        """获取或创建场景节点"""
        if scene_name in self.scene_cache:
            return self.scene_cache[scene_name]
        
        query = """
        MERGE (s:DFM_Scene {name: $name})
        SET s.category = $category
        RETURN id(s) as id
        """
        result = session.run(query, name=scene_name, category=scene_category)
        record = result.single()
        scene_id = record['id']
        self.scene_cache[scene_name] = scene_id
        return scene_id
    
    def _get_or_create_rule(self, session, rule_content, ipc_standard, difficulty_level):
        """获取或创建规则节点"""
        if rule_content in self.rule_cache:
            return self.rule_cache[rule_content]
        
        query = """
        MERGE (r:DFM_Rule {content: $content})
        SET r.ipc_standard = $ipc_standard, r.difficulty_level = $difficulty_level
        RETURN id(r) as id
        """
        result = session.run(query, content=rule_content, ipc_standard=ipc_standard, difficulty_level=difficulty_level)
        record = result.single()
        rule_id = record['id']
        self.rule_cache[rule_content] = rule_id
        return rule_id
    
    def _get_or_create_defect(self, session, defect_name, cause_description, solution):
        """获取或创建缺陷节点"""
        if defect_name in self.defect_cache:
            return self.defect_cache[defect_name]
        
        query = """
        MERGE (d:Defect_Case {name: $name})
        SET d.cause_description = $cause_description, d.solution = $solution
        RETURN id(d) as id
        """
        result = session.run(query, name=defect_name, cause_description=cause_description, solution=solution)
        record = result.single()
        defect_id = record['id']
        self.defect_cache[defect_name] = defect_id
        return defect_id
    
    def _get_or_create_competency(self, session, goal_name, skill_level, certification_standard):
        """获取或创建能力目标节点"""
        if goal_name in self.competency_cache:
            return self.competency_cache[goal_name]
        
        query = """
        MERGE (c:Competency_Goal {name: $name})
        SET c.skill_level = $skill_level, c.certification_standard = $certification_standard
        RETURN id(c) as id
        """
        result = session.run(query, name=goal_name, skill_level=skill_level, certification_standard=certification_standard)
        record = result.single()
        competency_id = record['id']
        self.competency_cache[goal_name] = competency_id
        return competency_id
    
    def _create_scene_rule_relation(self, session, scene_id, rule_id):
        """创建场景到规则的关系"""
        query = """
        MATCH (s:DFM_Scene), (r:DFM_Rule)
        WHERE id(s) = $scene_id AND id(r) = $rule_id
        MERGE (s)-[:CONTAINS_RULE]->(r)
        """
        session.run(query, scene_id=scene_id, rule_id=rule_id)
    
    def _create_rule_defect_relation(self, session, rule_id, defect_id):
        """创建规则到缺陷的关系"""
        query = """
        MATCH (r:DFM_Rule), (d:Defect_Case)
        WHERE id(r) = $rule_id AND id(d) = $defect_id
        MERGE (r)-[:PREVENTS_DEFECT]->(d)
        """
        session.run(query, rule_id=rule_id, defect_id=defect_id)
    
    def _create_competency_scene_relation(self, session, competency_id, scene_id):
        """创建能力目标到场景的关系"""
        query = """
        MATCH (c:Competency_Goal), (s:DFM_Scene)
        WHERE id(c) = $competency_id AND id(s) = $scene_id
        MERGE (c)-[:REQUIRES_KNOWLEDGE]->(s)
        """
        session.run(query, competency_id=competency_id, scene_id=scene_id)
    
    def _create_competency_rule_relation(self, session, competency_id, rule_id):
        """创建能力目标到规则的关系"""
        query = """
        MATCH (c:Competency_Goal), (r:DFM_Rule)
        WHERE id(c) = $competency_id AND id(r) = $rule_id
        MERGE (c)-[:REQUIRES_SKILL]->(r)
        """
        session.run(query, competency_id=competency_id, rule_id=rule_id)
    
    def _find_rule_by_content(self, session, content):
        """根据规则内容查找规则节点"""
        query = """
        MATCH (r:DFM_Rule)
        WHERE r.content CONTAINS $content
        RETURN id(r) as id
        LIMIT 1
        """
        result = session.run(query, content=content)
        record = result.single()
        return record['id'] if record else None
    
    def _find_scene_by_name(self, session, name):
        """根据场景名称查找场景节点"""
        query = """
        MATCH (s:DFM_Scene)
        WHERE s.name CONTAINS $name
        RETURN id(s) as id
        LIMIT 1
        """
        result = session.run(query, name=name)
        record = result.single()
        return record['id'] if record else None
    
    def _find_rules_by_keyword(self, session, keyword):
        """根据关键词查找规则节点"""
        query = """
        MATCH (r:DFM_Rule)
        WHERE r.content CONTAINS $keyword
        RETURN id(r) as id
        """
        result = session.run(query, keyword=keyword)
        return [record['id'] for record in result]
    
    def run(self):
        """运行数据导入流程"""
        try:
            logger.info("开始导入知识图谱数据")
            
            # 加载 Excel 文件
            excel_data = self.load_excel()
            
            # 处理各个 Sheet
            self.process_scene_rule_sheet(excel_data)
            self.process_defect_sheet(excel_data)
            self.process_competency_sheet(excel_data)
            
            logger.info("知识图谱数据导入完成")
        except Exception as e:
            logger.error(f"数据导入失败: {str(e)}")
            raise
        finally:
            self.close()

if __name__ == "__main__":
    initializer = GraphDataInitializer()
    initializer.run()
