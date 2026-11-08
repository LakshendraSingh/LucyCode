"""
Tests for Structural RepoMap and Centrality Scoring.
"""

import os
import tempfile
import unittest
from pathlib import Path

from lucy.core.repomap import RepoMap


class TestRepoMap(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

        # Create sample files
        (self.root / "models.py").write_text(
            "class User:\n    def __init__(self, name: str):\n        self.name = name\n\n"
            "class Product:\n    def get_price(self) -> float:\n        return 9.99\n",
            encoding="utf-8",
        )

        (self.root / "service.py").write_text(
            "from models import User, Product\n\n"
            "class OrderService:\n    def process(self, u: User, p: Product):\n        return p.get_price()\n\n"
            "def helper():\n    pass\n",
            encoding="utf-8",
        )

        (self.root / "app.py").write_text(
            "from service import OrderService\n\n"
            "def main():\n    service = OrderService()\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_repomap_symbol_extraction_and_centrality(self):
        rm = RepoMap(root_dir=self.root, max_tokens=1000)
        file_map = rm.scan_repo()

        self.assertIn("models.py", file_map)
        self.assertIn("service.py", file_map)
        self.assertIn("app.py", file_map)

        models_syms = [s.name for s in file_map["models.py"].symbols]
        self.assertIn("User", models_syms)
        self.assertIn("Product", models_syms)

        # OrderService and User should increase centrality
        rendered = rm.render_map(max_tokens=1000)
        self.assertIn("class User", rendered)
        self.assertIn("class OrderService", rendered)

    def test_repomap_token_budget_respected(self):
        rm = RepoMap(root_dir=self.root, max_tokens=20)
        rendered = rm.render_map(max_tokens=20)
        # Should be truncated to fit budget
        self.assertTrue(len(rendered) < 200)


if __name__ == "__main__":
    unittest.main()

