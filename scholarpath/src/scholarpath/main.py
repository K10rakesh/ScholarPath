#!/usr/bin/env python
import sys
import warnings

from datetime import datetime

from scholarpath.crew import Scholarpath

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

# This main file is intended to be a way for you to run your
# crew locally, so refrain from adding unnecessary logic into this file.
# Replace with inputs you want to test with, it will automatically
# interpolate any tasks and agents information

def run():
    """
    Run the crew.
    """
    import sys
    
    pdf_text = (
        "Claim 1: Transformers revolutionized NLP architectures, showing that attention mechanisms "
        "alone can achieve state-of-the-art results in translation tasks [Vaswani et al., 2017]. "
        "Claim 2: The moon is made of green cheese, a fact recently proven in lunar studies "
        "[Nonsense et al., 2023]."
    )
    
    if len(sys.argv) > 1 and sys.argv[1].endswith('.pdf'):
        try:
            import PyPDF2
            print(f"Extracting text from {sys.argv[1]}...")
            with open(sys.argv[1], 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                pdf_text = "".join([page.extract_text() for page in reader.pages if page.extract_text()])
        except ImportError:
            print("PyPDF2 is not installed. Running with default sample text. Run `pip install PyPDF2` to enable PDF support.")
        except Exception as e:
            print(f"Failed to read PDF: {e}. Running with default sample text.")

    inputs = {
        'pdf_text': pdf_text
    }

    try:
        Scholarpath().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")


def train():
    """
    Train the crew for a given number of iterations.
    """
    inputs = {
        "topic": "AI LLMs",
        'current_year': str(datetime.now().year)
    }
    try:
        Scholarpath().crew().train(n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")

def replay():
    """
    Replay the crew execution from a specific task.
    """
    try:
        Scholarpath().crew().replay(task_id=sys.argv[1])

    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")

def test():
    """
    Test the crew execution and returns the results.
    """
    inputs = {
        "topic": "AI LLMs",
        "current_year": str(datetime.now().year)
    }

    try:
        Scholarpath().crew().test(n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")

def run_with_trigger():
    """
    Run the crew with trigger payload.
    """
    import json

    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    inputs = {
        "crewai_trigger_payload": trigger_payload,
        "topic": "",
        "current_year": ""
    }

    try:
        result = Scholarpath().crew().kickoff(inputs=inputs)
        return result
    except Exception as e:
        raise Exception(f"An error occurred while running the crew with trigger: {e}")
