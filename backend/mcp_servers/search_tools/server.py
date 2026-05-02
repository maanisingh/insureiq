import os
import httpx
from typing import Optional

try:
    from fastmcp import FastMCP
except ImportError:
    from mcp import FastMCP

mcp = FastMCP("search-tools")

@mcp.tool()
def web_search(query: str, limit: int = 5) -> list[dict]:
    """Search the web for insurance-related information
    
    Use this to find current information, news, regulations,
    or topics not in the knowledge base.
    
    Args:
        query: Search query
        limit: Number of results (default: 5)
    """
    # Using DuckDuckGo API (free, no key required)
    # For production, consider Tavily, Serper, or Brave Search
    
    try:
        url = "https://html.duckduckgo.com/html/"
        data = {"q": query, "b": limit}
        
        response = httpx.post(url, data=data, timeout=10.0)
        
        if response.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, "html.parser")
            
            results = []
            for result in soup.select(".result"):
                title_elem = result.select_one(".result__title")
                snippet_elem = result.select_one(".result__snippet")
                link_elem = result.select_one("a.result__a")
                
                if title_elem:
                    results.append({
                        "title": title_elem.get_text(strip=True),
                        "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                        "url": link_elem.get("href", "") if link_elem else ""
                    })
                    
                    if len(results) >= limit:
                        break
            
            return results
        else:
            return [{"error": f"Search failed with status {response.status_code}"}]
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def search_insurance_news(query: str, limit: int = 5) -> list[dict]:
    """Search for insurance industry news
    
    Args:
        query: Search query
        limit: Number of results (default: 5)
    """
    return web_search(f"insurance {query} news", limit)

@mcp.tool()
def search_regulations(query: str, country: str = "US") -> list[dict]:
    """Search for insurance regulations
    
    Args:
        query: Regulation topic
        country: Country code (default: US)
    """
    return web_search(f"insurance {query} regulations {country}", 5)

@mcp.tool()
def health_check() -> dict:
    """Health check for the search tools server"""
    try:
        response = httpx.get("https://html.duckduckgo.com/html/", timeout=5.0)
        return {"status": "healthy", "duckduckgo": "ok" if response.status_code == 200 else "error"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import sys
    
    transport = "stdio"
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        transport = "http"
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8004
    
    if transport == "http":
        mcp.run(transport="http", port=port)
    else:
        mcp.run(transport="stdio")