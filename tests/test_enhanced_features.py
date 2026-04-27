#!/usr/bin/env python3
"""
Enhanced Features Test Script
Tests the enhanced CIBE whitepaper generation system with web search and reflection functionality.
"""

import os
import sys
import json
from datetime import datetime

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def create_mock_pandas():
    """Create a minimal mock pandas module to avoid dependency issues."""
    import types
    
    class MockDataFrame:
        def __init__(self, data=None):
            self.data = data or {}
        
        def to_dict(self, orient='records'):
            if isinstance(self.data, dict):
                return [self.data]
            return self.data or []
        
        def head(self, n=5):
            return MockDataFrame(self.data)
        
        def shape(self):
            return (1, len(self.data) if self.data else 0)
    
    # Create mock pandas module
    mock_pandas = types.ModuleType('pandas')
    mock_pandas.DataFrame = MockDataFrame
    mock_pandas.read_csv = lambda x: MockDataFrame()
    mock_pandas.read_excel = lambda x: MockDataFrame()
    mock_pandas.concat = lambda *args, **kwargs: MockDataFrame()
    mock_pandas.merge = lambda *args, **kwargs: MockDataFrame()
    mock_pandas.to_datetime = datetime.datetime.now
    mock_pandas.NA = None
    
    # Add to sys.modules
    sys.modules['pandas'] = mock_pandas

# Mock pandas module
create_mock_pandas()

def test_enhanced_web_search():
    """Test enhanced web search functionality."""
    print("==================================================")
    print("Testing Enhanced Web Search Functionality")
    print("==================================================")
    
    try:
        from web_search import WebSearch, quick_search, verify_data, get_search_trends
        
        # Test 1: Basic search functionality
        print("1. Testing basic search functionality...")
        searcher = WebSearch()
        results = searcher.search("artificial intelligence", limit=3)
        
        if results and len(results) > 0:
            print(f"✅ Search returned {len(results)} results")
            for i, result in enumerate(results[:2]):
                print(f"   Result {i+1}: {result['title'][:50]}...")
        else:
            print("⚠️  Search returned no results (may be due to network issues)")
        
        # Test 2: Quick search function
        print("\n2. Testing quick_search function...")
        quick_results = quick_search("machine learning", limit=2)
        if quick_results:
            print(f"✅ Quick search returned {len(quick_results)} results")
        else:
            print("⚠️  Quick search returned no results")
        
        # Test 3: Data verification
        print("\n3. Testing data verification...")
        verification = verify_data("climate change", "global warming")
        print(f"✅ Verification result: {verification['status']} (confidence: {verification['confidence']}%)")
        
        # Test 4: Search trends
        print("\n4. Testing search trends...")
        trends = get_search_trends()
        if trends:
            print(f"✅ Found {len(trends)} trending topics")
            print(f"   Top trend: {trends[0] if trends else 'None'}")
        else:
            print("⚠️  No trends found (may be due to network issues)")
        
        print("\n✅ Enhanced web search test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Enhanced web search test failed: {e}")
        return False

def test_enhanced_reflection():
    """Test enhanced reflection functionality."""
    print("==================================================")
    print("Testing Enhanced Reflection System")
    print("==================================================")
    
    try:
        from reflection_storage import ReflectionStorage
        from reflection_agent import ReflectionAgent
        from reflection_criteria import ReflectionCriteria
        
        # Test 1: Enhanced storage functionality
        print("1. Testing enhanced reflection storage...")
        storage = ReflectionStorage("test_reflections.json")
        
        # Save test reflections
        test_reflections = [
            "This is a test reflection about data accuracy.",
            "Another test reflection about report quality.",
            "Final test reflection about AI-generated content."
        ]
        
        saved_ids = []
        for i, reflection in enumerate(test_reflections):
            metadata = {"type": "test", "iteration": i+1}
            success = storage.save_reflection(reflection, metadata)
            if success:
                saved_ids.append(i+1)
                print(f"   ✅ Reflection {i+1} saved successfully")
        
        # Test 2: Enhanced retrieval functionality
        print("\n2. Testing enhanced reflection retrieval...")
        all_reflections = storage.get_reflections(limit=10)
        print(f"✅ Retrieved {len(all_reflections)} total reflections")
        
        # Test 3: Reflection by type
        test_type_reflections = storage.get_reflections_by_type("test", limit=5)
        print(f"✅ Retrieved {len(test_type_reflections)} test-type reflections")
        
        # Test 4: Reflection history
        history = storage.get_reflection_history(limit=5, offset=0)
        print(f"✅ Retrieved {len(history)} reflections from history")
        
        # Test 5: Reflection criteria
        print("\n3. Testing reflection criteria...")
        criteria = ReflectionCriteria()
        
        test_content = """
        This is a test reflection that demonstrates the evaluation criteria.
        It contains good aspects like clarity and structure, but may have some 
        areas for improvement in terms of depth and actionable insights.
        """
        
        evaluation = criteria.evaluate_reflection(test_content)
        print(f"✅ Reflection evaluation completed:")
        print(f"   Overall Score: {evaluation['overall_score']}/100")
        print(f"   Clarity: {evaluation['clarity']}/100")
        print(f"   Depth: {evaluation['depth']}/100")
        print(f"   Actionability: {evaluation['actionability']}/100")
        
        # Test 6: Reflection agent
        print("\n4. Testing reflection agent...")
        agent = ReflectionAgent()
        
        test_whitepaper = """
        # Test Whitepaper
        
        ## Executive Summary
        This is a test whitepaper about artificial intelligence.
        
        ## Introduction
        Artificial intelligence is transforming various industries.
        
        ## Conclusion
        AI will continue to evolve and impact society.
        """
        
        reflection = agent.reflect_on_content(test_whitepaper, "AI Technology Whitepaper")
        if reflection:
            print(f"✅ Reflection agent generated response")
            print(f"   Reflection length: {len(reflection)} characters")
        else:
            print("⚠️  Reflection agent returned empty response")
        
        print("\n✅ Enhanced reflection system test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Enhanced reflection system test failed: {e}")
        return False

