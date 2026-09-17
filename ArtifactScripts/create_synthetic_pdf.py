#!/usr/bin/env python3
from __future__ import annotations

import random
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "Inputs" / "sample_statistical_report.pdf"


def styled_table(data, widths):
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EAF2F8")]),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def main() -> None:
    random.seed(20260916)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=15 * mm, bottomMargin=15 * mm, title="Synthetic Statistical Outlook 2025")
    story = [
        Paragraph("Synthetic Statistical Outlook 2025", styles["Title"]),
        Paragraph("Published by the International Synthetic Statistics Office (ISSO)", styles["Heading2"]),
        Paragraph("Publication date: 15 September 2026", styles["Normal"]), Spacer(1, 6 * mm),
        Paragraph("Purpose", styles["Heading1"]),
        Paragraph("This synthetic report illustrates two distinct statistical domains: employment rates and government expenditure by function. All values and institutions are fictional; country names are used only as familiar statistical area labels.", styles["BodyText"]),
        Paragraph("Methodology", styles["Heading1"]),
        Paragraph("Employment rates are synthetic annual percentages of the population aged 25-54 that is employed. Values are disaggregated by reference area and sex. Government expenditure is synthetic annual expenditure in millions of national currency, classified by selected government functions. The two tables were generated independently and should not be forced into one statistical structure.", styles["BodyText"]),
        Paragraph("Source", styles["Heading1"]),
        Paragraph("ISSO Synthetic Labour Survey and ISSO Synthetic Government Finance Compilation. Reference periods are calendar years. Figures were generated with fixed random seed 20260916.", styles["BodyText"]),
        Paragraph("Definitions", styles["Heading1"]),
        Paragraph("Employment rate: employed persons aged 25-54 as a percentage of the corresponding population. Government expenditure: consolidated general-government outlays for the stated function, expressed in millions of national currency.", styles["BodyText"]),
        Paragraph("Limitations and caveats", styles["Heading1"]),
        Paragraph("The data are entirely synthetic and are not suitable for policy analysis. Cross-country expenditure levels are not comparable without currency conversion. Thailand 2024 expenditure values are estimated. France 2024 employment observations are provisional.", styles["BodyText"]),
        PageBreak(), Paragraph("Table 1. Employment rate by country, sex and year", styles["Heading1"]),
    ]
    employment = [["Country", "Sex", "Age group", "Year", "Employment rate", "Unit", "Status"]]
    bases = {"France": 79.0, "Germany": 80.3, "Thailand": 76.1}
    for country, base in bases.items():
        for sex, adjustment in (("Women", -2.4), ("Men", 2.1), ("Total", 0.0)):
            for year in (2023, 2024):
                value = round(base + adjustment + (year - 2023) * 0.6 + random.uniform(-0.25, 0.25), 1)
                status = "Provisional" if country == "France" and year == 2024 else "Final"
                employment.append([country, sex, "25-54 years", str(year), f"{value:.1f}", "Percent", status])
    story.extend([
        styled_table(employment, [27*mm, 20*mm, 22*mm, 14*mm, 27*mm, 18*mm, 22*mm]),
        Spacer(1, 3*mm), Paragraph("Footnote: France 2024 observations are provisional. Total includes women and men in this synthetic binary classification; it is not a universal definition of total population.", styles["BodyText"]),
        PageBreak(), Paragraph("Table 2. Government expenditure by function and year", styles["Heading1"]),
    ])
    expenditure = [["Country", "Function", "Year", "Expenditure", "Unit", "Status"]]
    for country, base in {"France": 122000, "Germany": 146000, "Thailand": 310000}.items():
        for function, factor in (("Health", 1.0), ("Education", 0.72)):
            for year in (2023, 2024):
                value = int(base * factor * (1 + 0.035 * (year - 2023)) + random.randint(-900, 900))
                status = "Estimated" if country == "Thailand" and year == 2024 else "Final"
                expenditure.append([country, function, str(year), f"{value:,}", "Million national currency", status])
    story.extend([
        styled_table(expenditure, [28*mm, 28*mm, 17*mm, 30*mm, 38*mm, 22*mm]),
        Spacer(1, 3*mm), Paragraph("Footnote: Thailand 2024 values are estimates. National-currency values must not be compared directly across countries. Functions are intended to correspond conceptually to health and education, but classification-version confirmation is required before assigning official COFOG codes.", styles["BodyText"]),
        Paragraph("Revision policy", styles["Heading1"]),
        Paragraph("Provisional and estimated observations may be revised in the next annual release. Final observations are not routinely revised unless a processing error is identified.", styles["BodyText"]),
        Paragraph("Confidentiality", styles["Heading1"]),
        Paragraph("The synthetic tables contain no person-level records and no confidential data.", styles["BodyText"]),
    ])
    document.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    main()

