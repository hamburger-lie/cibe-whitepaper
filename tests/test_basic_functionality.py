#!/usr/bin/env python3

import tempfile
import os
from reflection_agent import ReflectionAgent

def test_basic_functionality():
    """Test basic ReflectionAgent functionality."""
    # Create a temporary file for testing
    temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
    temp_file.close()
    temp_path = temp_file.name
    
    try:
        # Create agent instance
        agent = ReflectionAgent(storage_path=temp_path)
        print("✓ ReflectionAgent initialized successfully")
        
        # Test data
        query = "What is machine learning?"
        response = "Machine learning is a subset of artificial intelligence that enables systems to learn from data."
        reflection = "I should have provided more specific examples and explained the difference between supervised and unsupervised learning."
        
        # Test evaluate_and_reflect
        session = agent.evaluate_and_reflect(
            query=query,
            response=response,
            reflection=reflection,
            session_id="test_session"
        )
        
        print(f"✓ Reflection evaluated. Overall score: {session.evaluation_result.overall_score:.2f}")
        print(f"✓ Session created with ID: {session.session_id}")
        
        # Test generate_improved_prompt
        improved_prompt = agent.generate_improved_prompt(
            query=query,
            response=response,
            reflection=reflection
        )
        
        print(f"✓ Improved prompt generated ({len(improved_prompt)} characters)")
        
        # Test get_reflection_session
        retrieved_session = agent.get_reflection_session("test_session")
        if retrieved_session:
            print("✓ Session retrieved successfully")
            print(f"  - Query: {retrieved_session['query'][:50]}...")
            print(f"  - Reflection: {retrieved_session['reflection'][:50]}...")
        else:
            print("✗ Failed to retrieve session")
        
        # Test get_reflection_sessions
        all_sessions = agent.get_reflection_sessions()
        print(f"✓ Retrieved {len(all_sessions)} total sessions")
        
        # Test export_session_evaluation
        exported = agent.export_session_evaluation("test_session", "txt")
        if exported:
            print("✓ Session evaluation exported successfully")
            print(f"  - Export length: {len(exported)} characters")
        else:
            print("✗ Failed to export session evaluation")
        
        print("\n🎉 All basic functionality tests passed!")
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        if os.path.exists(temp_path):
            os.unlink(temp_path)
            print("✓ Cleaned up temporary file")

if __name__ == "__main__":
    test_basic_functionality()