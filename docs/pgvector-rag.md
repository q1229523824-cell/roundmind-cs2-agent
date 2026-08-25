# pgvector 混合 RAG

## 默认为什么仍是 local

RoundMind 现有 10 条 Dust2 知识用元数据过滤和关键词计分已经足够稳定。数据量很小时，加入向量数据库不会
自动让建议更准确。默认 `ROUNDMIND_KNOWLEDGE_BACKEND=local`，便于离线运行和回归测试。

设置为 `pgvector` 后，系统会将版本化 JSON 知识同步到 PostgreSQL `knowledge_vectors`，先按地图过滤，
再用余弦距离召回候选，最后叠加阵营、点位和主题分数。这是“向量召回 + 结构化重排”的混合检索，输出仍
只能引用白名单知识 ID。

## 零费用向量基线

当前 384 维向量由中文字符 bigram 和英文词做稳定哈希后归一化生成。优点是完全离线、无 API Key、可复现；
缺点是只能捕捉词面相似，不能真正理解同义表达。因此它用于学习 pgvector 管线和建立评测基线，不应在简历中
写成“训练了语义 Embedding 模型”。以后可以保持表和检索接口不变，将生成函数替换为已评测的中文
Embedding 模型，并重新同步索引。

## 启用

PostgreSQL 服务需要允许 `CREATE EXTENSION vector`：

```powershell
$env:DATABASE_URL="postgresql://..."
python -m alembic -c chapter07_cs2_coach/alembic.ini upgrade head
python -m chapter07_cs2_coach.knowledge_index
$env:ROUNDMIND_KNOWLEDGE_BACKEND="pgvector"
```

不要在代码里硬编码数据库密码。是否提升效果应通过固定问题集对比 Recall@K、知识 ID 命中率和最终动作推荐
一致率，而不是只看几个回答是否“像人话”。
