# 卖家精灵 MCP 接口速查（本 skill 用到的部分）

端点：`https://mcp.sellersprite.com/mcp`
鉴权：HTTP header `secret-key: <KEY>`
协议：JSON-RPC 2.0，`method=tools/call`

## 1. product_node —— 类目节点

```json
{"request": {"marketplace": "DE", "keyword": "Insektenschutz"}}
{"request": {"marketplace": "DE", "nodeIdPath": "64187031:2860338031:2860457031"}}
```

返回节点列表，字段含 `nodeIdPath`（冒号分隔层级）、`nodeLabelPath`、`goodsCount`。
**子节点判定**：`nodeIdPath` 的层级数 = 父节点层级数 + 1。

## 2. product_research —— 商品池

```json
{"request": {"marketplace": "DE", "nodeIdPath": "<节点>", "size": 100, "page": 1,
             "order": {"field": "total_units", "desc": true}}}
```

返回 `data.items[]`，常用字段：

| 字段 | 含义 |
|---|---|
| asin / title / brand / imageUrl | 基础信息 |
| price / units / revenue | 售价、月销、月销额 |
| ratings / rating | 评论数、星级 |
| bsr / bsrId | 大类排名、类目 |
| fba | FBA 配送费（部分商品为空） |
| pkgDimensions / pkgWeight | 包装尺寸/重量 |
| createdTime / availableDate | 上架时间 |

也支持 `keyword` + `matchType`（1=词组，2=模糊，3=精准）替代 nodeIdPath。

## 3. keyword_miner —— 关键词

```json
{"request": {"marketplace": "DE", "keyword": "<种子词>", "size": 100, "page": 1}}
```

`data.items[]`：`keyword / searches / products / purchaseRate / bid / relevancy`。

## 4. review —— 评论

```json
{"marketplace": "DE", "asin": "B0XXXXXXXX", "starList": [1,2,3], "size": 30, "page": 1}
```

注意参数是**扁平**的（没有 `request` 包一层），`starList` 传 1–3 取差评。

## 错误码

| code | 含义 | 处理 |
|---|---|---|
| `ERROR_VISIT_MAX` | 接口访问次数已达上限（总量配额） | 停止调用，用缓存或等重置 |
| `secret_unauthorized` | key 未授权该服务 | 检查 key |
| `secret_expired` / `secret_no_remaining` | 过期 / 无剩余次数 | 续费 |

## 参数嵌套规则（易错）

- `product_node` / `product_research` / `keyword_miner` / `market_research`：**`{"request": {...}}`**
- `review` / `asin_detail`：**扁平参数**（`{marketplace, asin}`）
- 传错会得到空结果而不是报错，很难排查——先传一个已知 ASIN 验证。
