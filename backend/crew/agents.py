from crewai import Agent

verification_agent = Agent(
    role="Academic Claim Verifier",
    goal="Evaluate how well a claim matches a research paper abstract",
    backstory=(
        "You are a highly skilled academic reviewer. "
        "You compare claims with research paper abstracts and determine "
        "how strongly the claim is supported."
    ),
    verbose=True
)
