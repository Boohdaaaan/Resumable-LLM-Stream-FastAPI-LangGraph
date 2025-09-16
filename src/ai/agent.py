from langgraph.prebuilt import create_react_agent
from langmem.short_term import SummarizationNode
from src.ai.tools import web_search_tool


class GraphBuilder:
    def __init__(self, llm, store, checkpointer):
        self.llm = llm
        self.store = store
        self.checkpointer = checkpointer

    def get_graph(self):
        prompt = "You are a helpful assistant."

        summarization_node = SummarizationNode(
            model=self.llm,
            max_tokens=170_000,
            max_tokens_before_summary=None,
            max_summary_tokens=8_000,
            input_messages_key="messages",
            output_messages_key="summarized_messages",
        )
        agent = create_react_agent(
            model=self.llm,
            tools=[web_search_tool],
            prompt=prompt,
            pre_model_hook=summarization_node,
            store=self.store,
            checkpointer=self.checkpointer,
        )
        return agent
