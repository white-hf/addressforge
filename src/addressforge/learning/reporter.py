import json
from datetime import datetime

I18N = {
    "en": {
        "title": "AddressForge Evaluation Report",
        "promote": "Promote Recommended",
        "comparison": "Release Comparison",
        "buckets": "Error Buckets",
        "total_errors": "Total Errors",
    },
    "zh": {
        "title": "AddressForge 评估报告",
        "promote": "推荐发布",
        "comparison": "发布对比 (Release Comparison)",
        "buckets": "错误分桶 (Error Buckets)",
        "total_errors": "总错误数",
    }
}

def generate_markdown_report(metrics_json: dict, locale: str = "en") -> str:
    i18n = I18N.get(locale, I18N["en"])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = [f"# {i18n['title']} - {timestamp}", ""]
    
    # Release Comparison
    if "release_comparison" in metrics_json:
        comp = metrics_json["release_comparison"]
        report.append(f"## {i18n['comparison']}")
        report.append(f"- {i18n['promote']}: **{'✅ ' + ('Yes' if locale == 'en' else '是') if comp.get('promote_recommended') else '❌ ' + ('No' if locale == 'en' else '否')}**")
        report.append("| Metric | Candidate | Active | Delta | Passed |")
        report.append("| --- | --- | --- | --- | --- |")
        for check in comp.get("gate_checks", []):
            report.append(f"| {check['metric']} | {check['candidate']} | {check['active']} | {check['delta']} | {'✅' if check['passed'] else '❌'} |")
        report.append("")

    # Error Buckets
    report.append(f"## {i18n['buckets']}")
    for field in ["decision", "building_type", "unit_number"]:
        buckets = metrics_json.get(f"{field}_error_buckets")
        if buckets:
            if isinstance(buckets, dict) and "bucket_counts" in buckets:
                bucket_counts = buckets.get("bucket_counts") or {}
                total_errors = int(buckets.get("total_errors") or sum(bucket_counts.values()))
            else:
                bucket_counts = buckets if isinstance(buckets, dict) else {}
                total_errors = sum(bucket_counts.values())
            report.append(f"### {field.upper()}")
            report.append(f"- {i18n['total_errors']}: {total_errors}")
            for bucket, count in bucket_counts.items():
                report.append(f"- {bucket}: {count}")
    
    return "\n".join(report)
