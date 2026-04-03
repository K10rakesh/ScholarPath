from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from scholarpath.tools.custom_tool import SemanticScholarTool, ArxivTool

# Set up local Ollama LLM
# Make sure you have Ollama running locally and have pulled a model (e.g., `ollama run llama3`)
local_llm = LLM(
    model="ollama/llama3.2",
    base_url="http://localhost:11434"
)

# If you want to run a snippet of code before or after the crew starts,
# you can use the @before_kickoff and @after_kickoff decorators
# https://docs.crewai.com/concepts/crews#example-crew-class-with-decorators

@CrewBase
class Scholarpath():
    """Scholarpath Trust Gate Crew"""

    agents: list[BaseAgent]
    tasks: list[Task]

    # Learn more about YAML configuration files here:
    # Agents: https://docs.crewai.com/concepts/agents#yaml-configuration-recommended
    # Tasks: https://docs.crewai.com/concepts/tasks#yaml-configuration-recommended
    
    @agent
    def claim_extractor(self) -> Agent:
        return Agent(
            config=self.agents_config['claim_extractor'], # type: ignore[index]
            verbose=True,
            llm=local_llm
        )

    @agent
    def fact_checker(self) -> Agent:
        return Agent(
            config=self.agents_config['fact_checker'], # type: ignore[index]
            verbose=True,
            # Commented out Semantic Scholar for now as requested
            tools=[ArxivTool()],
            llm=local_llm
        )

    @agent
    def roadmap_generator(self) -> Agent:
        return Agent(
            config=self.agents_config['roadmap_generator'], # type: ignore[index]
            verbose=True,
            llm=local_llm
        )

    @task
    def extraction_task(self) -> Task:
        return Task(
            config=self.tasks_config['extraction_task'], # type: ignore[index]
        )

    @task
    def verification_task(self) -> Task:
        return Task(
            config=self.tasks_config['verification_task'], # type: ignore[index]
            output_file='fact_check_report.json'
        )

    @task
    def roadmap_task(self) -> Task:
        return Task(
            config=self.tasks_config['roadmap_task'], # type: ignore[index]
            output_file='learning_roadmap.md'
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Scholarpath crew"""
        return Crew(
            agents=[self.claim_extractor(), self.fact_checker(), self.roadmap_generator()], # type: ignore
            tasks=[self.extraction_task(), self.verification_task(), self.roadmap_task()], # type: ignore
            process=Process.sequential,
            verbose=True,
        )
