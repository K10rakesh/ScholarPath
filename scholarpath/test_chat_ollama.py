import os
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

print("Host:", os.getenv("OLLAMA_HOST"))

llm = ChatOllama(
    model="llama3.2",
    temperature=0.1,
    base_url=f"http://{os.environ.get('OLLAMA_HOST', '127.0.0.1:11434')}"
)

print("Invoking...")
res = llm.invoke([HumanMessage(content="hello")])
print("Res:", res)
