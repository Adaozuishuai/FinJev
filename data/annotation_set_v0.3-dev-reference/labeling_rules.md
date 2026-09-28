# 金融标注集规则逻辑 v0.1

## 1. 标注目标

目标不是给上市公司贴“好公司/坏公司”标签，也不是直接生成买卖建议，而是把年报中的原始证据变成 FinJev 可以继续判断的结构化对象：

```text
PDF 页
  -> 证据片段（句子、表格行、表格中的关联数字）
  -> 事实/事件主张
  -> 证据等级与数值事实
  -> 方向、重要性、风险标签
  -> ACCEPT / VERIFY / HUMAN_REVIEW 等后续动作
```

最重要的原则是：

> 披露事实、管理层解释、审计结论、外部事实和分析推断必须分开。年报写了某件事，不等于这件事已经被独立证实。

## 2. 标注单位：`metric_event`

一条记录只表达一个可以被复核的核心主张，通常是以下四种之一：

- 一个核心指标及其同比/期末变动，例如营业收入、经营现金流、合同资产、短期借款。
- 一个事件及其状态，例如股权出售、回购、分红预案、融资计划、项目延期。
- 一个风险披露，例如担保、诉讼保全、客户集中度、理财余额。
- 一个审计或合规结论，例如标准无保留意见、收入确认关键审计事项。

不要把一整页作为一条标注，也不要把“收入增长、毛利下降、现金流恶化”强行标成一个单一正负标签。若它们共同形成一个必须综合判断的关系，可以建立一条 `mixed` 记录，同时保留各个指标的原始 `numeric_facts`。

### 2.1 表格规则

1. 一行有明确项目名、期间、单位和数字时，按“表格行”作为最小证据单元。
2. 同一行的本期值、上期值、同比比例必须一起保留，不能只保留同比百分比。
3. 表格跨页时，使用多个 `source_excerpts`，并在 `follow_up_questions` 记录是否需要视觉复核。
4. PDF 抽取把列打乱时，不能凭推测重排数字。要么引用能定位的短片段，要么标记 `label_confidence=low` 并进入人工复核。
5. “-”“不适用”“空白”不是同一个值：分别保留原始文字，不能自动改成 0 或 null。只有明确数值且单位可确定时才填 `normalized_value`。

### 2.2 事件状态规则

`claim_type` 和事件状态要同时看：

- `planned_event`：拟投资、拟分红、拟发行、待股东会/监管审批；不能标成已经发生。
- `completed_event`：报告明确写明已签约、交割、登记、发行或实施完毕。
- `management_explanation`：管理层对变化原因的解释；这是披露，不是独立验证。
- `audit_finding`：审计报告、内控审计或中介鉴证明确写出的结论。
- `absence_statement`：例如“无重大诉讼”。负面披露的证据强度低于具体判决或公告，必须加 `negative_evidence` 或 `disclosure_completeness` 风险。

## 3. 来源权重：`source_authority`

来源权重决定“可以直接接受到什么程度”，不决定主张一定为真。

| 值 | 典型来源 | 标注含义 |
| --- | --- | --- |
| `audited_financial_statement` | 审计报告和经审计资产负债表、利润表、现金流量表 | 对“报表列示了什么”是最高权重；仍不能推导未来表现 |
| `external_audit_quoted` | 年报中引用的审计、保荐、鉴证结论 | 可支持“中介机构发表了什么意见”；最好获取原报告 |
| `issuer_primary_reported` | 年报表格、重大事项、担保、理财、募集资金表 | 是发行人一级披露，适合事实抽取；复杂事实仍应核对附注/公告 |
| `management_discussion` | 管理层对收入、成本、项目延期、战略的解释 | 只能标成“管理层解释”，不能当独立因果证明 |
| `unknown` | 来源或页码无法确认 | 默认 `VERIFY`，不进入已审定训练集 |

