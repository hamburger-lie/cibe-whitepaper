#!/usr/bin/env python3
"""
简化的测试脚本 - 测试基本功能不依赖外部包
"""

import os
import sys
import json
import time
from pathlib import Path

def test_web_search_basic():
    """测试基本的web搜索功能"""
    print("=" * 50)
    print("Testing Web Search (Basic)")
    print("=" * 50)
    
    try:
        # 直接导入web_search模块
        sys.path.insert(0, '.')
        from web_search import WebSearch, quick_search
        
        print("✅ WebSearch module imported successfully")
        
        # 测试快速搜索函数
        print("\n1. Testing quick_search function...")
        results = quick_search("test query", limit=2)
        print(f"Quick search returned {len(results)} results")
        
        if results:
            print(f"Sample result: {results[0]['title']}")
        
        print("\n✅ Basic web search test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Web search test failed: {e}")
        return False


def test_reflection_basic():
    """测试基本的反思功能"""
    print("\n" + "=" * 50)
    print("Testing Reflection System (Basic)")
    print("=" * 50)
    
    try:
        # 测试反思存储
        from reflection_storage import ReflectionStorage
        
        print("1. Testing ReflectionStorage...")
        storage = ReflectionStorage("test_reflections.json")
        
        # 测试保存反思
        test_reflection = "这是一个测试反思内容"
        metadata = {"type": "test", "created_by": "test_script"}
        
        reflection_id = storage.save_reflection(test_reflection, metadata)
        print(f"✅ Reflection saved with ID: {reflection_id}")
        
        # 测试获取反思历史
        history = storage.get_reflection_history(5)
        print(f"✅ Retrieved {len(history)} reflection(s) from history")
        
        print("\n✅ Basic reflection system test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Reflection system test failed: {e}")
        return False


def test_configuration():
    """测试配置加载"""
    print("\n" + "=" * 50)
    print("Testing Configuration")
    print("=" * 50)
    
    try:
        # 测试环境变量加载
        config_values = {
            "ENABLE_REFLECTION": os.getenv("ENABLE_REFLECTION", "false"),
            "ENABLE_WEB_SEARCH": os.getenv("ENABLE_WEB_SEARCH", "false"),
            "ENABLE_DATA_VERIFICATION": os.getenv("ENABLE_DATA_VERIFICATION", "false"),
            "REFLECTION_STORAGE_PATH": os.getenv("REFLECTION_STORAGE_PATH", "reflections.json"),
            "WEB_SEARCH_TIMEOUT": os.getenv("WEB_SEARCH_TIMEOUT", "10"),
        }
        
        print("Configuration values:")
        for key, value in config_values.items():
            print(f"  {key}: {value}")
        
        # 检查必需的API密钥
        api_keys = {
            "DEEPSEEK_API_KEY": bool(os.getenv("DEEPSEEK_API_KEY")),
            "ARK_API_KEY": bool(os.getenv("ARK_API_KEY")),
        }
        
        print("\nAPI Key status:")
        for key, exists in api_keys.items():
            status = "✅ Configured" if exists else "❌ Not configured"
            print(f"  {key}: {status}")
        
        print("\n✅ Configuration test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False


def test_file_structure():
    """测试文件结构"""
    print("\n" + "=" * 50)
    print("Testing File Structure")
    print("=" * 50)
    
    try:
        required_files = [
            "proxy.py",
            "web_search.py",
            "reflection_agent.py",
            "reflection_criteria.py",
            "reflection_storage.py",
            "index.html",
            "requirements.txt",
            ".env.example",
            "README.md"
        ]
        
        missing_files = []
        
        for file in required_files:
            if os.path.exists(file):
                print(f"✅ {file} exists")
            else:
                print(f"❌ {file} missing")
                missing_files.append(file)
        
        if missing_files:
            print(f"\n❌ Missing {len(missing_files)} file(s): {', '.join(missing_files)}")
            return False
        else:
            print("\n✅ All required files present!")
            return True
            
    except Exception as e:
        print(f"❌ File structure test failed: {e}")
        return False


def test_imports():
    """测试模块导入"""
    print("\n" + "=" * 50)
    print("Testing Module Imports")
    print("=" * 50)
    
    try:
        modules_to_test = [
            ("web_search", "WebSearch"),
            ("reflection_storage", "ReflectionStorage"),
            ("reflection_criteria", "ReflectionCriteria"),
            ("reflection_agent", "ReflectionAgent"),
        ]
        
        failed_imports = []
        
        for module_name, class_name in modules_to_test:
            try:
                module = __import__(module_name, fromlist=[class_name])
                getattr(module, class_name)
                print(f"✅ {module_name}.{class_name} imported successfully")
            except Exception as e:
                print(f"❌ {module_name}.{class_name} import failed: {e}")
                failed_imports.append(module_name)
        
        if failed_imports:
            print(f"\n❌ {len(failed_imports)} module(s) failed to import")
            return False
        else:
            print("\n✅ All modules imported successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        return False


def test_env_setup():
    """测试环境设置"""
    print("\n" + "=" * 50)
    print("Testing Environment Setup")
    print("=" * 50)
    
    try:
        # 检查Python版本
        python_version = sys.version_info
        print(f"Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
        
        if python_version.major >= 3 and python_version.minor >= 8:
            print("✅ Python version is compatible")
        else:
            print("❌ Python version may not be compatible")
            return False
        
        # 检查工作目录
        print(f"Working directory: {os.getcwd()}")
        
        # 检查是否有.env文件
        if os.path.exists(".env"):
            print("✅ .env file exists")
        else:
            print("⚠️  .env file not found - using environment defaults")
        
        print("\n✅ Environment setup test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Environment setup test failed: {e}")
        return False


def main():
    """运行所有测试"""
    print("Starting CIBE Whitepaper System Basic Tests")
    print("=" * 60)
    
    # 运行测试
    tests = [
        ("File Structure", test_file_structure),
        ("Environment Setup", test_env_setup),
        ("Configuration", test_configuration),
        ("Module Imports", test_imports),
        ("Web Search", test_web_search_basic),
        ("Reflection System", test_reflection_basic),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # 汇总
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
        
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {passed + failed}, Passed: {passed}, Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All tests passed!")
        return True
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please check the output above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)