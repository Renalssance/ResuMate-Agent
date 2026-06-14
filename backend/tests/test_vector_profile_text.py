import unittest

from backend.vector.milvus_store import build_jd_profile_text


class VectorProfileTextTests(unittest.TestCase):
    def test_build_jd_profile_text_accepts_llm_array_payload(self):
        content = build_jd_profile_text(
            [
                {
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "requirements": ["3+ years Python"],
                    "skills": ["FastAPI", "Milvus"],
                    "responsibilities": ["Build APIs"],
                    "location": "Shanghai",
                }
            ],
            "raw jd text",
        )

        self.assertIn("Backend Engineer", content)
        self.assertIn("Acme", content)
        self.assertIn("FastAPI", content)
        self.assertIn("raw jd text", content)


if __name__ == "__main__":
    unittest.main()
