import math
import unittest

from chapter07_cs2_coach.knowledge_base import load_knowledge
from chapter07_cs2_coach.vector_knowledge import (
    EMBEDDING_DIMENSIONS,
    knowledge_document,
    local_text_embedding,
)


def cosine(first, second):
    return sum(a * b for a, b in zip(first, second))


class VectorKnowledgeTests(unittest.TestCase):
    def test_local_embedding_is_normalized_and_deterministic(self):
        first = local_text_embedding("A大 闪光 补枪")
        second = local_text_embedding("A大 闪光 补枪")

        self.assertEqual(len(first), EMBEDDING_DIMENSIONS)
        self.assertEqual(first, second)
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in first)), 1.0)

    def test_related_query_scores_above_unrelated_knowledge(self):
        entries = {item.id: item for item in load_knowledge()}
        query = local_text_embedding("A大突破需要闪光和队友补枪")
        related = local_text_embedding(
            knowledge_document(entries["dust2-long-entry-001"])
        )
        unrelated = local_text_embedding(
            knowledge_document(entries["dust2-clutch-time-001"])
        )

        self.assertGreater(cosine(query, related), cosine(query, unrelated))


if __name__ == "__main__":
    unittest.main()
