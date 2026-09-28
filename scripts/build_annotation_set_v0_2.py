"""Extend the v0.1 seed set with key pages from two additional annual reports."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pdfplumber
from jsonschema import Draft202012Validator

BASE_DATASET = Path("data/annotation_set_v0.1")
OUTPUT = Path("data/annotation_set_v0.2")
LABEL_VERSION = "0.2"

SOURCES = {
    "futong": {
        "path": Path("/Users/Admin/Desktop/上市公司二.pdf"),
        "document": "上市公司二.pdf",
        "issuer": "天津富通信息科技股份有限公司",
        "stock_code": "000836",
        "report_period": "2023",
        "pages": [7, 8, 15, 39, 61, 62],
    },
    "langfang": {
        "path": Path("/Users/Admin/Desktop/上市公司报告3.pdf"),
        "document": "上市公司报告3.pdf",
        "issuer": "廊坊发展股份有限公司",
        "stock_code": "600149",
        "report_period": "2024",
        "pages": [5, 6, 17, 19, 44, 52, 53],
    },
}


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fact(
    metric: str,
    raw_value: str,
    *,
    normalized_value: int | float | None = None,
    unit: str | None = None,
    currency: str | None = None,
    period: str | None = None,
    comparison_value: str | None = None,
    comparison_period: str | None = None,
    change_pct: float | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    result = {
        "metric": metric,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "unit": unit,
        "currency": currency,
        "period": period,
        "comparison_value": comparison_value,
        "comparison_period": comparison_period,
        "change_pct": change_pct,
    }
    if note:
        result["note"] = note
    return result


def spec(
    record_id: str,
    source: str,
    page: int,
    section: str,
    claim: str,
    excerpts: list[str],
    *,
    source_authority: str,
    claim_type: str,
    event_type: str,
    direction: str,
    materiality: str,
    materiality_basis: str,
    risk_flags: list[str],
    evidence_relation: str,
    label_confidence: str,
    gold_action: str,
    numeric_facts: list[dict[str, Any]] | None = None,
    derived_calculations: list[dict[str, Any]] | None = None,
    follow_up_questions: list[str] | None = None,
    linked_record_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "source": source,
        "pdf_page": page,
        "section": section,
        "claim": claim,
        "source_excerpts": excerpts,
        "source_authority": source_authority,
        "claim_type": claim_type,
        "event_type": event_type,
        "direction": direction,
        "materiality": materiality,
        "materiality_basis": materiality_basis,
        "risk_flags": risk_flags,
        "evidence_relation": evidence_relation,
        "label_confidence": label_confidence,
        "gold_action": gold_action,
        "numeric_facts": numeric_facts or [],
        "derived_calculations": derived_calculations or [],
        "follow_up_questions": follow_up_questions or [],
        "linked_record_ids": linked_record_ids or [],
    }


SPECS = [
    spec(
        "futong-annual-2023-p007-001",
        "futong",
        7,
        "主要会计数据和财务指标",
        "2023年营业收入同比下降77.61%，归母净利润由盈利转为亏损2.275亿元，净资产同比下降19.00%。",
        [
            "营业收入 297,904,737.1 1,330,580,721 1,330,580,721 1,429,520,94 1,429,520,94 -77.61% （元） 4 .10 .10 3.53 3.53",
            "归属于上市公 - 司股东的净利 227,517,734.2 12,648,224.82 12,674,153.05 -1,895.13%",
            "归属于上市公 1,039,678,437 1,283,657,560 1,283,621,171 1,320,284,33 1,320,284,33 -19.00% 司股东的净资 .04 .58 .33 5.76 5.76",
        ],
        source_authority="issuer_primary_reported",
        claim_type="reported_metric",
        event_type="earnings",
        direction="negative",
        materiality="critical",
        materiality_basis="收入下降超过四分之三、归母净利润由正转负且净资产下降，构成核心经营和资本状况恶化。",
        risk_flags=["earnings_quality", "market", "liquidity"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="HUMAN_REVIEW",
        numeric_facts=[
            fact("营业收入", "297,904,737.14", normalized_value=297904737.14, unit="元", currency="CNY", period="2023年度", comparison_value="1,330,580,721.10", comparison_period="2022年度", change_pct=-77.61),
            fact("归属于上市公司股东的净利润", "-227,517,734.29", normalized_value=-227517734.29, unit="元", currency="CNY", period="2023年度", comparison_value="12,674,153.05", comparison_period="2022年度", change_pct=-1895.13),
            fact("归属于上市公司股东的净资产", "1,039,678,437.04", normalized_value=1039678437.04, unit="元", currency="CNY", period="2023年末", comparison_value="1,283,621,171.33", comparison_period="2022年末", change_pct=-19.0),
        ],
        linked_record_ids=["futong-annual-2023-p062-001"],
    ),
    spec(
        "futong-annual-2023-p008-001",
        "futong",
        8,
        "营业收入扣除",
        "2023年营业收入2.979亿元中有8,505.01万元被扣除，扣除后营业收入为2.1285亿元。",
        [
            "营业收入（元） 297,904,737.14 1,330,580,721.10",
            "营业收入扣除金额（元） 85,050,121.41 6,854,550.68",
            "营业收入扣除后金额（元） 212,854,615.73 1,323,726,170.42",
        ],
        source_authority="issuer_primary_reported",
        claim_type="reported_metric",
        event_type="earnings",
        direction="negative",
        materiality="high",
        materiality_basis="扣除项目约占报告营业收入28.55%，且扣除后收入较上年显著下降。",
        risk_flags=["earnings_quality", "nonrecurring_items"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="VERIFY",
        numeric_facts=[
            fact("营业收入", "297,904,737.14", normalized_value=297904737.14, unit="元", currency="CNY", period="2023年度"),
            fact("营业收入扣除金额", "85,050,121.41", normalized_value=85050121.41, unit="元", currency="CNY", period="2023年度"),
            fact("营业收入扣除后金额", "212,854,615.73", normalized_value=212854615.73, unit="元", currency="CNY", period="2023年度"),
        ],
        derived_calculations=[{"metric": "营业收入扣除比例", "formula": "85,050,121.41 / 297,904,737.14", "result_pct": 28.55}],
    ),
    spec(
        "futong-annual-2023-p015-001",
        "futong",
        15,
        "收入与成本",
        "光通信网络产品收入同比下降86.38%，成本同比下降75.73%，毛利率为-48.14%。",
        ["光通信网络产 174,579,027. 258,628,644. -48.14% -86.38% -75.73% -64.97% 品 18 93"],
        source_authority="management_discussion",
        claim_type="reported_metric",
        event_type="operations",
        direction="negative",
        materiality="critical",
        materiality_basis="核心产品收入断崖式下降且呈大幅负毛利，直接影响主营业务持续性。",
        risk_flags=["margin_compression", "cost_inflation", "market", "execution"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="HUMAN_REVIEW",
        numeric_facts=[
            fact("光通信网络产品营业收入", "174,579,027.18", normalized_value=174579027.18, unit="元", currency="CNY", period="2023年度", change_pct=-86.38),
            fact("光通信网络产品营业成本", "258,628,644.93", normalized_value=258628644.93, unit="元", currency="CNY", period="2023年度", change_pct=-75.73),
            fact("光通信网络产品毛利率", "-48.14%", normalized_value=-48.14, unit="%", period="2023年度"),
        ],
    ),
    spec(
        "futong-annual-2023-p039-001",
        "futong",
        39,
        "内部控制审计报告",
        "审计师认定协议签订和款项支付控制存在重大缺陷，相关及其他供应商预付账款合计约5.959亿元，期末尚未整改。",
        [
            "富通信息公司在协议签订以及款项支付管理上未能实施有效的控制。",
            "形成的预付账款期末余额为13,439.91万元",
            "形成的预付账款期末余额为46,146.43万元",
            "截至2023年12月31日，富通信息公司未完成对上述重大缺陷的整改",
        ],
        source_authority="external_audit_quoted",
        claim_type="audit_finding",
        event_type="accounting_policy",
        direction="negative",
        materiality="critical",
        materiality_basis="审计师明确认定财务报告内控重大缺陷且期末未整改，涉及大额资金支付和关联方完整性。",
        risk_flags=["internal_control", "related_party", "audit_quality", "liquidity"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="HUMAN_REVIEW",
        numeric_facts=[
            fact("关联方预付账款期末余额", "13,439.91万元", normalized_value=134399100, unit="元", currency="CNY", period="2023年末"),
            fact("其他大额预付账款期末余额", "46,146.43万元", normalized_value=461464300, unit="元", currency="CNY", period="2023年末"),
        ],
        linked_record_ids=["futong-annual-2023-p061-001"],
    ),
    spec(
        "futong-annual-2023-p061-001",
        "futong",
        61,
        "保留意见审计报告",
        "审计师因无法获取充分适当证据确认6.267亿元预付账款实际用途及关联方交易完整性，对财务报表发表保留意见。",
        [
            "审计意见类型 保留意见",
            "预付账款余额62,672.23万元",
            "但无法获取充分、适当的审计证据，以确定这些预付账款的实际用途以及财务报表附注中披露的关联方及其交易是否完整",
        ],
        source_authority="external_audit_quoted",
        claim_type="audit_finding",
        event_type="accounting_policy",
        direction="negative",
        materiality="critical",
        materiality_basis="非标准审计意见直接限制财务报表可信边界，且无法验证金额约占年末总资产四分之一。",
        risk_flags=["audit_quality", "internal_control", "related_party", "disclosure_completeness"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="HUMAN_REVIEW",
        numeric_facts=[fact("预付账款余额", "62,672.23万元", normalized_value=626722300, unit="元", currency="CNY", period="2023年末")],
        linked_record_ids=["futong-annual-2023-p039-001"],
    ),
    spec(
        "futong-annual-2023-p062-001",
        "futong",
        62,
        "持续经营重大不确定性",
        "审计报告披露公司净亏损2.2509亿元、逾期银行借款1.83亿元、部分账户被冻结，并存在停产和拖欠薪资，持续经营存在重大不确定性。",
        [
            "富通信息公司2023年发生净亏损22,509.29万元；截至2023年12月31日，已逾期银行借款1.83亿元。",
            "导致公司部分银行账户被冻结",
            "富通信息公司及大部分子公司已经停产、拖欠薪资",
            "存在可能导致对富通信息公司持续经营能力产生重大疑虑的重大不确定性",
        ],
        source_authority="external_audit_quoted",
        claim_type="audit_finding",
        event_type="risk_disclosure",
        direction="negative",
        materiality="critical",
        materiality_basis="逾期债务、冻结账户、停产和欠薪同时出现，是持续经营的直接定性触发器。",
        risk_flags=["liquidity", "refinancing", "cash_flow_pressure", "execution", "litigation"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="HUMAN_REVIEW",
        numeric_facts=[
            fact("净亏损", "22,509.29万元", normalized_value=-225092900, unit="元", currency="CNY", period="2023年度"),
            fact("逾期银行借款", "1.83亿元", normalized_value=183000000, unit="元", currency="CNY", period="2023年末"),
        ],
        linked_record_ids=["futong-annual-2023-p007-001"],
    ),
    spec(
        "futong-annual-2023-p062-002",
        "futong",
        62,
        "关键审计事项",
        "审计师将2023年2.979亿元营业收入列为关键审计事项，原因是管理层可能存在不恰当确认收入的固有风险。",
        [
            "富通信息公司2023年度营业收入29,790.47万元。",
            "管理层可能存在不恰当确认收入的固有风险，因此我们将其列为关键审计事项。",
        ],
        source_authority="external_audit_quoted",
        claim_type="audit_finding",
        event_type="accounting_policy",
        direction="negative",
        materiality="high",
        materiality_basis="收入是关键业绩指标且审计师明确识别不恰当确认收入的固有风险。",
        risk_flags=["revenue_recognition", "audit_quality", "earnings_quality"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="HUMAN_REVIEW",
        numeric_facts=[fact("营业收入", "29,790.47万元", normalized_value=297904700, unit="元", currency="CNY", period="2023年度")],
    ),
    spec(
        "langfang-annual-2024-p005-001",
        "langfang",
        5,
        "主要会计数据",
        "2024年归母净利润为8,492.61万元，但扣非归母净利润仅987.59万元，利润增长主要不是来自经常性损益。",
        [
            "归属于上市公司股 84,926,060.80 -14,908,569.40 不适用 -8,381,974.33 东的净利润",
            "归属于上市公司股 东的扣除非经常性 9,875,908.96 -15,905,004.33 不适用 -9,846,360.19 损益的净利润",
        ],
        source_authority="issuer_primary_reported",
        claim_type="reported_metric",
        event_type="earnings",
        direction="mixed",
        materiality="high",
        materiality_basis="归母净利润扭亏，但扣非净利润只占归母净利润约11.63%，需区分持续经营收益和一次性收益。",
        risk_flags=["earnings_quality", "nonrecurring_items"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="VERIFY",
        numeric_facts=[
            fact("归属于上市公司股东的净利润", "84,926,060.80", normalized_value=84926060.8, unit="元", currency="CNY", period="2024年度", comparison_value="-14,908,569.40", comparison_period="2023年度"),
            fact("扣非归母净利润", "9,875,908.96", normalized_value=9875908.96, unit="元", currency="CNY", period="2024年度", comparison_value="-15,905,004.33", comparison_period="2023年度"),
        ],
        derived_calculations=[{"metric": "扣非净利润占归母净利润比例", "formula": "9,875,908.96 / 84,926,060.80", "result_pct": 11.63}],
        linked_record_ids=["langfang-annual-2024-p006-001"],
    ),
    spec(
        "langfang-annual-2024-p006-001",
        "langfang",
        6,
        "资产处置与利润来源",
        "资产处置增加其他业务收入1.86亿元，并贡献归母净利润7,347万元，约占全年归母净利润86.51%。",
        ["本报告期内，公司资产处置增加其他业务收入1.86亿元（扣除此事项影响后，营业收入2.10亿元），增加归属于母公司所有者的净利润7,347万元。"],
        source_authority="issuer_primary_reported",
        claim_type="reported_metric",
        event_type="capital_allocation",
        direction="mixed",
        materiality="high",
        materiality_basis="一次性资产处置贡献全年归母净利润的大部分，表面盈利增长不能直接外推为主营改善。",
        risk_flags=["nonrecurring_items", "earnings_quality", "valuation"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="VERIFY",
        numeric_facts=[
            fact("资产处置增加其他业务收入", "1.86亿元", normalized_value=186000000, unit="元", currency="CNY", period="2024年度"),
            fact("资产处置增加归母净利润", "7,347万元", normalized_value=73470000, unit="元", currency="CNY", period="2024年度"),
        ],
        derived_calculations=[{"metric": "资产处置利润贡献比例", "formula": "73,470,000 / 84,926,060.80", "result_pct": 86.51}],
        linked_record_ids=["langfang-annual-2024-p005-001"],
    ),
    spec(
        "langfang-annual-2024-p017-001",
        "langfang",
        17,
        "资产负债状况",
        "2024年末存货为3,074.10万元，同比增长104.84%，公司解释为煤炭储存量增加。",
        ["主要是煤炭储存 存货 30,740,977.86 4.88 15,007,320.14 2.51 104.84 量增加所致"],
        source_authority="management_discussion",
        claim_type="management_explanation",
        event_type="operations",
        direction="negative",
        materiality="medium",
        materiality_basis="存货翻倍并达到总资产4.88%，原因来自管理层解释，需结合供暖周期和煤价核验。",
        risk_flags=["inventory", "working_capital", "cost_inflation"],
        evidence_relation="supports",
        label_confidence="medium",
        gold_action="VERIFY",
        numeric_facts=[fact("存货", "30,740,977.86", normalized_value=30740977.86, unit="元", currency="CNY", period="2024年末", comparison_value="15,007,320.14", comparison_period="2023年末", change_pct=104.84)],
    ),
    spec(
        "langfang-annual-2024-p019-001",
        "langfang",
        19,
        "重大资产和股权出售",
        "公司以140.20万元向控股股东转让全资子公司至尚无忧100%股权，款项已收且工商变更完成。",
        [
            "公司向控股股东廊坊控股转让全资子公司至尚无忧100%股权，转让价款为140.20万元。",
            "公司已收到廊坊控股支付的全部转让款，至尚无忧已完成工商变更登记手续",
        ],
        source_authority="issuer_primary_reported",
        claim_type="completed_event",
        event_type="related_party",
        direction="neutral",
        materiality="medium",
        materiality_basis="交易金额不大但交易对手为控股股东，需要核验定价依据和独立程序。",
        risk_flags=["related_party", "valuation"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="VERIFY",
        numeric_facts=[fact("股权转让价款", "140.20万元", normalized_value=1402000, unit="元", currency="CNY", period="2024年度")],
    ),
    spec(
        "langfang-annual-2024-p044-001",
        "langfang",
        44,
        "担保情况",
        "公司对子公司担保余额2,000万元，占净资产8.62%，且全部对应资产负债率超过70%的被担保对象。",
        [
            "报告期末对子公司担保余额合计（B） 2,000",
            "担保总额占公司净资产的比例(%) 8.62",
            "直接或间接为资产负债率超过70%的被担保 2,000 对象提供的债务担保金额（D）",
        ],
        source_authority="issuer_primary_reported",
        claim_type="risk_disclosure",
        event_type="guarantee",
        direction="negative",
        materiality="high",
        materiality_basis="担保占净资产比例超过5%，且被担保对象资产负债率超过70%。",
        risk_flags=["guarantee", "contingent_liability", "leverage"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="VERIFY",
        numeric_facts=[
            fact("对子公司担保余额", "2,000万元", normalized_value=20000000, unit="元", currency="CNY", period="2024年末"),
            fact("担保总额占净资产比例", "8.62%", normalized_value=8.62, unit="%", period="2024年末"),
        ],
    ),
    spec(
        "langfang-annual-2024-p052-001",
        "langfang",
        52,
        "审计意见",
        "众华会计师事务所对廊坊发展2024年度财务报表发表标准无保留意见。",
        ["我们认为，后附的财务报表在所有重大方面按照企业会计准则的规定编制，公允反映了廊坊发展公司2024年12月31日合并及母公司的财务状况以及2024年度合并及母公司的经营成果和现金流量。"],
        source_authority="external_audit_quoted",
        claim_type="audit_finding",
        event_type="accounting_policy",
        direction="positive",
        materiality="medium",
        materiality_basis="标准无保留意见提高对报表列示的来源权重，但不消除收入确认和商誉估计风险。",
        risk_flags=["audit_quality"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="ACCEPT",
        linked_record_ids=["langfang-annual-2024-p052-002", "langfang-annual-2024-p053-001"],
    ),
    spec(
        "langfang-annual-2024-p052-002",
        "langfang",
        52,
        "关键审计事项",
        "审计师将3.9615亿元营业收入确认列为关键审计事项，收入包括处置投资性房地产收入。",
        [
            "我们确定下列事项是需要在审计报告中沟通的关键审计事项。",
            "（一）营业收入的确认",
            "廊坊发展公司2024年度合并口径营业收入为396,149,803.66元。",
            "主要包括热力产品销售、工程及设计收入、房屋租赁收入、咨询服务收入、处置投资性房地产收入。",
        ],
        source_authority="external_audit_quoted",
        claim_type="audit_finding",
        event_type="accounting_policy",
        direction="negative",
        materiality="high",
        materiality_basis="收入翻倍且含重大资产处置，审计师明确识别收入确认重大错报风险。",
        risk_flags=["revenue_recognition", "nonrecurring_items", "audit_quality"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="HUMAN_REVIEW",
        numeric_facts=[fact("营业收入", "396,149,803.66元", normalized_value=396149803.66, unit="元", currency="CNY", period="2024年度")],
    ),
    spec(
        "langfang-annual-2024-p053-001",
        "langfang",
        53,
        "关键审计事项",
        "2024年末商誉账面净值为4,035.93万元，减值测试依赖未来现金流增长率和折现等管理层估计。",
        [
            "截止2024年12月31日，合并报表商誉账面净值人民币40,359,271.98元。",
            "管理层至少于每年年度终了进行减值测试",
        ],
        source_authority="external_audit_quoted",
        claim_type="audit_finding",
        event_type="accounting_policy",
        direction="unknown",
        materiality="high",
        materiality_basis="商誉约占年末净资产17.39%，减值结论依赖关键估计，需核验预测和折现假设。",
        risk_flags=["accounting_estimate", "valuation", "audit_quality"],
        evidence_relation="supports",
        label_confidence="high",
        gold_action="HUMAN_REVIEW",
        numeric_facts=[fact("商誉账面净值", "40,359,271.98元", normalized_value=40359271.98, unit="元", currency="CNY", period="2024年末")],
        derived_calculations=[{"metric": "商誉占归母净资产比例", "formula": "40,359,271.98 / 232,148,560.06", "result_pct": 17.39}],
    ),
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values), encoding="utf-8")


def build_new_pages() -> tuple[list[dict[str, Any]], dict[tuple[str, int], str]]:
    page_records: list[dict[str, Any]] = []
    page_texts: dict[tuple[str, int], str] = {}
    for source_key, source in SOURCES.items():
        with pdfplumber.open(source["path"]) as pdf:
            for page_number in source["pages"]:
                text = pdf.pages[page_number - 1].extract_text() or ""
                page_texts[(source_key, page_number)] = text
                page_records.append(
                    {
                        "page_id": f"{source_key}-annual-{source['report_period']}-p{page_number:03d}",
                        "source_document": source["document"],
                        "source_path": str(source["path"]),
                        "pdf_page": page_number,
                        "section": "关键财务与审计证据",
                        "selection_reason": "高重要性财务指标、重大事项、审计意见或关键审计事项",
                        "text": text,
                        "normalized_text": normalize(text),
                        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        "visual_review_status": "sampled",
                        "extraction_status": "text_extracted",
                    }
                )
    return page_records, page_texts


def build_new_annotations(page_texts: dict[tuple[str, int], str]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in SPECS:
        source = SOURCES[item["source"]]
        page_text = page_texts[(item["source"], item["pdf_page"])]
        missing = [excerpt for excerpt in item["source_excerpts"] if compact(excerpt) not in compact(page_text)]
        if missing:
            errors.append(f"{item['record_id']} missing excerpt(s): {missing}")
        records.append(
            {
                "record_id": item["record_id"],
                "source_document": source["document"],
                "source_path": str(source["path"]),
                "issuer": source["issuer"],
                "stock_code": source["stock_code"],
                "report_type": "annual_report",
                "report_period": source["report_period"],
                "unit_type": "metric_event",
                "pdf_page": item["pdf_page"],
                "section": item["section"],
                "claim": item["claim"],
                "source_excerpts": item["source_excerpts"],
                "evidence_text": " ".join(item["source_excerpts"]),
                "source_authority": item["source_authority"],
                "claim_type": item["claim_type"],
                "event_type": item["event_type"],
                "direction": item["direction"],
                "materiality": item["materiality"],
                "materiality_basis": item["materiality_basis"],
                "risk_flags": item["risk_flags"],
                "evidence_relation": item["evidence_relation"],
                "label_confidence": item["label_confidence"],
                "gold_action": item["gold_action"],
                "numeric_facts": item["numeric_facts"],
                "derived_calculations": item["derived_calculations"],
                "follow_up_questions": item["follow_up_questions"],
                "linked_record_ids": item["linked_record_ids"],
                "page_visual_review_status": "sampled",
                "annotation_status": "seed_pending_human_review",
                "review_status": "pending_human_review",
                "annotator": "codex_seed",
                "label_version": LABEL_VERSION,
            }
        )
    return records, errors


def main() -> int:
    for source in SOURCES.values():
        if not source["path"].is_file():
            raise SystemExit(f"Missing source PDF: {source['path']}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in ("label_schema.json", "labeling_rules.md"):
        shutil.copy2(BASE_DATASET / name, OUTPUT / name)

    base_pages = load_jsonl(BASE_DATASET / "pages.jsonl")
    base_annotations = load_jsonl(BASE_DATASET / "annotations.jsonl")
    new_pages, page_texts = build_new_pages()
    new_annotations, excerpt_errors = build_new_annotations(page_texts)
    pages = base_pages + new_pages
    annotations = base_annotations + new_annotations

    schema = json.loads((OUTPUT / "label_schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    schema_errors = [
        f"{record['record_id']}: {error.message}"
        for record in annotations
        for error in validator.iter_errors(record)
    ]
    ids = {record["record_id"] for record in annotations}
    broken_links = [
        f"{record['record_id']} -> {linked}"
        for record in annotations
        for linked in record.get("linked_record_ids", [])
        if linked not in ids
    ]
    errors = excerpt_errors + schema_errors + broken_links
    if errors:
        raise SystemExit("\n".join(errors))

    write_jsonl(OUTPUT / "pages.jsonl", pages)
    write_jsonl(OUTPUT / "annotations.jsonl", annotations)

    previous_manifest = json.loads((BASE_DATASET / "manifest.json").read_text(encoding="utf-8"))
    source_entries = [
        {
            "source_document": previous_manifest["source_document"],
            "source_path": previous_manifest["source_path"],
            "source_sha256": previous_manifest["source_sha256"],
            "issuer": previous_manifest["issuer"],
            "stock_code": previous_manifest["stock_code"],
            "report_period": previous_manifest["report_period"],
            "selected_pages": previous_manifest["selected_pages"],
            "visually_reviewed_pages": previous_manifest["visually_reviewed_pages"],
        }
    ]
    source_entries.extend(
        {
            "source_document": source["document"],
            "source_path": str(source["path"]),
            "source_sha256": sha256_file(source["path"]),
            "issuer": source["issuer"],
            "stock_code": source["stock_code"],
            "report_period": source["report_period"],
            "selected_pages": source["pages"],
            "visually_reviewed_pages": source["pages"],
        }
        for source in SOURCES.values()
    )
    manifest = {
        "dataset_name": "finjev-core-financial-annotation-set",
        "dataset_version": LABEL_VERSION,
        "status": "seed_pending_human_review",
        "parent_dataset": str(BASE_DATASET),
        "sources": source_entries,
        "selected_page_count": len(pages),
        "annotation_count": len(annotations),
        "extractor": "pdfplumber",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "label_policy_note": "Thresholds and actions are FinJev annotation policy, not accounting standards or investment advice.",
        "outputs": ["pages.jsonl", "annotations.jsonl", "label_schema.json", "manifest.json", "validation_report.json"],
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "status": "passed",
        "selected_page_count": len(pages),
        "annotation_count": len(annotations),
        "new_selected_page_count": len(new_pages),
        "new_annotation_count": len(new_annotations),
        "excerpt_errors": excerpt_errors,
        "record_validation_errors": schema_errors,
        "broken_link_errors": broken_links,
        "annotation_status": {"seed_pending_human_review": len(annotations)},
        "new_records_by_issuer": {
            source["issuer"]: sum(record["issuer"] == source["issuer"] for record in new_annotations)
            for source in SOURCES.values()
        },
    }
    (OUTPUT / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / "README.md").write_text(
        "# FinJev core financial annotation seed set v0.2\n\n"
        "This version preserves all v0.1 seed records and adds only high-information pages from "
        "Tianjin Futong Information (2023) and Langfang Development (2024). It is a multi-issuer "
        "development seed, not a human-adjudicated gold benchmark.\n\n"
        "Run `uv run finjev-audit-annotations data/annotation_set_v0.2` for the current quality report.\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
