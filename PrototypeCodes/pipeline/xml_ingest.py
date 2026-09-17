from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .artifacts import ArtifactDefinition, artifact_folder_name, file_hash
from .config import ARTIFACT_ROOT, PIPELINE_VERSION, ROOT, XML_INPUTS
from .control import ControlWorkbook
from .cross_validation import cross_artifact_issues
from .csv_companion import json_to_csv, mtime_ns, write_json_atomic
from .dependency_graph import ARTIFACT_ORDER, dependency_material
from .models import model_for


XML_CONVERTER_VERSION = "sdmx_xml_mechanical_v1"


def _local(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _elements(root: ET.Element, *names: str) -> list[ET.Element]:
    accepted = set(names)
    return [element for element in root.iter() if _local(element) in accepted]


def _children(root: ET.Element, *names: str) -> list[ET.Element]:
    accepted = set(names)
    return [element for element in list(root) if _local(element) in accepted]


def _text(element: ET.Element | None, default: str = "not stated in XML") -> str:
    if element is None:
        return default
    value = " ".join(part.strip() for part in element.itertext() if part.strip())
    return value or default


def _named(element: ET.Element, name: str, default: str = "not stated in XML") -> str:
    candidates = _children(element, name)
    english = next((item for item in candidates if item.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"), None)
    return _text(english or (candidates[0] if candidates else None), default)


def _first_descendant(element: ET.Element, *names: str) -> ET.Element | None:
    accepted = set(names)
    return next((item for item in element.iter() if item is not element and _local(item) in accepted), None)


def _reference(value: str | None) -> tuple[str | None, str | None, str | None]:
    if not value:
        return None, None, None
    match = re.search(r"(?:=|^)([A-Za-z][A-Za-z0-9_.-]*):([A-Za-z][A-Za-z0-9_.-]*)\(([^)]+)\)", value)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None, value.strip(), None


def _descendant_reference(element: ET.Element, class_name: str | None = None) -> tuple[str | None, str | None, str | None]:
    for item in element.iter():
        if _local(item) == "Ref" and (class_name is None or item.attrib.get("class") == class_name):
            return item.attrib.get("agencyID"), item.attrib.get("id"), item.attrib.get("version")
    for item in element.iter():
        text = (item.text or "").strip()
        if text and (class_name is None or class_name in text):
            result = _reference(text)
            if result[1]:
                return result
    return None, None, None


def _base(artifact: ArtifactDefinition, source: Path, source_hash: str, artifact_type: str) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "source_report": source.name,
        "source_sha256": source_hash,
        "principles_file": artifact.path.name,
        "principles_sha256": artifact.sha256,
        "retrieved_chunk_ids": [],
        "standard_references": [],
        "limitations": [
            "Mechanically converted from XML; no AI interpretation was used.",
            "Fields absent from the XML are explicitly marked as not stated or inferred only from XML structure.",
        ],
    }


def _concept_schemes(root: ET.Element, artifact: ArtifactDefinition, source: Path, digest: str) -> dict[str, Any]:
    schemes = []
    codelist_concepts = {
        component.attrib.get("conceptRef") or component.attrib.get("id")
        for component in _elements(root, "Dimension", "TimeDimension", "PrimaryMeasure", "Measure", "Attribute")
    }
    for scheme in _elements(root, "ConceptScheme"):
        scheme_id = scheme.attrib.get("id", "UNKNOWN_CONCEPT_SCHEME")
        name = _named(scheme, "Name", scheme_id)
        concepts = []
        for concept in _children(scheme, "Concept"):
            concept_id = concept.attrib.get("id", "UNKNOWN_CONCEPT")
            concept_name = _named(concept, "Name", concept_id)
            definition = _named(concept, "Description", concept_name)
            representation = "Coded or structured according to the governing DSD" if concept_id in codelist_concepts else "String"
            if concept_id == "TIME_PERIOD":
                representation = "Observational time period"
            elif concept_id == "OBS_VALUE":
                representation = "Numeric"
            concepts.append({
                "concept_id": concept_id, "name": concept_name, "definition": definition,
                "context": f"Imported from XML concept scheme {scheme_id}",
                "recommended_representation": representation,
                "standard_source_agency": scheme.attrib.get("agencyID", "not stated"),
                "standard_scheme_id": scheme_id,
                "standard_version": scheme.attrib.get("version", "not stated"),
                "source_url": "not stated in XML", "local_notes": "Mechanically imported from SDMX XML.",
                "evidence_quote": concept_name,
            })
        if concepts:
            schemes.append({
                "scheme_id": scheme_id, "name": name,
                "agency_id": scheme.attrib.get("agencyID", "UNKNOWN_AGENCY"),
                "version": scheme.attrib.get("version", "not stated"), "concepts": concepts,
            })
    value = _base(artifact, source, digest, "CONCEPT_SCHEME")
    value["concept_schemes"] = schemes
    return value


def _codelists(root: ET.Element, artifact: ArtifactDefinition, source: Path, digest: str) -> dict[str, Any]:
    result = []
    for element in _elements(root, "Codelist", "CodeList"):
        codelist_id = element.attrib.get("id", "UNKNOWN_CODELIST")
        name = _named(element, "Name", codelist_id)
        codes = []
        for code in _children(element, "Code"):
            code_id = code.attrib.get("id") or code.attrib.get("value") or "UNKNOWN"
            label = _named(code, "Name", _named(code, "Description", code_id))
            description = _named(code, "Description", label)
            codes.append({
                "code": code_id, "name": label, "definition": description,
                "parent_code": code.attrib.get("parentCode"), "status": "ACTIVE",
                "evidence_quote": label, "local_creation_justification": None,
            })
        if codes:
            result.append({
                "codelist_id": codelist_id, "name": name,
                "agency_id": element.attrib.get("agencyID", "UNKNOWN_AGENCY"),
                "version": element.attrib.get("version", "not stated"),
                "source_url": "not stated in XML", "maintenance_status": "AUTHORITATIVE_REFERENCE",
                "verification_status": "CONFIRMED", "date_checked": date.today().isoformat(),
                "scope_notes": "Mechanically imported from the supplied SDMX XML.", "codes": codes,
            })
    value = _base(artifact, source, digest, "CODELISTS")
    value["codelists"] = result
    return value


def _component_reference(component: ET.Element) -> tuple[str, str | None, str | None, str | None]:
    concept_id = component.attrib.get("conceptRef") or component.attrib.get("id")
    if not concept_id:
        identity = _first_descendant(component, "ConceptIdentity")
        _, parsed, _ = _descendant_reference(identity or component, "Concept")
        concept_id = parsed
        if not concept_id and identity is not None:
            concept_id = (_text(identity, "UNKNOWN").rsplit(".", 1)[-1])
    codelist_id = component.attrib.get("codelist")
    agency = component.attrib.get("codelistAgency")
    version = component.attrib.get("codelistVersion")
    if not codelist_id:
        representation = _first_descendant(component, "LocalRepresentation")
        ref_agency, ref_id, ref_version = _descendant_reference(representation or component, "Codelist")
        if ref_id:
            agency, codelist_id, version = ref_agency, ref_id, ref_version
        elif representation is not None:
            enumeration = _first_descendant(representation, "Enumeration")
            if enumeration is not None:
                ref_agency, ref_id, ref_version = _reference(_text(enumeration, ""))
                agency, codelist_id, version = ref_agency, ref_id, ref_version
    return concept_id or "UNKNOWN_CONCEPT", agency, codelist_id, version


def _structures(root: ET.Element, artifact: ArtifactDefinition, source: Path, digest: str) -> dict[str, Any]:
    structures = []
    for dsd in _elements(root, "KeyFamily", "DataStructure"):
        dsd_id = dsd.attrib.get("id")
        if not dsd_id:
            continue
        name = _named(dsd, "Name", dsd_id)
        components = []
        position = 0
        for component in dsd.iter():
            tag = _local(component)
            if tag not in {"Dimension", "TimeDimension", "PrimaryMeasure", "Measure", "Attribute"}:
                continue
            if not (component.attrib.get("conceptRef") or component.attrib.get("id") or _first_descendant(component, "ConceptIdentity")):
                continue
            position += 1
            concept_id, cl_agency, cl_id, cl_version = _component_reference(component)
            role = "TIME" if tag == "TimeDimension" else "MEASURE" if tag in {"PrimaryMeasure", "Measure"} else "ATTRIBUTE" if tag == "Attribute" else "DIMENSION"
            text_format = _first_descendant(component, "TextFormat")
            data_type = (text_format.attrib.get("textType") if text_format is not None else None) or ("String" if role != "MEASURE" else "Double")
            representation = f"Coded by {cl_id}" if cl_id else data_type
            raw_usage = component.attrib.get("assignmentStatus") or component.attrib.get("usage") or "Mandatory"
            usage = "MANDATORY" if raw_usage.lower() in {"mandatory", "required"} else "CONDITIONAL" if raw_usage.lower() == "conditional" else "OPTIONAL"
            attachment = component.attrib.get("attachmentLevel")
            attachment = attachment.upper() if attachment else ("OBSERVATION" if role == "ATTRIBUTE" else None)
            components.append({
                "position": int(component.attrib.get("position", position)) if role in {"DIMENSION", "TIME"} else None,
                "concept_id": concept_id, "role": role, "representation": representation,
                "codelist_agency": cl_agency, "codelist_id": cl_id, "codelist_version": cl_version,
                "data_type": data_type, "usage_status": usage, "attachment_level": attachment,
                "notes": f"Mechanically extracted from XML {tag}.", "evidence_quote": name,
            })
        structures.append({
            "dsd_id": dsd_id, "name": name, "agency_id": dsd.attrib.get("agencyID", "UNKNOWN_AGENCY"),
            "version": dsd.attrib.get("version", "not stated"),
            "statistical_scope": root.attrib.get("title", name), "components": components,
        })
    value = _base(artifact, source, digest, "DSD_KEY_FAMILY")
    value["data_structures"] = structures
    value["structure_separation_rationale"] = "Each distinct DSD/Key Family present in the XML is preserved as a separate structure."
    return value


def _dataflows(root: ET.Element, artifact: ArtifactDefinition, source: Path, digest: str) -> dict[str, Any]:
    flows = []
    logical = _elements(root, "LogicalDefinition")
    candidates = logical or [item for item in _elements(root, "Dataflow") if item.attrib.get("id")]
    for flow in candidates:
        flow_id = flow.attrib.get("id", "UNKNOWN_DATAFLOW")
        name = _named(flow, "Name", flow_id)
        governing = _first_descendant(flow, "GoverningKeyFamily", "Structure")
        agency = dsd_id = version = None
        if governing is not None and _local(governing) == "GoverningKeyFamily":
            agency, dsd_id, version = governing.attrib.get("agencyID"), governing.attrib.get("id"), governing.attrib.get("version")
        elif governing is not None:
            agency, dsd_id, version = _descendant_reference(governing, "DataStructure")
            if not dsd_id:
                agency, dsd_id, version = _reference(_text(governing, ""))
        flows.append({
            "dataflow_id": flow_id, "name": name, "agency_id": flow.attrib.get("agencyID", "UNKNOWN_AGENCY"),
            "version": flow.attrib.get("version", "not stated"), "dsd_id": dsd_id or "UNKNOWN_DSD",
            "dsd_agency_id": agency or flow.attrib.get("agencyID", "UNKNOWN_AGENCY"),
            "dsd_version": version or "not stated", "description": _named(flow, "Description", name),
            "coverage": root.attrib.get("title", name), "evidence_quote": name,
        })
    value = _base(artifact, source, digest, "DATAFLOW")
    value["dataflows"] = flows
    return value


def _metadata_structures(root: ET.Element, artifact: ArtifactDefinition, source: Path, digest: str) -> dict[str, Any]:
    structures = []
    for msd in _elements(root, "MetadataStructureDefinition", "MetadataStructure"):
        msd_id = msd.attrib.get("id")
        if not msd_id:
            continue
        name = _named(msd, "Name", msd_id)
        concepts = []
        seen = set()
        for attribute in _elements(msd, "MetadataAttribute"):
            concept_id = attribute.attrib.get("conceptRef") or attribute.attrib.get("id")
            if not concept_id:
                _, concept_id, _ = _descendant_reference(attribute, "Concept")
            if not concept_id or concept_id in seen:
                continue
            seen.add(concept_id)
            text_format = _first_descendant(attribute, "TextFormat")
            representation = (text_format.attrib.get("textType") if text_format is not None else None) or "String"
            required = attribute.attrib.get("usageStatus", "").lower() == "mandatory" or attribute.attrib.get("minOccurs") == "1"
            concepts.append({
                "concept_id": concept_id, "name": concept_id.replace("_", " ").title(),
                "definition": f"Metadata concept {concept_id} imported from {msd_id}.",
                "representation": representation, "required": required,
                "usage_status": "MANDATORY" if required else "OPTIONAL", "target_attachment": "DATAFLOW",
                "extraction_guidance": "Use the value encoded in the XML metadata report.",
                "source_standard": f"SDMX XML {root.attrib.get('sdmxVersion', 'unknown')}",
                "source_url": "not stated in XML",
            })
        structures.append({
            "msd_id": msd_id, "name": name, "agency_id": msd.attrib.get("agencyID", "UNKNOWN_AGENCY"),
            "version": msd.attrib.get("version", "not stated"), "concepts": concepts,
        })
    value = _base(artifact, source, digest, "METADATA_STRUCTURE_DEFINITION_MSD")
    value["metadata_structures"] = structures
    return value


def _metadata_sets(root: ET.Element, artifact: ArtifactDefinition, source: Path, digest: str) -> dict[str, Any]:
    exports = _elements(root, "MetadataSetExport")
    scope = exports[0] if exports else root
    header_id = _text(_first_descendant(scope, "ID"), f"METADATA_SET_{source.stem}")
    msd_ref = _text(_first_descendant(scope, "MetadataStructureRef"), "")
    if not msd_ref:
        structures = _elements(scope, "Structure")
        structure = next(
            (item for item in structures if "MetadataStructure=" in (item.text or "")),
            structures[0] if structures else None,
        )
        _, msd_ref, _ = _reference((structure.text or "").strip() if structure is not None else "")
    target_value = _first_descendant(scope, "ComponentValue", "ReferenceValue")
    _, target_id, _ = _reference(_text(target_value, "UNKNOWN_DATAFLOW"))
    values = []
    for item in _elements(scope, "ReportedAttribute"):
        concept_id = item.attrib.get("conceptID") or item.attrib.get("id") or "UNKNOWN_METADATA_CONCEPT"
        value_text = _text(_first_descendant(item, "Value"), _text(item))
        values.append({
            "concept_id": concept_id, "value": value_text, "evidence_quote": value_text,
            "source_location": f"XML metadata attribute {concept_id}",
        })
    value = _base(artifact, source, digest, "METADATA_SET")
    value["metadata_sets"] = [{
        "metadata_set_id": re.sub(r"[^A-Za-z0-9_.-]", "_", header_id),
        "msd_id": msd_ref or "UNKNOWN_MSD", "target_id": target_id or "UNKNOWN_DATAFLOW",
        "target_type": "DATAFLOW", "values": values,
    }]
    return value


def _templates(root: ET.Element, artifact: ArtifactDefinition, source: Path, digest: str) -> dict[str, Any]:
    templates = []
    for template in _elements(root, "AIFillableDataTemplate"):
        _, dsd_id, _ = _reference(template.attrib.get("dsd"))
        columns = []
        for column in _elements(template, "Column"):
            role_raw = column.attrib.get("role", "attribute").lower()
            role = "TIME" if role_raw == "timedimension" else "MEASURE" if role_raw == "measure" else "DIMENSION" if role_raw == "dimension" else "ATTRIBUTE"
            columns.append({
                "column_id": column.attrib.get("id", "UNKNOWN_COLUMN"), "role": role,
                "required": column.attrib.get("required", "false").lower() == "true",
                "data_type": "Number" if role == "MEASURE" else "ObservationalTimePeriod" if role == "TIME" else "String",
                "codelist_id": column.attrib.get("codelist"),
                "description": f"Mechanically imported XML template column {column.attrib.get('id', 'UNKNOWN_COLUMN')}.",
            })
        observations = []
        for observation in _elements(template, "Observation"):
            row_values = [
                {"column_id": item.attrib.get("concept", "UNKNOWN_COLUMN"), "value": item.attrib.get("value")}
                for item in _children(observation, "Value")
            ]
            evidence = next((str(item["value"]) for item in row_values if item["value"] not in (None, "")), root.attrib.get("title", source.stem))
            observations.append({"dsd_id": dsd_id or "UNKNOWN_DSD", "values": row_values, "evidence_quote": evidence})
        templates.append({
            "template_id": f"TPL_{dsd_id or source.stem.upper()}", "dsd_id": dsd_id or "UNKNOWN_DSD",
            "columns": columns, "observations": observations,
        })
    value = _base(artifact, source, digest, "AI_FILLABLE_DATA_TEMPLATE")
    value["templates"] = templates
    return value


def _codebook(root: ET.Element, artifact: ArtifactDefinition, source: Path, digest: str) -> dict[str, Any]:
    concept_names = {}
    for scheme in _elements(root, "ConceptScheme"):
        for concept in _children(scheme, "Concept"):
            concept_names[concept.attrib.get("id")] = _named(concept, "Name", concept.attrib.get("id", "Unknown"))
    template = next(iter(_elements(root, "AIFillableDataTemplate")), None)
    fields = []
    if template is not None:
        for column in _elements(template, "Column"):
            field_id = column.attrib.get("id", "UNKNOWN_FIELD")
            role_raw = column.attrib.get("role", "attribute").lower()
            role = "TIME" if role_raw == "timedimension" else "MEASURE" if role_raw == "measure" else "DIMENSION" if role_raw == "dimension" else "ATTRIBUTE"
            fields.append({
                "field_id": field_id, "name": concept_names.get(field_id, field_id.replace("_", " ").title()),
                "definition": f"Field {field_id} mechanically imported from the XML template.",
                "role": role, "representation": f"Coded by {column.attrib['codelist']}" if column.attrib.get("codelist") else "Number" if role == "MEASURE" else "String",
                "codelist_id": column.attrib.get("codelist"),
                "required": column.attrib.get("required", "false").lower() == "true",
                "example": next((item.attrib.get("value") for item in _elements(template, "Value") if item.attrib.get("concept") == field_id), "not stated"),
                "source_standard": f"SDMX XML {root.attrib.get('sdmxVersion', 'unknown')}", "source_url": "not stated in XML",
            })
    mappings = []
    container = next(iter(_elements(root, "CodebookAndSourceMapping")), None)
    if container is not None:
        for item in _elements(container, "Field"):
            target = item.attrib.get("targetConcept", "UNKNOWN_FIELD")
            mappings.append({
                "source_value": item.attrib.get("source", "not stated"), "source_context": "XML FieldMappings",
                "target_field": target, "target_code": None, "target_code_label": None,
                "mapping_type": "EXACT" if item.attrib.get("status") == "accepted" else "UNRESOLVED",
                "target_standard": "Accepted XML codebook field", "notes": "Mechanically imported field mapping.",
                "evidence_quote": item.attrib.get("source", "not stated"),
            })
        for concept in _elements(container, "Concept"):
            target_field = concept.attrib.get("id", "UNKNOWN_FIELD")
            for item in _children(concept, "Map"):
                mappings.append({
                    "source_value": item.attrib.get("source", "not stated"), "source_context": f"XML ValueMappings for {target_field}",
                    "target_field": target_field, "target_code": item.attrib.get("target"),
                    "target_code_label": item.attrib.get("source"),
                    "mapping_type": "EXACT" if item.attrib.get("status") == "accepted" else "UNRESOLVED",
                    "target_standard": concept.attrib.get("codelist", "XML mapping"), "notes": "Mechanically imported value mapping.",
                    "evidence_quote": item.attrib.get("source", "not stated"),
                })
        for item in _elements(container, "MetadataField"):
            mappings.append({
                "source_value": item.attrib.get("source", "not stated"), "source_context": "XML MetadataMappings",
                "target_field": item.attrib.get("targetAttribute", "UNKNOWN_METADATA_FIELD"),
                "target_code": None, "target_code_label": None,
                "mapping_type": "EXACT" if item.attrib.get("status") == "accepted" else "UNRESOLVED",
                "target_standard": item.attrib.get("msd", "XML MSD"), "notes": "Mechanically imported metadata mapping.",
                "evidence_quote": item.attrib.get("source", "not stated"),
            })
    value = _base(artifact, source, digest, "CODEBOOK_AND_SOURCE_MAPPING")
    value["fields"] = fields
    value["source_value_mappings"] = mappings
    value["unresolved"] = []
    return value


BUILDERS = {
    "CONCEPT_SCHEME": _concept_schemes,
    "CODELISTS": _codelists,
    "DSD_KEY_FAMILY": _structures,
    "DATAFLOW": _dataflows,
    "METADATA_STRUCTURE_DEFINITION_MSD": _metadata_structures,
    "METADATA_SET": _metadata_sets,
    "AI_FILLABLE_DATA_TEMPLATE": _templates,
    "CODEBOOK_AND_SOURCE_MAPPING": _codebook,
}


def convert_xml(source: Path, artifacts: list[ArtifactDefinition]) -> tuple[str, dict[str, dict[str, Any]]]:
    root = ET.parse(source).getroot()
    version = root.attrib.get("sdmxVersion", "unknown")
    digest = file_hash(source)
    values = {artifact.key: BUILDERS[artifact.key](root, artifact, source, digest) for artifact in artifacts}
    for artifact in artifacts:
        values[artifact.key] = model_for(artifact.key).model_validate(values[artifact.key]).model_dump(mode="json")
    return version, values


def run_xml_ingestion(artifacts: list[ArtifactDefinition], control: ControlWorkbook) -> bool:
    print("\nMechanical XML ingestion stage")
    rank = {key: index for index, key in enumerate(ARTIFACT_ORDER)}
    ordered = sorted(artifacts, key=lambda item: rank.get(item.key, len(rank)))
    all_success = True
    for source in sorted(XML_INPUTS.rglob("*.xml")):
        relative = source.relative_to(ROOT).as_posix()
        try:
            root = ET.parse(source).getroot()
            version = root.attrib.get("sdmxVersion", "unknown")
            row, changed = control.sync_xml_file(source, relative, file_hash(source), version)
            expected_hash = hashlib.sha256(
                f"{file_hash(source)}|{XML_CONVERTER_VERSION}|{PIPELINE_VERSION}".encode()
            ).hexdigest()
            current = not changed and control.get(row, "XML_STATUS") in {"SUCCESS", "MODIFIED"}
            if current:
                for artifact in ordered:
                    output = ARTIFACT_ROOT / artifact_folder_name(artifact.key) / f"{source.stem}.json"
                    current = current and output.exists() and control.get(row, f"{artifact.key}_INPUT_HASH") == expected_hash
            if current:
                print(f"  {source.name}: SKIPPED (current XML conversion)")
                continue
            control.stage(row, "XML", "RUNNING")
            _, values = convert_xml(source, ordered)
            for artifact in ordered:
                output = ARTIFACT_ROOT / artifact_folder_name(artifact.key) / f"{source.stem}.json"
                write_json_atomic(output, values[artifact.key])
                json_to_csv(output, output.with_suffix(".csv"))
                control.set(row, f"{artifact.key}_PRINCIPLES_HASH", artifact.sha256, save=False)
                control.set(row, f"{artifact.key}_INPUT_HASH", expected_hash, save=False)
                control.set(row, f"{artifact.key}_JSON_PATH", str(output.relative_to(ROOT)), save=False)
                control.set(row, f"{artifact.key}_JSON_MTIME_NS", mtime_ns(output), save=False)
                control.set(row, f"{artifact.key}_CSV_MTIME_NS", mtime_ns(output.with_suffix('.csv')), save=False)
                control.set(row, f"{artifact.key}_CSV_STATUS", "SUCCESS", save=False)
                control.set(row, f"{artifact.key}_STATUS", "SUCCESS", save=False)
                control.set(row, f"{artifact.key}_AGGREGATED", "NO", save=False)
            for artifact in ordered:
                _, _, dependencies = dependency_material(artifact.key, source.stem)
                issues = cross_artifact_issues(artifact.key, values[artifact.key], dependencies)
                if issues:
                    raise ValueError(f"{artifact.key}: {'; '.join(issues)}")
            control.stage(row, "CONSISTENCY", "SUCCESS")
            control.set(row, "CONSISTENCY_PASSES", 1, save=False)
            control.stage(row, "XML", "SUCCESS")
            print(f"  {source.name}: SUCCESS (SDMX {version}; 8 artifacts, no AI)")
        except Exception as error:
            row = control.find_row(relative)
            if row is not None:
                control.stage(row, "XML", "FAILED", f"{type(error).__name__}: {error}")
                control.stage(row, "CONSISTENCY", "FAILED", f"XML conversion failed: {type(error).__name__}: {error}")
            print(f"  {source.name}: FAILED ({type(error).__name__}: {error})")
            all_success = False
    return all_success
