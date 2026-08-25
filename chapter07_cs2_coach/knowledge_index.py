"""将版本化 JSON 战术知识同步到 pgvector。"""

from chapter07_cs2_coach.knowledge_base import load_knowledge
from chapter07_cs2_coach.vector_knowledge import pgvector_store_from_environment


def main() -> None:
    entries = load_knowledge()
    pgvector_store_from_environment().sync(entries)
    print(f"已同步 {len(entries)} 条战术知识到 pgvector。")


if __name__ == "__main__":
    main()