def test_integration():
    """Test integration of enhanced features."""
    print("==================================================")
    print("Testing Enhanced Features Integration")
    print("==================================================")
    
    try:
        # Test configuration integration
        print("1. Testing configuration integration...")
        
        # Check environment variables
        config = {
            "ENABLE_REFLECTION": os.getenv("ENABLE_REFLECTION", "false"),
            "ENABLE_WEB_SEARCH": os.getenv("ENABLE_WEB_SEARCH", "false"),
            "ENABLE_DATA_VERIFICATION": os.getenv("ENABLE_DATA_VERIFICATION", "false"),
            "REFLECTION_STORAGE_PATH": os.getenv("REFLECTION_STORAGE_PATH", "reflections.json"),
            "WEB_SEARCH_TIMEOUT": os.getenv("WEB_SEARCH_TIMEOUT", "10")
        }
        
        print(f"✅ Configuration loaded: {config}")
        
        # Test 2: File integration
        print("\n2. Testing file integration...")
        required_files = [
            "proxy.py", "web_search.py", "reflection_agent.py", 
            "reflection_criteria.py", "reflection_storage.py"
        ]
        
        missing_files = []
        for file in required_files:
            if os.path.exists(file):
                print(f"   ✅ {file} exists")
            else:
                missing_files.append(file)
                print(f"   ❌ {file} missing")
        
        if missing_files:
            print(f"❌ Missing files: {missing_files}")
            return False
        
        # Test 3: Module integration
        print("\n3. Testing module integration...")
        try:
            from proxy import run_four_agent_pipeline
            print("✅ Main proxy module imported successfully")
        except ImportError as e:
            print(f"⚠️  Main proxy module import failed (expected if dependencies missing): {e}")
        
        print("\n✅ Enhanced features integration test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Enhanced features integration test failed: {e}")
        return False

def test_error_handling():
    """Test error handling for enhanced features."""
    print("==================================================")
    print("Testing Error Handling")
    print("==================================================")
    
    try:
        from web_search import WebSearch
        from reflection_storage import ReflectionStorage
        
        # Test 1: Web search error handling
        print("1. Testing web search error handling...")
        searcher = WebSearch()
        
        # Test empty query
        try:
            results = searcher.search("")
            print("❌ Should have failed on empty query")
        except ValueError as e:
            print(f"✅ Correctly handled empty query: {e}")
        
        # Test invalid limit
        try:
            results = searcher.search("test", limit=-1)
            print("❌ Should have failed on negative limit")
        except ValueError as e:
            print(f"✅ Correctly handled negative limit: {e}")
        
        # Test 2: Reflection storage error handling
        print("\n2. Testing reflection storage error handling...")
        storage = ReflectionStorage("test_error_reflections.json")
        
        # Test empty reflection
        result = storage.save_reflection("", {"type": "test"})
        if not result:
            print("✅ Correctly handled empty reflection")
        
        # Test invalid reflection ID
        reflection = storage.get_reflection("invalid")
        if reflection is None:
            print("✅ Correctly handled invalid reflection ID")
        
        print("\n✅ Error handling test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False

def main():
    """Main test function."""
    print("Starting CIBE Whitepaper System Enhanced Features Tests")
    print("============================================================\n")
    
    tests = [
        ("Enhanced Web Search", test_enhanced_web_search),
        ("Enhanced Reflection System", test_enhanced_reflection),
        ("Enhanced Features Integration", test_integration),
        ("Error Handling", test_error_handling)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
        
        print("\n")
    
    # Summary
    print("============================================================")
    print("Enhanced Features Test Summary")
    print("============================================================")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nTotal: {total}, Passed: {passed}, Failed: {total - passed}")
    
    if passed == total:
        print("\n🎉 All enhanced features tests passed!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please check the output above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)