本批最容易犯的错误是：把“安永华明出具无保留意见”扩展成“公司没有风险”，或把“管理层称采购支付增加导致现金流为负”扩展成“现金流恶化原因已经查实”。规则禁止这两种扩展。

## 4. 字段规则

### 4.1 `claim` 与 `evidence_relation`

`claim` 是本条真正要判断的目标，不要写成模糊摘要。例如：

- 好：`合同资产同比增长375.94%，期末余额占总资产3.26%。`
- 不好：`公司经营情况复杂。`

`evidence_relation` 是相对于这条 `claim` 的关系，不是对整个公司的评价：

- `supports`：原文直接支持该主张。
- `contradicts`：同一来源或更高权重来源直接否定该主张。
- `neutral`：原文只是列示数字，尚未支持一个带方向性的判断。
- `insufficient`：证据片段不够，缺期间、单位、主体或关键上下文。

例如，“前五名客户占销售46.05%”可以 `supports` “年报披露了该占比”，但对“公司不存在客户集中风险”不能直接 `supports`；后一个主张应是 `VERIFY`。

### 4.2 `event_type`

使用闭集，不要任意创造同义标签：

- `earnings`：收入、利润、现金流、EPS、ROE、季度表现。
- `operations`：产量、销量、库存、成本、毛利、客户/供应商。
- `financing`：借款、债券、中票、再融资、偿债。
- `capital_allocation`：分红、回购、股权激励、员工持股、理财配置。
- `investment`：对外投资、证券投资、重大资本开支。
- `merger_acquisition`：股权收购、出售子公司、资产重组。
- `related_party`：关联交易、关联回购、关联担保。
- `guarantee`：担保、反担保、或有负债。
- `fundraising`：募集资金到账、募投项目进度、变更、现金管理。
- `accounting_policy`：收入确认、研发资本化、减值、预计负债、审计事项。
- `litigation`：诉讼、仲裁、财产保全、执行。
- `regulatory`：监管审批、问询、处罚、上市规则事项。
- `management_change`：审计机构或管理层等关键治理变化。
- `risk_disclosure`：无法归入以上类别的重大风险声明。

如果一条记录有多个维度，选“触发后续判断的主事件”，其余放进 `risk_flags`，不要为了覆盖更多标签而复制同一条证据。

### 4.3 `direction`

方向描述被标注事实的局部方向，不是公司整体评级：

- `positive`：指标改善、合规结论为肯定、风险事项解除。
- `negative`：亏损、现金流为负、毛利率下降、项目延期、担保/诉讼风险增加。
- `mixed`：同一证据中存在相反方向，例如收入和利润增长但经营现金流为负。
- `neutral`：分红、持仓、交易金额等事实本身没有经济好坏结论。
- `unknown`：数字变化的经济含义需要更多上下文，不能安全推断。

不能把“收入同比增长”单独标成公司整体 `positive`；若经营现金流、毛利或应收同时恶化，应使用 `mixed` 或拆成多条记录。

### 4.4 `risk_flags`

风险标签可以多选，但每个标签都必须能在证据或后续问题中找到原因：

`cash_flow_pressure`、`working_capital`、`earnings_quality`、`nonrecurring_items`、`margin_compression`、`cost_inflation`、`inventory`、`contract_asset`、`revenue_recognition`、`accounting_estimate`、`leverage`、`liquidity`、`refinancing`、`guarantee`、`contingent_liability`、`litigation`、`legal`、`regulatory`、`related_party`、`concentration`、`customer`、`supplier`、`execution`、`execution_delay`、`grid_connection`、`capex`、`market`、`valuation`、`dilution`、`share_based_payment`、`internal_control`、`audit_quality`、`negative_evidence`、`disclosure_completeness`。

v0.2 数据已使用的扩展标签也属于受控词表：

