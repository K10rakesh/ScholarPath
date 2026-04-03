from crewai.tools import BaseTool
import urllib.request
import urllib.parse
import json
from typing import Type
from pydantic import BaseModel, Field

class SemanticScholarSearchInput(BaseModel):
    """Input schema for SemanticScholarTool."""
    query: str = Field(..., description="The title or keywords of the paper to search for.")

class SemanticScholarTool(BaseTool):
    name: str = "Semantic Scholar Paper Search Tool"
    description: str = (
        "Search for an academic paper by title or keywords to retrieve its abstract and details. "
        "Useful for verifying claims from citations against the Semantic Scholar database."
    )
    args_schema: Type[BaseModel] = SemanticScholarSearchInput

    def _run(self, query: str) -> str:
        try:
            query = urllib.parse.quote(query)
            # Searching for papers and requesting abstract and title
            url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={query}&limit=1&fields=title,authors,year,abstract"
            
            req = urllib.request.Request(url, headers={'User-Agent': 'ScholarPath-Bot'})
            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode())
                    if data.get('data') and len(data['data']) > 0:
                        paper = data['data'][0]
                        
                        abstract = paper.get('abstract') or "No abstract available"
                        title = paper.get('title')
                        year = paper.get('year')
                        return f"Title: {title}\nYear: {year}\nAbstract: {abstract}"
                    return f"No papers found in Semantic Scholar for: {urllib.parse.unquote(query)}"
                else:
                    return "Error fetching from Semantic Scholar."
        except Exception as e:
            return f"Error using Semantic Scholar Tool: {str(e)}"

class ArxivSearchInput(BaseModel):
    """Input schema for ArxivTool."""
    query: str = Field(..., description="The query to search arXiv to find a paper's abstract.")

class ArxivTool(BaseTool):
    name: str = "arXiv Paper Search Tool"
    description: str = (
        "Search for an academic paper in the arXiv open-access database. "
        "Useful for fetching abstracts of physics, computer science, and math papers to verify citations."
    )
    args_schema: Type[BaseModel] = ArxivSearchInput

    def _run(self, query: str) -> str:
        try:
            query = urllib.parse.quote(query)
            url = f"http://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results=1"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as response:
                xml_data = response.read().decode('utf-8')
                
                # Super basic XML abstract extraction to avoid external dependencies like BeautifulSoup initially
                if "<summary>" in xml_data:
                    start = xml_data.find("<summary>") + len("<summary>")
                    end = xml_data.find("</summary>", start)
                    abstract = xml_data[start:end].strip()
                    
                    title_start = xml_data.find("<title>", start - 500)
                    title_start = title_start + len("<title>")
                    title_end = xml_data.find("</title>", title_start)
                    title = xml_data[title_start:title_end].strip()
                    
                    return f"Title: {title}\nAbstract: {abstract}"
                return f"No papers found in arXiv for: {urllib.parse.unquote(query)}"
        except Exception as e:
            return f"Error using arXiv Tool: {str(e)}"
