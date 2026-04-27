#!/usr/bin/env python3
"""
Web Search Usage Examples
演示如何在项目中使用 WebSearcher 类
"""

import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 导入 WebSearcher
from web_search import WebSearcher

def example_basic_search():
    """基本搜索示例"""
    print("=== 基本搜索示例 ===")
    
    # 初始化搜索器（需要配置 SERPAPI_KEY）
    try:
        searcher = WebSearcher()
        
        # 执行搜索
        results = searcher.search("美业 市场趋势", num_results=5)
        
        print(f"找到 {len(results)} 个结果:")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result.get('title', 'N/A')}")
            print(f"   链接: {result.get('link', 'N/A')}")
            print(f"   摘要: {result.get('snippet', 'N/A')[:100]}...")
            print()
            
    except Exception as e:
        print(f"搜索失败: {e}")

def example_data_verification():
    """数据验证示例"""
    print("=== 数据验证示例 ===")
    
    try:
        searcher = WebSearcher()
        
        # 验证数据点
        verification = searcher.verify_data_point(
            "中国 化妆品 市场规模",
            "中国化妆品市场规模超过5000亿元",
            num_results=5
        )
        
        print(f"验证结果: {verification['message']}")
        print(f"置信度: {verification['confidence']:.2f}")
        print(f"验证状态: {'通过' if verification['verified'] else '未通过'}")
        print(f"相关源数量: {verification['relevant_sources']}")
        
        if verification['verified'] and verification['relevant_sources_details']:
            print("\n相关来源:")
            for source in verification['relevant_sources_details'][:3]:
                print(f"- {source['title']} (相关性: {source['relevance_score']:.2f})")
                print(f"  链接: {source['link']}")
                
    except Exception as e:
        print(f"验证失败: {e}")

def example_search_summary():
    """搜索摘要示例"""
    print("=== 搜索摘要示例 ===")
    
    try:
        searcher = WebSearcher()
        
        # 获取搜索摘要
        summary = searcher.get_search_summary("护肤品 成分分析", num_results=10)
        
        print(f"查询: {summary['query']}")
        print(f"总结果数: {summary['total_results']}")
        print(f"摘要: {summary['summary']}")
        
        if summary['common_keywords']:
            print(f"\n常见关键词:")
            for keyword, freq in summary['common_keywords'][:5]:
                print(f"- {keyword}: {freq}次")
                
    except Exception as e:
        print(f"摘要生成失败: {e}")

def example_with_existing_project():
    """与现有项目集成示例"""
    print("=== 与现有项目集成示例 ===")
    
    # 模拟在白皮书生成过程中使用网络搜索
    def enhance_whitepaper_with_web_data():
        """使用网络搜索增强白皮书内容"""
        try:
            searcher = WebSearcher()
            
            # 白皮书主题
            topic = "功效护肤品市场分析"
            
            # 搜索相关数据
            market_data = searcher.search("功效护肤品 市场规模 数据", num_results=5)
            trend_data = searcher.search("功效护肤品 发展趋势", num_results=5)
            
            # 验证关键数据点
            verification = searcher.verify_data_point(
                "功效护肤品 市场增长",
                "功效护肤品市场年增长率超过20%",
                num_results=3
            )
            
            # 构建增强内容
            enhanced_content = {
                "topic": topic,
                "market_data": market_data,
                "trend_data": trend_data,
                "data_verification": verification,
                "web_sources_count": len(market_data) + len(trend_data)
            }
            
            print(f"白皮书主题: {topic}")
            print(f"网络数据源数量: {enhanced_content['web_sources_count']}")
            print(f"数据验证状态: {verification['message']}")
            
            return enhanced_content
            
        except Exception as e:
            print(f"数据增强失败: {e}")
            return None
    
    # 执行集成示例
    result = enhance_whitepaper_with_web_data()
    if result:
        print(f"✓ 白皮书数据增强完成")

if __name__ == "__main__":
    print("Web Search 使用示例")
    print("=" * 50)
    
    # 检查 API Key 配置
    if not os.getenv("SERPAPI_KEY"):
        print("⚠️  警告: SERPAPI_KEY 未配置，请确保 .env 文件中设置了 SERPAPI_KEY")
        print("   取消注释以下示例以测试功能")
        return
    
    # 运行示例
    example_basic_search()
    print()
    
    example_data_verification()
    print()
    
    example_search_summary()
    print()
    
    example_with_existing_project()