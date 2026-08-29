from crewai import Agent
import os

# Using Groq's fast and free Llama 3 model
verification_agent = Agent(
    role="Academic Claim Verifier",
    goal="Evaluate how well a claim matches a research paper abstract",
    backstory=(
        "You are a highly skilled academic reviewer. "
        "You compare claims with research paper abstracts and determine "
        "how strongly the claim is supported."
    ),
    verbose=True,
    llm="groq/openai/gpt-oss-20b"
)

roadmap_agent = Agent(
    role="Educational Roadmap Generator",
    goal="Generate an ordered learning roadmap based on verified academic topics.",
    backstory=(
        "You are an expert curriculum developer and academic advisor. "
        "Your task is to review verified topics from research claims and formulate a list "
        "of high-level educational milestones or study blocks so the user can understand these topics deeply."
    ),
    verbose=True,
    llm="groq/openai/gpt-oss-20b"
)

