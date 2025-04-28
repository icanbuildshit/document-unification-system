import unittest
import asyncio
from src.agents.validator_agent import ValidatorAgent

class TestValidatorAgent(unittest.TestCase):
    def setUp(self):
        self.agent = ValidatorAgent()

    def test_initialization(self):
        self.assertEqual(self.agent.name, "validator")

    def test_process_minimal(self):
        # Minimal parser output with no documents
        parser_output = {"documents": []}
        result = asyncio.run(self.agent.process(parser_output))
        self.assertIn("documents", result)
        self.assertIn("validation_results", result)
        self.assertEqual(result["validation_results"]["stats"]["total_facts"], 0)
        self.assertEqual(result["validation_results"]["stats"]["total_contradictions"], 0)

if __name__ == "__main__":
    unittest.main() 