`accounting_policy`、`approval_pending`、`asset_disposal`、`auditor_change`、`capital_allocation`、`compliance`、`credit`、`cutoff`、`financing`、`foreign_exchange`、`fraud_risk`、`fundraising`、`going_concern`、`governance`、`international`、`management_assertion`、`pricing`、`provision`、`receivable`、`research_development`、`restricted_assets`、`seasonality`、`supplier_credit`、`warranty`。

风险标签不是“负面新闻分类”。例如标准无保留意见仍可以有 `audit_quality`，因为它表示需要理解审计范围和保证边界，而不是说审计意见为负面。

## 5. 数值事实规则

每个 `numeric_facts` 至少包含：

```json
{
  "metric": "合同资产",
  "raw_value": "3,155,177,189.75",
  "normalized_value": 3155177189.75,
  "unit": "元",
  "currency": "CNY",
  "period": "2025年末",
  "comparison_value": "662,942,444.38",
  "comparison_period": "2024年末",
  "change_pct": 375.94
}
```

具体要求：

1. `raw_value` 必须保留原表中的逗号、负号、百分号语义和原始单位。
2. `normalized_value` 只做机器计算，不覆盖 `raw_value`。万元、亿元不能不经记录就换算成元。
3. 同比/期末变动优先使用报告列出的 `change_pct`。报告写“不适用”就保持空值并在 `note` 说明，不自行计算百分比。
4. 期间必须明确是年度、季度、期末、计划期、协议期还是报告披露日。
5. “拟投资142.10亿元”要标注 `planned_event`；不能把计划额当已投入资产或现金流出。
6. 如果做衍生计算，必须在 `derived_calculations` 记录公式、分子、分母、来源页和舍入方式。没有同报告分母时，不计算比例。

## 6. 重要性 `materiality`

这是 FinJev 的任务级优先级，不是交易所或会计准则中的“重大性”法律认定。先看定性触发器，再看定量阈值；定性触发器可以覆盖金额阈值。

### 6.1 `critical`

满足任一条件：

1. 非标准审计意见、重大错报更正、持续经营重大不确定性。
2. 退市、破产、重大监管处罚、重大违约或可能改变控制权/资本结构的交易。
3. 关键审计事项同时覆盖超过80%的收入/资产，并明确存在收入操纵、重大估计或舞弊风险。本批“主要收入占93.23%且被列为收入确认关键审计事项”按此规则进入 `critical` 和 `HUMAN_REVIEW`。

### 6.2 `high`

满足任一条件：

1. 在同一报告、同一期间、分母明确时，金额达到收入、总资产或归母净资产的10%以上。
2. 担保、或有负债或集中风险达到净资产的5%以上，或覆盖高负债率对象。
3. 现金流、利润、毛利、短期借款等核心指标出现明显冲突，或年度/季度出现亏损。
4. 金额虽低于阈值，但涉及收入确认、减值、预计负债、重大诉讼、监管批准或项目延期等高风险主题。

### 6.3 `medium`

金额约占相关分母1%–10%，或虽无可靠分母但具有明确经营意义，例如理财、客户/供应商集中度、股权激励、分红预案、审计机构变更。

### 6.4 `low`

纯背景信息、金额很小、没有可识别的财务/治理后果，也没有触发风险标签。当前核心种子集没有为了凑齐 `low` 而添加无效样本。

如果分母缺失、单位混乱或表格列无法可靠对应，不要为了提高重要性而猜测；使用 `label_confidence=low/medium`、`gold_action=VERIFY`，并在 `materiality_basis` 写出缺口。

## 7. 证据置信度与后续动作

`label_confidence` 只表示“这条标签从文本上是否清楚”，不表示 Jev 对公司未来的置信度：

- `high`：页码、主体、期间、单位和数值关系清楚，摘录经匹配。
- `medium`：内容可读，但属于管理层判断、负面声明、跨页表格或需要附注才能解释。
- `low`：抽取顺序、主体、期间或单位不确定，不能进入正式 gold set。

