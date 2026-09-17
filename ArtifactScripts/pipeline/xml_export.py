from __future__ import annotations

import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import ArtifactDefinition, artifact_folder_name
from .config import FINAL_ARTIFACT_ROOT, FINAL_SDMX_ROOT, ROOT
from .control import ControlWorkbook
from .models import final_envelope_model


EXPORTER_VERSION = "final_sdmx_bundle_v1"
BUNDLE = "urn:example:sdmx-case-bundle:1.0"


def _q(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _add(parent: ET.Element, namespace: str, name: str, attributes: dict[str, Any] | None = None, text: Any = None) -> ET.Element:
    element = ET.SubElement(parent, _q(namespace, name), {key: str(value) for key, value in (attributes or {}).items() if value is not None})
    if text is not None:
        element.text = str(text)
    return element


def _plain(parent: ET.Element, name: str, attributes: dict[str, Any] | None = None) -> ET.Element:
    return ET.SubElement(parent, name, {key: str(value) for key, value in (attributes or {}).items() if value is not None})


def _name(parent: ET.Element, common: str, text: str) -> None:
    element = _add(parent, common, "Name", text=text)
    element.set("{http://www.w3.org/XML/1998/namespace}lang", "en")


def _urn(package: str, class_name: str, agency: str, artifact_id: str, version: str, item_id: str | None = None) -> str:
    value = f"urn:sdmx:org.sdmx.infomodel.{package}.{class_name}={agency}:{artifact_id}({version})"
    return f"{value}.{item_id}" if item_id else value


def _namespaces(version: str) -> dict[str, str]:
    marker = "2_1" if version == "2.1" else "3_0"
    return {
        "message": f"http://www.sdmx.org/resources/sdmxml/schemas/v{marker}/message",
        "structure": f"http://www.sdmx.org/resources/sdmxml/schemas/v{marker}/structure",
        "common": f"http://www.sdmx.org/resources/sdmxml/schemas/v{marker}/common",
        "generic": f"http://www.sdmx.org/resources/sdmxml/schemas/v{marker}/genericmetadata",
    }


def _register(version: str, namespaces: dict[str, str]) -> None:
    suffix = "21" if version == "2.1" else "30"
    ET.register_namespace("bundle", BUNDLE)
    ET.register_namespace(f"mes{suffix}", namespaces["message"])
    ET.register_namespace(f"str{suffix}", namespaces["structure"])
    ET.register_namespace(f"com{suffix}", namespaces["common"])
    ET.register_namespace(f"g{suffix}", namespaces["generic"])


def _concept_identity(parent: ET.Element, version: str, ns: dict[str, str], agency: str, scheme: str, scheme_version: str, concept: str) -> None:
    identity = _add(parent, ns["structure"], "ConceptIdentity")
    if version == "2.1":
        _plain(identity, "Ref", {
            "agencyID": agency, "maintainableParentID": scheme,
            "maintainableParentVersion": scheme_version, "id": concept,
            "package": "conceptscheme", "class": "Concept",
        })
    else:
        identity.text = _urn("conceptscheme", "Concept", agency, scheme, scheme_version, concept)


def _local_representation(parent: ET.Element, version: str, ns: dict[str, str], agency: str, codelist: str | None, codelist_version: str | None, data_type: str) -> None:
    representation = _add(parent, ns["structure"], "LocalRepresentation")
    if codelist:
        enumeration = _add(representation, ns["structure"], "Enumeration")
        if version == "2.1":
            _plain(enumeration, "Ref", {
                "agencyID": agency, "id": codelist, "version": codelist_version or "1.0",
                "package": "codelist", "class": "Codelist",
            })
        else:
            enumeration.text = _urn("codelist", "Codelist", agency, codelist, codelist_version or "1.0.0")
    else:
        _add(representation, ns["structure"], "TextFormat", {"textType": data_type or "String"})


def _structure_message(root: ET.Element, values: dict[str, dict[str, Any]], version: str, ns: dict[str, str], prepared: str) -> None:
    export = _add(root, BUNDLE, "StructureExport", {"format": f"SDMX-ML {version}"})
    message = _add(export, ns["message"], "Structure")
    header = _add(message, ns["message"], "Header")
    _add(header, ns["message"], "ID", text=f"FINAL_STRUCTURE_{version.replace('.', '_')}")
    _add(header, ns["message"], "Test", text="false")
    _add(header, ns["message"], "Prepared", text=prepared)
    _add(header, ns["message"], "Sender", {"id": "PIPELINE"})
    structures = _add(message, ns["message"], "Structures")

    codelists_container = _add(structures, ns["structure"], "Codelists")
    for codelist in values["CODELISTS"]["codelists"]:
        node = _add(codelists_container, ns["structure"], "Codelist", {
            "agencyID": codelist["agency_id"], "id": codelist["codelist_id"], "version": codelist["version"],
        })
        _name(node, ns["common"], codelist["name"])
        for code in codelist["codes"]:
            code_node = _add(node, ns["structure"], "Code", {"id": code["code"]})
            _name(code_node, ns["common"], code["name"])
            description = _add(code_node, ns["common"], "Description", text=code["definition"])
            description.set("{http://www.w3.org/XML/1998/namespace}lang", "en")

    concepts_container = _add(structures, ns["structure"], "Concepts")
    scheme_lookup: dict[str, tuple[str, str]] = {}
    concept_lookup: dict[str, tuple[str, str, str]] = {}
    for scheme in values["CONCEPT_SCHEME"]["concept_schemes"]:
        scheme_lookup[scheme["scheme_id"]] = (scheme["agency_id"], scheme["version"])
        node = _add(concepts_container, ns["structure"], "ConceptScheme", {
            "agencyID": scheme["agency_id"], "id": scheme["scheme_id"], "version": scheme["version"],
        })
        _name(node, ns["common"], scheme["name"])
        for concept in scheme["concepts"]:
            concept_lookup.setdefault(concept["concept_id"], (scheme["agency_id"], scheme["scheme_id"], scheme["version"]))
            concept_node = _add(node, ns["structure"], "Concept", {"id": concept["concept_id"]})
            _name(concept_node, ns["common"], concept["name"])
            description = _add(concept_node, ns["common"], "Description", text=concept["definition"])
            description.set("{http://www.w3.org/XML/1998/namespace}lang", "en")

    dsd_container = _add(structures, ns["structure"], "DataStructures")
    dsd_lookup: dict[str, tuple[str, str]] = {}
    for dsd in values["DSD_KEY_FAMILY"]["data_structures"]:
        dsd_lookup[dsd["dsd_id"]] = (dsd["agency_id"], dsd["version"])
        node = _add(dsd_container, ns["structure"], "DataStructure", {
            "agencyID": dsd["agency_id"], "id": dsd["dsd_id"], "version": dsd["version"],
        })
        _name(node, ns["common"], dsd["name"])
        components = _add(node, ns["structure"], "DataStructureComponents")
        dimensions = _add(components, ns["structure"], "DimensionList", {"id": "DimensionDescriptor"})
        attributes = _add(components, ns["structure"], "AttributeList", {"id": "AttributeDescriptor"})
        measures = _add(components, ns["structure"], "MeasureList", {"id": "MeasureDescriptor"})
        for component in dsd["components"]:
            role = component["role"]
            parent = dimensions if role in {"DIMENSION", "TIME"} else measures if role == "MEASURE" else attributes
            tag = "TimeDimension" if role == "TIME" else "Measure" if role == "MEASURE" and version == "3.0" else "PrimaryMeasure" if role == "MEASURE" else "Attribute" if role == "ATTRIBUTE" else "Dimension"
            attributes_map = {"id": component["concept_id"]}
            if component.get("position") is not None and role in {"DIMENSION", "TIME"}:
                attributes_map["position"] = component["position"]
            if role == "ATTRIBUTE":
                attributes_map["usage"] = component["usage_status"].lower()
            item = _add(parent, ns["structure"], tag, attributes_map)
            concept_agency, scheme_id, scheme_version = concept_lookup.get(
                component["concept_id"], (dsd["agency_id"], next(iter(scheme_lookup), "UNKNOWN_SCHEME"), "1.0")
            )
            _concept_identity(item, version, ns, concept_agency, scheme_id, scheme_version, component["concept_id"])
            _local_representation(
                item, version, ns, component.get("codelist_agency") or dsd["agency_id"],
                component.get("codelist_id"), component.get("codelist_version"), component.get("data_type", "String"),
            )
            if role == "ATTRIBUTE":
                relationship = _add(item, ns["structure"], "AttributeRelationship")
                _add(relationship, ns["structure"], (component.get("attachment_level") or "OBSERVATION").title())

    flows_container = _add(structures, ns["structure"], "Dataflows")
    for flow in values["DATAFLOW"]["dataflows"]:
        node = _add(flows_container, ns["structure"], "Dataflow", {
            "agencyID": flow["agency_id"], "id": flow["dataflow_id"], "version": flow["version"],
        })
        _name(node, ns["common"], flow["name"])
        structure = _add(node, ns["structure"], "Structure")
        if version == "2.1":
            _plain(structure, "Ref", {
                "agencyID": flow["dsd_agency_id"], "id": flow["dsd_id"], "version": flow["dsd_version"],
                "package": "datastructure", "class": "DataStructure",
            })
        else:
            structure.text = _urn("datastructure", "DataStructure", flow["dsd_agency_id"], flow["dsd_id"], flow["dsd_version"])

    metadata_container = _add(structures, ns["structure"], "MetadataStructures")
    for msd in values["METADATA_STRUCTURE_DEFINITION_MSD"]["metadata_structures"]:
        node = _add(metadata_container, ns["structure"], "MetadataStructure", {
            "agencyID": msd["agency_id"], "id": msd["msd_id"], "version": msd["version"],
        })
        _name(node, ns["common"], msd["name"])
        components = _add(node, ns["structure"], "MetadataStructureComponents")
        target = _add(components, ns["structure"], "MetadataTarget", {"id": "DATAFLOW_TARGET"})
        identifiable = _add(target, ns["structure"], "IdentifiableObjectTarget", {"id": "TARGET_DATAFLOW"})
        local_rep = _add(identifiable, ns["structure"], "LocalRepresentation")
        enumeration = _add(local_rep, ns["structure"], "Enumeration")
        if version == "2.1":
            _plain(enumeration, "Ref", {"package": "datastructure", "class": "Dataflow"})
        else:
            enumeration.text = "urn:sdmx:org.sdmx.infomodel.datastructure.Dataflow"
        report = _add(components, ns["structure"], "ReportStructure", {"id": f"{msd['msd_id']}_REPORT"})
        for concept in msd["concepts"]:
            item = _add(report, ns["structure"], "MetadataAttribute", {
                "id": concept["concept_id"], "minOccurs": "1" if concept["required"] else "0", "maxOccurs": "1",
            })
            concept_agency, scheme_id, scheme_version = concept_lookup.get(
                concept["concept_id"], (msd["agency_id"], next(iter(scheme_lookup), "UNKNOWN_SCHEME"), "1.0")
            )
            _concept_identity(item, version, ns, concept_agency, scheme_id, scheme_version, concept["concept_id"])
            _local_representation(item, version, ns, msd["agency_id"], None, None, concept["representation"])


def _metadata_message(root: ET.Element, values: dict[str, dict[str, Any]], version: str, ns: dict[str, str], prepared: str) -> None:
    export = _add(root, BUNDLE, "MetadataSetExport", {"format": f"SDMX-ML Generic Metadata {version}"})
    metadata_structures = {item["msd_id"]: item for item in values["METADATA_STRUCTURE_DEFINITION_MSD"]["metadata_structures"]}
    flows = {item["dataflow_id"]: item for item in values["DATAFLOW"]["dataflows"]}
    for metadata_set in values["METADATA_SET"]["metadata_sets"]:
        msd = metadata_structures.get(metadata_set["msd_id"], {})
        flow = flows.get(metadata_set["target_id"], {})
        message = _add(export, ns["message"], "GenericMetadata")
        header = _add(message, ns["message"], "Header")
        _add(header, ns["message"], "ID", text=metadata_set["metadata_set_id"])
        _add(header, ns["message"], "Test", text="false")
        _add(header, ns["message"], "Prepared", text=prepared)
        _add(header, ns["message"], "Sender", {"id": "PIPELINE"})
        if version == "3.0":
            structure = _add(header, ns["message"], "Structure", {"structureID": metadata_set["msd_id"]})
            _add(structure, ns["message"], "Structure", text=_urn(
                "metadatastructure", "MetadataStructure", msd.get("agency_id", "UNKNOWN_AGENCY"),
                metadata_set["msd_id"], msd.get("version", "1.0.0"),
            ))
        container = _add(message, ns["generic"], "MetadataSet")
        if version == "2.1":
            _add(container, ns["generic"], "MetadataStructureRef", text=metadata_set["msd_id"])
            _add(container, ns["generic"], "MetadataStructureAgencyRef", text=msd.get("agency_id", "UNKNOWN_AGENCY"))
            _add(container, ns["generic"], "ReportRef", text=f"{metadata_set['msd_id']}_REPORT")
            value_set = _add(container, ns["generic"], "AttributeValueSet")
            _add(value_set, ns["generic"], "TargetRef", text="DATAFLOW_TARGET")
            targets = _add(value_set, ns["generic"], "TargetValues")
            _add(targets, ns["generic"], "ComponentValue", {"object": "Dataflow"}, metadata_set["target_id"])
            values_parent = value_set
        else:
            report = _add(container, ns["generic"], "Report", {"structureID": f"{metadata_set['msd_id']}_REPORT"})
            target = _add(report, ns["generic"], "Target")
            target_text = _urn("datastructure", "Dataflow", flow.get("agency_id", "UNKNOWN_AGENCY"), metadata_set["target_id"], flow.get("version", "1.0.0"))
            _add(target, ns["generic"], "ReferenceValue", {"id": "DATAFLOW_TARGET"}, target_text)
            values_parent = report
        for item in metadata_set["values"]:
            attribute = _add(values_parent, ns["generic"], "ReportedAttribute", {"conceptID" if version == "2.1" else "id": item["concept_id"]})
            _add(attribute, ns["generic"], "Value", text=item["value"])


def _custom_artifacts(root: ET.Element, values: dict[str, dict[str, Any]]) -> None:
    for template in values["AI_FILLABLE_DATA_TEMPLATE"]["templates"]:
        node = _add(root, BUNDLE, "AIFillableDataTemplate", {"dsd": f"PIPELINE:{template['dsd_id']}(1.0)"})
        columns = _add(node, BUNDLE, "Columns")
        role_names = {"DIMENSION": "dimension", "TIME": "timeDimension", "MEASURE": "measure", "ATTRIBUTE": "attribute"}
        for column in template["columns"]:
            _add(columns, BUNDLE, "Column", {
                "id": column["column_id"], "role": role_names[column["role"]],
                "required": str(column["required"]).lower(), "codelist": column.get("codelist_id"),
            })
        observations = _add(node, BUNDLE, "Observations")
        for index, observation in enumerate(template["observations"], 1):
            row = _add(observations, BUNDLE, "Observation", {"row": index})
            for item in observation["values"]:
                _add(row, BUNDLE, "Value", {"concept": item["column_id"], "value": "" if item["value"] is None else item["value"]})

    codebook = values["CODEBOOK_AND_SOURCE_MAPPING"]
    node = _add(root, BUNDLE, "CodebookAndSourceMapping")
    definitions = _add(node, BUNDLE, "Fields")
    for field in codebook["fields"]:
        item = _add(definitions, BUNDLE, "FieldDefinition", {
            "id": field["field_id"], "role": field["role"].lower(), "required": str(field["required"]).lower(),
            "codelist": field.get("codelist_id"), "representation": field["representation"],
        })
        _add(item, BUNDLE, "Name", text=field["name"])
        _add(item, BUNDLE, "Definition", text=field["definition"])
    field_mappings = _add(node, BUNDLE, "FieldMappings")
    value_mappings = _add(node, BUNDLE, "ValueMappings")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for mapping in codebook["source_value_mappings"]:
        if mapping.get("target_code") is None:
            _add(field_mappings, BUNDLE, "Field", {
                "source": mapping["source_value"], "targetConcept": mapping["target_field"],
                "status": "accepted" if mapping["mapping_type"] == "EXACT" else "unresolved",
            })
        else:
            grouped.setdefault(mapping["target_field"], []).append(mapping)
    for field_id, mappings in grouped.items():
        concept = _add(value_mappings, BUNDLE, "Concept", {"id": field_id})
        for mapping in mappings:
            _add(concept, BUNDLE, "Map", {
                "source": mapping["source_value"], "target": mapping["target_code"],
                "status": "accepted" if mapping["mapping_type"] == "EXACT" else "unresolved",
            })
    unresolved = _add(node, BUNDLE, "Unresolved")
    for item in codebook["unresolved"]:
        _add(unresolved, BUNDLE, "Item", text=item)


def build_bundle(values: dict[str, dict[str, Any]], version: str, prepared: str) -> ET.ElementTree:
    if version not in {"2.1", "3.0"}:
        raise ValueError(f"Unsupported SDMX export version: {version}")
    ns = _namespaces(version)
    _register(version, ns)
    root = ET.Element(_q(BUNDLE, "SDMXCaseBundle"), {
        "case": "FINAL", "sdmxVersion": version, "title": "Final Consolidated SDMX Artifacts",
    })
    about = _add(root, BUNDLE, "About")
    _add(about, BUNDLE, "Purpose", text="Mechanically exported final pipeline artifacts.")
    index = _add(about, BUNDLE, "ArtifactIndex")
    for label in (
        "Concept Scheme", "Codelists", "DSD", "Dataflow", "Metadata Structure Definition (MSD)",
        "Metadata Set", "AI-Fillable Data Template", "Codebook and Source-to-SDMX Mapping",
    ):
        _add(index, BUNDLE, "Artifact", text=label)
    _structure_message(root, values, version, ns, prepared)
    _metadata_message(root, values, version, ns, prepared)
    _custom_artifacts(root, values)
    ET.indent(root, space="  ")
    return ET.ElementTree(root)


def _load_final_values(artifacts: list[ArtifactDefinition]) -> tuple[dict[str, dict[str, Any]], str, str]:
    values = {}
    hashes = []
    mtimes = []
    for artifact in artifacts:
        path = FINAL_ARTIFACT_ROOT / f"{artifact_folder_name(artifact.key)}.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing final artifact: {path.name}")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        envelope = final_envelope_model(artifact.key).model_validate_json(raw)
        values[artifact.key] = envelope.final_artifact.model_dump(mode="json")
        hashes.append(f"{artifact.key}:{digest}")
        mtimes.append(path.stat().st_mtime)
    input_hash = hashlib.sha256((EXPORTER_VERSION + "|" + "|".join(sorted(hashes))).encode()).hexdigest()
    prepared = datetime.fromtimestamp(max(mtimes), timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return values, input_hash, prepared


def _write_xml_atomic(tree: ET.ElementTree, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(path) + f".{os.getpid()}.tmp")
    tree.write(temporary, encoding="utf-8", xml_declaration=True)
    temporary.replace(path)


def run_final_xml_export(artifacts: list[ArtifactDefinition], control: ControlWorkbook) -> None:
    print("\nFinal SDMX XML export stage")
    if any(control.aggregate_get(artifact.key, "FINAL_STATUS") not in {"SUCCESS", "MODIFIED"} for artifact in artifacts):
        for version in ("2.1", "3.0"):
            control.xml_export_stage(version, "PENDING", "Final JSON artifacts are not all approved")
        print("  PENDING (final JSON artifacts are not all approved)")
        return
    try:
        values, input_hash, prepared = _load_final_values(artifacts)
    except Exception as error:
        for version in ("2.1", "3.0"):
            control.xml_export_stage(version, "FAILED", f"{type(error).__name__}: {error}")
        print(f"  FAILED ({type(error).__name__}: {error})")
        return
    for version in ("2.1", "3.0"):
        path = FINAL_SDMX_ROOT / f"final_sdmx_{version.replace('.', '_')}_structures.xml"
        try:
            current = (
                control.xml_export_get(version, "STATUS") in {"SUCCESS", "MODIFIED"}
                and control.xml_export_get(version, "INPUT_HASH") == input_hash
                and path.exists()
            )
            if current:
                ET.parse(path)
                print(f"  SDMX {version}: SKIPPED (current)")
                continue
            control.xml_export_stage(version, "RUNNING")
            _write_xml_atomic(build_bundle(values, version, prepared), path)
            ET.parse(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            control.xml_export_set(version, "INPUT_HASH", input_hash, save=False)
            control.xml_export_set(version, "XML_PATH", str(path.relative_to(ROOT)), save=False)
            control.xml_export_set(version, "XML_HASH", digest, save=False)
            control.xml_export_set(version, "XML_MTIME_NS", str(path.stat().st_mtime_ns), save=False)
            control.xml_export_stage(version, "SUCCESS")
            print(f"  SDMX {version}: SUCCESS -> {path.relative_to(ROOT)}")
        except Exception as error:
            control.xml_export_stage(version, "FAILED", f"{type(error).__name__}: {error}")
            print(f"  SDMX {version}: FAILED ({type(error).__name__}: {error})")
