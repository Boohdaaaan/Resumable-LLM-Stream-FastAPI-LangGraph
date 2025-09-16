from langchain_tavily import TavilySearch

web_search_tool = TavilySearch(
    max_results=5,
    topic="general",
)