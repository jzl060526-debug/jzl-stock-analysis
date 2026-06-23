# -*- coding: utf-8 -*-
"""报告导出模块。"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

from config import REPORT_DIR, APP_NAME
from strategy import generate_trade_script
from ui_components import format_df_for_display

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def export_excel(scan_df: pd.DataFrame, reference_df: pd.DataFrame, sector_df: pd.DataFrame) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"A股趋势波段扫描报告_{ts}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        format_df_for_display(scan_df if scan_df is not None else pd.DataFrame()).to_excel(writer, sheet_name="全A候选", index=False)
        format_df_for_display(reference_df if reference_df is not None else pd.DataFrame()).to_excel(writer, sheet_name="参考列表", index=False)
        format_df_for_display(sector_df if sector_df is not None else pd.DataFrame()).to_excel(writer, sheet_name="板块热度", index=False)
    return str(path)


def _table_from_df(df: pd.DataFrame, max_rows: int = 10):
    if df is None or df.empty:
        return [["暂无数据"]]
    small = format_df_for_display(df.head(max_rows).copy())
    cols = small.columns.tolist()[:8]
    data = [cols]
    for _, row in small[cols].iterrows():
        data.append([str(row.get(c, ""))[:28] for c in cols])
    return data


def export_pdf(scan_df: pd.DataFrame, reference_df: pd.DataFrame, sector_df: pd.DataFrame, market_summary: dict) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"A股趋势波段投研报告_{ts}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=1.2*cm, leftMargin=1.2*cm, topMargin=1.2*cm, bottomMargin=1.2*cm)
    styles = getSampleStyleSheet()
    for s in styles.byName.values():
        s.fontName = "STSong-Light"
    story = []
    story.append(Paragraph(APP_NAME, styles["Title"]))
    story.append(Paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("市场总结", styles["Heading2"]))
    summary_data = [["指标", "数值"]] + [[k, str(v)] for k, v in market_summary.items()]
    story.append(Table(summary_data, style=[("BACKGROUND", (0,0), (-1,0), colors.HexColor("#dbeafe")), ("GRID", (0,0), (-1,-1), 0.5, colors.grey), ("FONTNAME", (0,0), (-1,-1), "STSong-Light")]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("重点股票前10名", styles["Heading2"]))
    table = Table(_table_from_df(scan_df, 10), repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.35, colors.grey), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#dbeafe")), ("FONTNAME", (0,0), (-1,-1), "STSong-Light"), ("FONTSIZE", (0,0), (-1,-1), 7)]))
    story.append(table)
    story.append(PageBreak())
    story.append(Paragraph("参考列表", styles["Heading2"]))
    table2 = Table(_table_from_df(reference_df, 10), repeatRows=1)
    table2.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.35, colors.grey), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#dcfce7")), ("FONTNAME", (0,0), (-1,-1), "STSong-Light"), ("FONTSIZE", (0,0), (-1,-1), 7)]))
    story.append(table2)
    story.append(Spacer(1, 12))
    story.append(Paragraph("风险提示", styles["Heading2"]))
    story.append(Paragraph("本报告由规则系统生成，不构成投资建议；不自动下单；全A接口可能受网络和数据源稳定性影响。", styles["Normal"]))
    doc.build(story)
    return str(path)
