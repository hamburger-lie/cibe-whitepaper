"""
Web Search Module
Provides functionality to search the web for information to ensure data accuracy in reports.
"""

import os
import requests
import json
from typing import List, Dict, Optional, Union
from datetime import datetime
import time
import re
from dotenv import load_dotenv

load_dotenv()

SCRAPFLY_API_KEY = os.getenv("SCRAPFLY_API_KEY", "").strip()
SCRAPFLY_ENDPOINT = "https://api.scrapfly.io/scrape"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


SCRAPFLY_CACHE_TTL = _int_env("SCRAPFLY_CACHE_TTL", 604800)
SCRAPFLY_COST_BUDGET_SEARCH = _int_env("SCRAPFLY_COST_BUDGET_SEARCH", 3)


class WebSearch:
    """
    A web search class that uses DuckDuckGo API for real-time web searches.
    Provides functionality to search for information and verify data accuracy.
    """
    
    def __init__(self, timeout: int = 10):
        """
        Initialize the WebSearch class.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.base_url = "https://api.duckduckgo.com/"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def _get_json(self, url: str, params: Dict[str, Union[str, int]]) -> Dict:
        if SCRAPFLY_API_KEY:
            from urllib.parse import urlencode

            full_url = f"{url}?{urlencode(params, doseq=True)}"
            response = self.session.get(
                SCRAPFLY_ENDPOINT,
                params={
                    "key": SCRAPFLY_API_KEY,
                    "url": full_url,
                    "asp": "true",
                    "retry": "true",
                    "country": "cn",
                    "cache": "true",
                    "cache_ttl": str(SCRAPFLY_CACHE_TTL),
                    "cost_budget": str(SCRAPFLY_COST_BUDGET_SEARCH),
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            print(
                "[WebSearch][Scrapfly] "
                f"cost={response.headers.get('X-Scrapfly-Api-Cost', '-')} "
                f"remaining={response.headers.get('X-Scrapfly-Remaining-Api-Credit', '-')}"
            )
            content = response.json().get("result", {}).get("content", "") or "{}"
            return json.loads(content)

        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Search the web for a given query using DuckDuckGo API.
        
        Args:
            query: The search query
            limit: Maximum number of results to return
            
        Returns:
            List of search results with title, url, and snippet
        """
        if not query:
            raise ValueError("Query cannot be empty")
        
        if limit <= 0:
            raise ValueError("Limit must be positive")
        
        try:
            # Using DuckDuckGo Instant Answer API
            params = {
                'q': query,
                'format': 'json',
                'no_html': 1,
                'skip_disambig': 1
            }
            
            data = self._get_json(self.base_url, params)
            
            # Extract results from DuckDuckGo API
            results = []
            
            # Add Related Topics (organic search results)
            if 'RelatedTopics' in data:
                for topic in data['RelatedTopics'][:limit]:
                    if 'Text' in topic and 'FirstURL' in topic:
                        # Clean and extract information
                        text = topic['Text']
                        url = topic['FirstURL']
                        
                        # Extract title from text if it's in the format "Title • URL"
                        if ' • ' in text:
                            title = text.split(' • ')[0]
                            snippet = text.split(' • ')[1] if ' • ' in text and len(text.split(' • ')) > 1 else ""
                        else:
                            title = text[:80] + "..." if len(text) > 80 else text
                            snippet = ""
                        
                        results.append({
                            "title": title,
                            "url": url,
                            "snippet": snippet,
                            "source": "duckduckgo"
                        })
            
            # If we don't have enough results, try additional search
            if len(results) < limit:
                additional_params = {
                    'q': query,
                    'format': 'json',
                    'p': 1  # Page parameter
                }
                
                add_data = self._get_json("https://api.duckduckgo.com/", additional_params)
                
                if 'Results' in add_data:
                    for result in add_data['Results'][:limit - len(results)]:
                        results.append({
                            "title": result.get('Title', 'No Title'),
                            "url": result.get('FirstURL', '#'),
                            "snippet": result.get('Text', ''),
                            "source": "duckduckgo"
                        })
            
            return results[:limit]
            
        except requests.exceptions.RequestException as e:
            print(f"[WebSearch] Search failed: {e}")
            # Return fallback results
            return self._get_fallback_results(query, limit)
        except Exception as e:
            print(f"[WebSearch] Unexpected error: {e}")
            return self._get_fallback_results(query, limit)
    
    def search_news(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Search for news articles using DuckDuckGo.
        
        Args:
            query: The search query
            limit: Maximum number of results to return
            
        Returns:
            List of news search results
        """
        if not query:
            raise ValueError("Query cannot be empty")
        
        try:
            # Use news-specific search
            params = {
                'q': f"{query} news",
                'format': 'json',
                'no_html': 1
            }
            
            data = self._get_json(self.base_url, params)
            results = []
            
            if 'RelatedTopics' in data:
                for topic in data['RelatedTopics'][:limit]:
                    if 'Text' in topic and 'FirstURL' in topic:
                        text = topic['Text']
                        url = topic['FirstURL']
                        
                        # Extract title
                        if ' • ' in text:
                            title = text.split(' • ')[0]
                            snippet = text.split(' • ')[1] if len(text.split(' • ')) > 1 else ""
                        else:
                            title = text[:80] + "..." if len(text) > 80 else text
                            snippet = ""
                        
                        results.append({
                            "title": f"[News] {title}",
                            "url": url,
                            "snippet": snippet,
                            "source": "duckduckgo_news"
                        })
            
            return results[:limit]
            
        except Exception as e:
            print(f"[WebSearch] News search failed: {e}")
            return []
    
    def verify_data_point(self, data_point: str, context: str = "") -> Dict[str, Union[bool, str, List[str]]]:
        """
        Verify a specific data point by searching for it online.
        
        Args:
            data_point: The data point to verify
            context: Optional context for the search
            
        Returns:
            Dictionary with verification results
        """
        if not data_point:
            return {
                "verified": False,
                "confidence": 0,
                "sources": [],
                "message": "No data point provided"
            }
        
        # Construct search query
        query = f"{data_point} {context}".strip()
        
        try:
            # Search for the data point
            results = self.search(query, limit=5)
            
            if not results:
                return {
                    "verified": False,
                    "confidence": 0,
                    "sources": [],
                    "message": "No search results found"
                }
            
            # Check if results support the data point
            supporting_sources = []
            conflicting_sources = []
            
            for result in results:
                # Simple keyword matching to determine if result supports the data point
                text_lower = (result['title'] + ' ' + result['snippet']).lower()
                data_point_lower = data_point.lower()
                
                # Check for supporting evidence
                if any(keyword in text_lower for keyword in [
                    'data', 'statistics', 'report', 'study', 'research', 'survey',
                    'according to', 'shows', 'indicates', 'reveals'
                ]):
                    supporting_sources.append(result)
                
                # Check for conflicting information
                if any(keyword in text_lower for keyword in [
                    'contradicts', 'disputes', 'debunks', 'incorrect', 'wrong',
                    'not', 'however', 'but'
                ]):
                    conflicting_sources.append(result)
            
            # Calculate confidence score
            confidence = len(supporting_sources) * 20  # 20 points per supporting source
            if conflicting_sources:
                confidence -= len(conflicting_sources) * 10  # 10 points per conflicting source
            
            confidence = max(0, min(100, confidence))  # Clamp between 0-100
            
            # Determine verification status
            if confidence >= 70:
                verified = True
                status = "High confidence"
            elif confidence >= 40:
                verified = True
                status = "Moderate confidence"
            else:
                verified = False
                status = "Low confidence" if confidence > 0 else "No confidence"
            
            return {
                "verified": verified,
                "confidence": confidence,
                "status": status,
                "supporting_sources": supporting_sources,
                "conflicting_sources": conflicting_sources,
                "sources": results,
                "message": f"Found {len(supporting_sources)} supporting and {len(conflicting_sources)} conflicting sources"
            }
            
        except Exception as e:
            return {
                "verified": False,
                "confidence": 0,
                "sources": [],
                "message": f"Verification failed: {str(e)}"
            }
    
    def get_search_trends(self) -> List[str]:
        """
        Get current search trends using DuckDuckGo.
        
        Returns:
            List of trending search terms
        """
        try:
            params = {
                'q': '',
                'format': 'json',
                'no_html': 1
            }
            
            response = self.session.get(self.base_url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract trending topics
            trends = []
            if 'RelatedTopics' in data:
                for topic in data['RelatedTopics'][:10]:  # Top 10 trends
                    if 'Text' in topic:
                        text = topic['Text']
                        # Extract trend name
                        if ' • ' in text:
                            trend_name = text.split(' • ')[0]
                            trends.append(trend_name)
            
            return trends
            
        except Exception as e:
            print(f"[WebSearch] Trends fetch failed: {e}")
            return []
    
    def _get_fallback_results(self, query: str, limit: int) -> List[Dict[str, str]]:
        """
        Fallback method when web search fails.
        
        Args:
            query: The search query
            limit: Maximum number of results to return
            
        Returns:
            List of fallback search results
        """
        results = []
        for i in range(min(limit, 5)):
            results.append({
                "title": f"Result {i+1}: {query}",
                "url": f"https://example.com/result/{i+1}",
                "snippet": f"This is a fallback result for {query}. Actual web search failed.",
                "source": "fallback"
            })
        return results
    
    def search_academic(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Search for academic papers (simplified implementation).
        
        Args:
            query: The search query
            limit: Maximum number of results to return
            
        Returns:
            List of academic search results
        """
        try:
            # Use Google Scholar-like search
            academic_query = f"{query} site:scholar.google.com"
            results = self.search(academic_query, limit)
            
            # Mark as academic results
            for result in results:
                result['source'] = 'academic'
                result['title'] = f"[Academic] {result['title']}"
            
            return results
            
        except Exception as e:
            print(f"[WebSearch] Academic search failed: {e}")
            return []


# Convenience functions for easy integration
def quick_search(query: str, limit: int = 10) -> List[Dict[str, str]]:
    """Quick search function for simple use cases."""
    searcher = WebSearch()
    return searcher.search(query, limit)


def verify_data(data_point: str, context: str = "") -> Dict[str, Union[bool, str, List[str]]]:
    """Quick data verification function for simple use cases."""
    searcher = WebSearch()
    return searcher.verify_data_point(data_point, context)


def get_search_trends() -> List[str]:
    """Get trending search terms."""
    searcher = WebSearch()
    return searcher.get_search_trends()
