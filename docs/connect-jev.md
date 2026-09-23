# 接入指南：跑通第一次真实 Jev 判断

> 目标：让 `verify_claim` 真的调用一次 Jev，返回一个**真实**判断和收据。
> 跑通这一次，你就从"只有想法"变成"接过 Jev、能真跑出判断"——才有资格谈发布。

---

## 为什么走 OpenRouter，而不是 TypeSafe 官方

TypeSafe 官方要 waitlist，可能等。**OpenRouter 不用排队**，注册就能拿 key，而且跑的是同一个 `/v1/systemone` 接口、同一套请求/响应格式。先用它跑通，以后想换官方只改一个环境变量。

（其他等价网关：Opper `https://api.opper.ai/v3/compat`、LLMGateway `https://api.llmgateway.io`，都一样。）

---

## 第一步：拿 key（5 分钟）

1. 去 https://openrouter.ai/settings/keys 注册、创建一个 API key
2. 充一点点额度——一次判断约 $0.00003，几美元够你测几万次
3. 复制 key，形如 `sk-or-...`

---

## 第二步：装依赖 + 设环境变量

```bash
cd a2h-onus
pip install -e .

export JUDGMENT_BACKEND=jev
export JEV_BASE_URL=https://openrouter.ai/api      # OpenRouter 网关
export JEV_API_KEY=sk-or-你的key
export JEV_MODEL=jev-1.13.0                           # 钉死版本，别用 latest
```

---

## 第三步：先裸测一次，确认 key 和格式（关键）

**别急着跑 verify_claim。先直接 curl 一次**，亲眼看到真实返回长什么样。这一步能帮你把后面所有问题隔离清楚：

```bash
curl https://openrouter.ai/api/v1/systemone \
  -H "Authorization: Bearer $JEV_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "jev-1.13.0",
    "state": "I was charged twice for my subscription.",
    "questions": {
      "refund": {"type": "noul", "instructions": "Is the customer asking for money back?"}
    }
  }'
```

**你应该看到**（这就是官方文档给的真实格式，本仓库的解析器就是按它写的）：

```json
{
  "model": "typesafe/jev-1.13-20260917",
  "answers": { "refund": { "type": "noul", "noul": 0.98 } },
  "usage": { "input_tokens": 275, "output_tokens": 20 }
}
```

- ✅ 看到 `answers.refund.noul` 是个 0-1 的数 → key 通了，格式对了，往下走
- ❌ 401 → key 不对
- ❌ 402 → 没额度，去充值
- ❌ 429/529 → 过载，稍后重试（本仓库代码会自动处理这个）

---

## 第四步：跑通 verify_claim 的第一次真实判断

把 x_post 例子从 mock 切到真 Jev：

```bash
# 例子里默认 setdefault mock，用环境变量覆盖它
JUDGMENT_BACKEND=jev python examples/verify_x_post.py
```

**成功的样子**：返回里 `model_id` 是 `typesafe/jev-1.13-...`（不是 `mock-heuristic-0`），`confidence` 是 Jev 真算出来的数，收据里 `distribution` 是真实概率。

**这一刻，你有真东西了。** 截图存下来——这是你第一张真收据。

---

## 第五步：确认没被我坑到（诚实检查）

本仓库的响应解析（`a2h_onus/verify/judgment.py` 的 `_parse_answers`）是按官方文档的 **noul** 例子写的。但 **choice 和 score 的确切字段，官方那页只给了 noul 的完整例子**，我是按模式推的：

```python
choice  → {"type":"choice", "choice":"billing", "probabilities":{...}}
score   → {"type":"score",  "score":3,           "probabilities":{...}}
```

**你的验证动作**：真跑一次带 choice 或 score 问题的请求（policy_packs 里 x_post.json 就有一个 `evidence_quality` score 问题），curl 看真实返回，对照 `_parse_answers` 里的字段名。如果对不上（比如 score 的键不叫 `score` 或概率不叫 `probabilities`），改那一处即可——其余逻辑不动。

这是唯一一处可能需要你回头微调的地方。noul 已被官方例子证实无误。

---

## 常见问题

**Q：state 太长报错？**
Jev 1.13 限制：state + 最长 question ≤ 32k token，总 ≤ 64k。证据太大就先截断/摘要（用别的模型摘要，不要用 Jev）。

**Q：想换回本地免费？**
起一个 kev server（Apache-2.0，API 兼容），`export JUDGMENT_BACKEND=kev KEV_URL=http://127.0.0.1:4827`。判断逻辑一行不用改。

**Q：判断结果不准？**
问题措辞（policy_packs 里的 instructions）是判断质量的全部。改措辞、重跑、对比。这是"questions as code"——版本化它，把问题文本连同答案记进收据。

---

## 跑通之后

你现在**真实拥有**：接过 Jev、能真跑出判断、有真实收据。这时候发布叙事才成立——而且是诚实的：

> "我用 Jev 搭了一套验证流水线，开源了。这是我认为 Jev 用在'判断错了要赔钱'的场景时必须有的四个护城河。"

下一步（可选，让数字变真）：跑一批真实证据（哪怕是你自己造的 20 个真假样本），记录自动通过率、拦截数、成本。**那批数字是你自己跑的，就能光明正大写进帖子。**