`gold_action` 的逻辑：

| 动作 | 触发条件 | 后续含义 |
| --- | --- | --- |
| `ACCEPT` | 来源清楚，主张与摘录直接一致，内部没有冲突 | 接受“该披露被来源支持”，不是接受投资结论 |
| `VERIFY` | 管理层解释、大额交易、计划事项、负面声明、金额/因果需要外部材料 | 继续找附注、临时公告、合同、期后数据或独立来源 |
| `HUMAN_REVIEW` | 收入确认、估计/减值、关键审计事项、重大诉讼、潜在控制/重大交易 | 必须由金融标注员或分析师审阅，不自动入 gold |
| `REJECT` | 摘录与主张直接矛盾，或页码/主体错误 | 记录错误，不把它作为正例使用 |
| `CONTINUE` | 证据足够但问题链尚未结束 | 进入下一个相关证据单元 |
| `STOP` | 证据达到任务停止条件，或有明确禁止继续的原因 | 结束该条研究链 |

本批用了 `ACCEPT`、`VERIFY` 和 `HUMAN_REVIEW`，没有把任何记录预先标成 `REJECT`、`STOP`。这是因为当前任务是建证据集，不是在做最终投资判断。

## 8. 冲突与交叉核验

同一事实同时出现在第 8 页摘要表和第 101/105 页审计财务报表时，不要删除一份；用 `linked_record_ids` 关联来源：

- 第 8 页：适合识别“摘要披露了什么”和利润/现金流冲突。
- 第 101 页：合并利润表的审计报表来源。
- 第 105 页：合并现金流量表的审计报表来源。

如果数值不同：

1. 先检查合并口径/母公司口径、年度/期末口径、调整前/调整后和单位。
2. 再检查 PDF 表格视觉版面和抽取列顺序。
3. 仍无法解释时标 `contradicts` 或 `insufficient`，不要用平均数或最新数字掩盖冲突。

## 9. 人工复核和数据集拆分

正式 gold set 的最低流程：

1. 标注员 A、B 独立对同一批记录标注，不能先看对方结果。
2. 对 `event_type`、`direction`、`materiality`、`gold_action` 分别计算一致率；冲突记录进入仲裁。
3. 对所有 `critical` 和 `HUMAN_REVIEW` 记录逐条查附注/临时公告/原始中介报告。
4. 记录修改前后版本和理由，不能直接覆盖原始 seed。
5. 至少抽取5%已标注记录回查页码、单位、负号和数值，发现一个系统性抽取错误时扩大回查范围。
6. 训练/验证/测试按发行人、报告期或公告事件分组切分。同一年度报告的第8页不能进训练集、第101页进测试集，否则会产生严重数据泄漏。

最终 gold 记录应满足：`annotation_status=adjudicated`、有复核人、有复核时间、有冲突处理说明，并且所有 `source_excerpts` 都能回到原 PDF 页。

## 10. 本批种子中最重要的校验逻辑

以下组合不是投资结论，而是给后续 FinJev 研究链的优先级：

1. 收入/归母净利润增长 + 经营现金流为负：`direction=mixed`、`risk_flags` 含现金流和利润质量、`gold_action=VERIFY`。
2. 电站产品收入增长但成本增幅更高、毛利率下降：`direction=negative`、`materiality=high`。
3. 合同资产、库存、短期借款和应付账款上升：分别标注，不将“规模增长”自动解释为健康增长。
4. 担保余额和高负债率被担保对象：金额阈值与定性风险同时触发 `high`。
5. 计划投资/计划分红/拟发行中票：保留 `planned_event` 和审批状态，不能标为已完成。
6. 无重大诉讼：标为 `absence_statement`，加负面证据风险，默认 `VERIFY`。
7. 收入确认和质量保证金：来源权重高，但估计/操纵风险仍然存在，进入 `HUMAN_REVIEW`。
