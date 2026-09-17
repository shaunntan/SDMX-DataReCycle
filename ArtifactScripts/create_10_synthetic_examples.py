#!/usr/bin/env python3
"""Create ten reproducible, structurally diverse statistical PDF reports."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "Inputs"
SEED = 20260916


@dataclass(frozen=True)
class TableSpec:
    title: str
    headers: list[str]
    rows: list[list[str]]
    footnote: str


@dataclass(frozen=True)
class ReportSpec:
    filename: str
    title: str
    publisher: str
    publication_date: str
    methodology: str
    source: str
    definitions: str
    caveats: str
    revision_policy: str
    tables: list[TableSpec]


def fmt(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}"


def rows_for_cross_product(dimensions, value_fn):
    rows = []

    def visit(prefix, index):
        if index == len(dimensions):
            rows.append(prefix + value_fn(prefix))
            return
        for item in dimensions[index]:
            visit(prefix + [str(item)], index + 1)

    visit([], 0)
    return rows


def build_specs() -> list[ReportSpec]:
    rng = random.Random(SEED)
    reports: list[ReportSpec] = []

    labor_1 = rows_for_cross_product(
        [["Northland", "Centralia", "South Coast"], ["Women", "Men", "Total"], ["2025-Q1", "2025-Q2"]],
        lambda row: [fmt(4.2 + rng.random() * 5.5), "Percent", "Provisional" if row[2] == "2025-Q2" else "Final"],
    )
    labor_2 = rows_for_cross_product(
        [["Manufacturing", "Construction", "Information services"], ["2025-01", "2025-02", "2025-03"]],
        lambda row: [str(rng.randint(820, 4200)), "Open positions", "Seasonally adjusted"],
    )
    reports.append(ReportSpec(
        "example_01_labour_market.pdf", "Quarterly Labour Market Bulletin 2025", "Synthetic Labour Observatory",
        "20 August 2026", "Unemployment rates are synthetic survey estimates for persons aged 15-64. Vacancy counts are compiled independently from a synthetic employer survey and use a monthly reference period.",
        "Synthetic Labour Force Survey and Synthetic Establishment Vacancy Survey.",
        "Unemployment rate is unemployed persons as a percentage of the labour force. A job vacancy is an unfilled position available for immediate recruitment.",
        "Quarterly rates and monthly vacancy counts represent different statistical structures. Total sex coverage includes respondents outside the displayed women/men categories; it must not be inferred by summing displayed rows.",
        "Provisional quarterly estimates are revised after annual weighting. Final vacancy counts may be corrected for reporting errors.",
        [TableSpec("Table 1. Unemployment rate by region, sex and quarter", ["Region", "Sex", "Quarter", "Value", "Unit", "Status"], labor_1, "2025-Q2 rates are provisional."), TableSpec("Table 2. Job vacancies by industry and month", ["Industry", "Month", "Vacancies", "Unit", "Adjustment"], labor_2, "Industry labels are local aggregates and are not confirmed ISIC categories.")],
    ))

    health_1 = rows_for_cross_product(
        [["Northland", "Centralia", "South Coast"], ["Circulatory diseases", "Neoplasms"], ["45-64", "65+"], [2023, 2024]],
        lambda row: [str(rng.randint(80, 760)), "Deaths", "Provisional" if row[3] == "2024" else "Final"],
    )
    health_2 = rows_for_cross_product(
        [["Public", "Private non-profit", "Private for-profit"], [2023, 2024]],
        lambda row: [str(rng.randint(1200, 4600)), "Beds", "Estimated" if row[0] == "Private for-profit" and row[1] == "2024" else "Final"],
    )
    reports.append(ReportSpec(
        "example_02_health_system.pdf", "Health Outcomes and Capacity Report", "Synthetic Public Health Agency", "3 July 2026",
        "Deaths are synthetic registered events classified by underlying cause and age group. Hospital beds are a year-end stock measure collected from facilities and should not share the mortality DSD.",
        "Synthetic Civil Registration System and Synthetic Facility Census.", "Registered deaths count events during the calendar year. Available beds are staffed beds available on 31 December.",
        "Cause labels resemble broad ICD families but no ICD version is confirmed. Private-sector bed reporting is incomplete in 2024.",
        "Provisional death counts are revised when late registrations arrive. Estimated bed counts are replaced after facility validation.",
        [TableSpec("Table 1. Registered deaths by area, cause, age and year", ["Area", "Cause", "Age", "Year", "Value", "Unit", "Status"], health_1, "2024 death counts are provisional."), TableSpec("Table 2. Available hospital beds by ownership", ["Ownership", "Year", "Value", "Unit", "Status"], health_2, "Private for-profit 2024 values are estimated.")],
    ))

    education_1 = rows_for_cross_product(
        [["Primary", "Lower secondary", "Upper secondary"], ["Female", "Male", "Total"], [2024, 2025]],
        lambda row: [str(rng.randint(42000, 165000)), "Students", "Provisional" if row[2] == "2025" else "Final"],
    )
    education_2 = rows_for_cross_product(
        [["Lowest quintile", "Middle quintile", "Highest quintile"], ["Female", "Male"], [2024]],
        lambda row: [fmt(58 + rng.random() * 36), "Percent", "Modelled estimate"],
    )
    reports.append(ReportSpec(
        "example_03_education.pdf", "Education Participation and Completion 2025", "Synthetic Ministry of Learning", "12 June 2026",
        "Enrollment is an administrative headcount by education level. Completion rates are separately modelled household-survey estimates by wealth quintile and sex.",
        "Synthetic Education Management Information System and Synthetic Household Learning Survey.", "Enrollment counts learners registered on census day. Completion rate is the percentage of the relevant cohort completing the stated education cycle.",
        "Education-level labels require ISCED mapping review. Wealth quintiles are survey-specific and should not be silently mapped to a standard income classification.",
        "Administrative counts become final after duplicate removal. Modelled completion estimates may change with revised survey weights.",
        [TableSpec("Table 1. Enrollment by education level, sex and year", ["Education level", "Sex", "Year", "Value", "Unit", "Status"], education_1, "2025 enrollment is provisional."), TableSpec("Table 2. Lower-secondary completion by wealth quintile", ["Wealth quintile", "Sex", "Year", "Value", "Unit", "Status"], education_2, "All completion rates are modelled estimates.")],
    ))

    agriculture_1 = rows_for_cross_product(
        [["Rice", "Maize", "Cassava"], ["Northland", "Centralia", "South Coast"], [2024, 2025]],
        lambda row: [str(rng.randint(12000, 98000)), "Hectares", str(rng.randint(30000, 480000)), "Tonnes", "Forecast" if row[2] == "2025" else "Final"],
    )
    agriculture_2 = rows_for_cross_product(
        [["Urea", "Compound NPK"], ["2025-01", "2025-02", "2025-03", "2025-04"]],
        lambda row: [fmt(260 + rng.random() * 190, 2), "Local currency per 50 kg bag", "Observed"],
    )
    reports.append(ReportSpec(
        "example_04_agriculture.pdf", "Crop Production and Input Prices", "Synthetic Agricultural Statistics Bureau", "28 May 2026",
        "Crop area and production are annual farm-survey aggregates. Fertilizer retail prices come from a monthly outlet panel and form a separate price structure.",
        "Synthetic Annual Farm Survey and Synthetic Agricultural Price Panel.", "Harvested area counts hectares harvested. Production is crop output in metric tonnes. Retail price is the median observed price per 50 kg bag.",
        "Crop names are common labels and require classification review. The local currency is deliberately unnamed. Forecast production is not observed output.",
        "Forecasts are replaced by provisional estimates after harvest and finalized after survey reconciliation.",
        [TableSpec("Table 1. Crop area and production by region", ["Crop", "Region", "Year", "Area", "Area unit", "Production", "Production unit", "Status"], agriculture_1, "2025 area and production are forecasts."), TableSpec("Table 2. Fertilizer retail prices by month", ["Product", "Month", "Price", "Unit", "Status"], agriculture_2, "Products are local market categories, not verified CPC codes.")],
    ))

    prices_1 = rows_for_cross_product(
        [["Food and non-alcoholic beverages", "Housing and utilities", "Transport"], ["2025-01", "2025-02", "2025-03", "2025-04"]],
        lambda row: [fmt(105 + rng.random() * 14, 2), "Index, 2023=100", "Provisional" if row[1] == "2025-04" else "Final"],
    )
    prices_2 = rows_for_cross_product(
        [["Urban", "Rural"], ["Lowest quintile", "Highest quintile"], [2024]],
        lambda row: [fmt(1800 + rng.random() * 7200, 0), "Local currency per household per month", "Survey estimate"],
    )
    reports.append(ReportSpec(
        "example_05_prices_consumption.pdf", "Consumer Prices and Household Spending", "Synthetic National Statistics Institute", "9 May 2026",
        "The CPI is a monthly fixed-basket index classified by consumption division. Household spending is an annual survey estimate by residence and expenditure quintile and is not a CPI observation.",
        "Synthetic Consumer Price Survey and Synthetic Household Budget Survey.", "CPI measures price change relative to 2023=100. Household spending is mean monthly consumption expenditure per household.",
        "Consumption divisions resemble COICOP but the revision is not confirmed. The report does not name the local currency. Survey estimates are subject to sampling error.",
        "The latest CPI month is provisional. Household estimates are revised only for processing errors or new calibration weights.",
        [TableSpec("Table 1. Consumer price index by division and month", ["Division", "Month", "Index", "Unit", "Status"], prices_1, "April 2025 indices are provisional."), TableSpec("Table 2. Mean household spending by residence and quintile", ["Residence", "Expenditure quintile", "Year", "Value", "Unit", "Status"], prices_2, "Quintiles are defined within the synthetic survey distribution.")],
    ))

    energy_1 = rows_for_cross_product(
        [["Hydro", "Solar", "Natural gas"], ["2025-01", "2025-02", "2025-03"]],
        lambda row: [fmt(180 + rng.random() * 920, 1), "GWh", "Estimated" if row[0] == "Solar" and row[1] == "2025-03" else "Final"],
    )
    energy_2 = rows_for_cross_product(
        [["Electricity generation", "Road transport"], [2023, 2024]],
        lambda row: [fmt(1200 + rng.random() * 7800, 1), "kt CO2 equivalent", "Provisional" if row[1] == "2024" else "Final"],
    )
    reports.append(ReportSpec(
        "example_06_energy_emissions.pdf", "Energy Supply and Greenhouse Gas Indicators", "Synthetic Energy and Climate Office", "18 April 2026",
        "Electricity generation is compiled monthly from system operators. Emissions are annual inventory estimates by source sector using separate methods and classifications.",
        "Synthetic Electricity Dispatch Register and Synthetic Greenhouse Gas Inventory.", "Generation is electrical energy supplied to the grid. Emissions are expressed as thousand tonnes of carbon-dioxide equivalent.",
        "Energy-source labels are local operational groups. Emissions are model-dependent and 2024 inventory values are provisional.",
        "Estimated generation is replaced after meter reconciliation. Emission inventory years may be recalculated when methods improve.",
        [TableSpec("Table 1. Electricity generation by source and month", ["Energy source", "Month", "Value", "Unit", "Status"], energy_1, "Solar generation for March 2025 is estimated."), TableSpec("Table 2. Greenhouse gas emissions by source sector", ["Source sector", "Year", "Value", "Unit", "Status"], energy_2, "2024 inventory values are provisional.")],
    ))

    trade_1 = rows_for_cross_product(
        [["France", "Germany", "Thailand"], ["Food products", "Machinery"], ["2025-01", "2025-02"]],
        lambda row: [fmt(2.5 + rng.random() * 26, 2), "Million US dollars", "Provisional" if row[2] == "2025-02" else "Final"],
    )
    trade_2 = rows_for_cross_product(
        [["Food products", "Machinery", "Textiles"], [2024, 2025]],
        lambda row: [fmt(1.5 + rng.random() * 12, 2), "Percent", "Applied rate"],
    )
    reports.append(ReportSpec(
        "example_07_trade_tariffs.pdf", "Merchandise Trade and Applied Tariffs", "Synthetic Trade Statistics Authority", "30 March 2026",
        "Exports are customs values by partner, product group and month. Tariff rates are annual simple averages from a separate administrative schedule.",
        "Synthetic Customs Declaration System and Synthetic Applied Tariff Schedule.", "Export value is free-on-board customs value. Applied tariff is the simple average ad valorem rate for the displayed product group.",
        "Product groups are broad local aggregates and do not identify an HS revision. Partner labels require an explicit geography codelist decision. February exports are provisional.",
        "Provisional customs values are revised for late and amended declarations. Tariff schedules are revised when legal rates change.",
        [TableSpec("Table 1. Merchandise exports by partner and product", ["Partner area", "Product group", "Month", "Value", "Unit", "Status"], trade_1, "February 2025 export values are provisional."), TableSpec("Table 2. Applied tariff rate by product group", ["Product group", "Year", "Rate", "Unit", "Status"], trade_2, "Rates are simple averages and are not trade weighted.")],
    ))

    population_1 = rows_for_cross_product(
        [["Under 20", "20-29", "30-39", "40+"], [2023, 2024]],
        lambda row: [str(rng.randint(2200, 17400)), "Live births", "Provisional" if row[1] == "2024" else "Final"],
    )
    population_2 = rows_for_cross_product(
        [["Citizen", "Non-citizen"], ["Female", "Male"], [2023, 2024]],
        lambda row: [str(rng.randint(-1800, 8200)), "Persons", "Estimated"],
    )
    reports.append(ReportSpec(
        "example_08_population_migration.pdf", "Vital Events and International Migration", "Synthetic Population Register Office", "14 February 2026",
        "Births are registered events by age of mother. Net migration is an independently estimated annual balance by citizenship status and sex.",
        "Synthetic Birth Registration Database and Synthetic Migration Estimation System.", "Live births count registered live-born children. Net migration is immigration minus emigration and may be negative.",
        "Age groups describe the mother, not the child. Citizenship categories are administrative and should not be interpreted as ethnicity. Migration estimates contain model uncertainty.",
        "Late birth registrations revise provisional counts. Migration estimates are routinely revised when register linkage improves.",
        [TableSpec("Table 1. Live births by age of mother", ["Mother age", "Year", "Value", "Unit", "Status"], population_1, "2024 births are provisional."), TableSpec("Table 2. Net migration by citizenship and sex", ["Citizenship status", "Sex", "Year", "Net migration", "Unit", "Status"], population_2, "Negative values indicate net emigration.")],
    ))

    environment_1 = rows_for_cross_product(
        [["Station North", "Station Central", "Station Coast"], ["PM2.5", "Nitrogen dioxide"], ["2025-04-01", "2025-04-02", "2025-04-03"]],
        lambda row: [fmt(8 + rng.random() * 48, 1), "Micrograms per cubic metre", "Validated" if row[2] != "2025-04-03" else "Preliminary"],
    )
    environment_2 = rows_for_cross_product(
        [["Terrestrial", "Marine"], [2023, 2024]],
        lambda row: [fmt(420 + rng.random() * 2700, 1), "Square kilometres", "Estimated" if row[1] == "2024" else "Final"],
    )
    reports.append(ReportSpec(
        "example_09_environment.pdf", "Air Quality and Protected Areas", "Synthetic Environmental Monitoring Agency", "31 January 2026",
        "Air pollution observations are daily station averages by pollutant. Protected-area extent is a separate annual geospatial estimate by ecosystem type.",
        "Synthetic Air Monitoring Network and Synthetic Protected Areas Geodatabase.", "PM2.5 is particulate matter with aerodynamic diameter up to 2.5 micrometres. Protected extent is mapped designated area without overlap correction.",
        "Station measurements are point observations and do not represent population exposure. Protected-area estimates may double count overlapping designations.",
        "Preliminary air observations are validated within 60 days. Geospatial estimates are revised after boundary updates.",
        [TableSpec("Table 1. Daily air pollutant concentration by station", ["Station", "Pollutant", "Date", "Value", "Unit", "Status"], environment_1, "Observations for 3 April are preliminary."), TableSpec("Table 2. Protected-area extent by ecosystem", ["Ecosystem", "Year", "Extent", "Unit", "Status"], environment_2, "2024 extents are estimated and may overlap.")],
    ))

    tourism_1 = rows_for_cross_product(
        [["Europe", "East Asia", "Neighbouring countries"], ["2025-01", "2025-02", "2025-03"]],
        lambda row: [str(rng.randint(18000, 92000)), "Arrivals", "Provisional" if row[1] == "2025-03" else "Final"],
    )
    tourism_2 = rows_for_cross_product(
        [["Hotels", "Guest houses", "Resorts"], ["Northland", "Centralia", "South Coast"], ["2025-Q1"]],
        lambda row: [fmt(38 + rng.random() * 44), "Percent", "Survey estimate"],
    )
    reports.append(ReportSpec(
        "example_10_tourism.pdf", "Inbound Tourism and Accommodation Performance", "Synthetic Tourism Analytics Office", "16 January 2026",
        "Inbound arrivals are monthly border-entry counts by origin region. Accommodation occupancy is a quarterly establishment-survey ratio by accommodation category and destination region.",
        "Synthetic Border Movement Register and Synthetic Accommodation Survey.", "An arrival is one inbound trip by a non-resident visitor. Room occupancy is occupied room nights as a percentage of available room nights.",
        "Origin regions are report-specific aggregates. Arrivals count trips rather than unique people. Small guest houses are under-covered in the accommodation survey.",
        "The latest arrivals are provisional. Survey estimates may be revised after nonresponse adjustment.",
        [TableSpec("Table 1. Inbound visitor arrivals by origin region", ["Origin region", "Month", "Value", "Unit", "Status"], tourism_1, "March 2025 arrivals are provisional."), TableSpec("Table 2. Room occupancy by accommodation and destination", ["Accommodation", "Destination", "Quarter", "Rate", "Unit", "Status"], tourism_2, "Occupancy estimates exclude unregistered accommodation.")],
    ))
    return reports


def render_table(spec: TableSpec) -> Table:
    data = [spec.headers, *spec.rows]
    available = 260 * mm
    widths = [available / len(spec.headers)] * len(spec.headers)
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#155E75")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 6.5),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#94A3B8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#ECFEFF")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def render_report(spec: ReportSpec) -> Path:
    path = OUTPUT_DIR / spec.filename
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(
        str(path), pagesize=landscape(A4), rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm, title=spec.title, author=spec.publisher,
    )
    story = [
        Paragraph(spec.title, styles["Title"]),
        Paragraph(spec.publisher, styles["Heading2"]),
        Paragraph(f"Publication date: {spec.publication_date}", styles["Normal"]),
        Spacer(1, 4 * mm), Paragraph("Methodology", styles["Heading1"]), Paragraph(spec.methodology, styles["BodyText"]),
        Paragraph("Source description", styles["Heading1"]), Paragraph(spec.source, styles["BodyText"]),
        Paragraph("Definitions", styles["Heading1"]), Paragraph(spec.definitions, styles["BodyText"]),
        Paragraph("Caveats and limitations", styles["Heading1"]), Paragraph(spec.caveats, styles["BodyText"]),
        Paragraph("Revision policy", styles["Heading1"]), Paragraph(spec.revision_policy, styles["BodyText"]),
        Paragraph("Confidentiality", styles["Heading1"]), Paragraph("All records and values are synthetic. No person-level or confidential data are included.", styles["BodyText"]),
    ]
    for table_spec in spec.tables:
        story.extend([PageBreak(), Paragraph(table_spec.title, styles["Heading1"]), render_table(table_spec), Spacer(1, 3 * mm), Paragraph(f"Footnote: {table_spec.footnote}", styles["BodyText"])])
    document.build(story)
    return path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = [render_report(spec) for spec in build_specs()]
    print(f"Created {len(paths)} synthetic PDF reports:")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
