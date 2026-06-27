#!/usr/bin/env python3
"""Generate the legacy simple XML schema used by the educational 2416-style flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


XSD_NS = "http://www.w3.org/2001/XMLSchema"


def indent(text: str, spaces: int = 2) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line else line for line in text.splitlines())


def enum_type(name: str, values: list[str]) -> str:
    lines = [f'<xs:simpleType name="{name}">', '  <xs:restriction base="xs:string">']
    lines.extend(f'    <xs:enumeration value="{value}"/>' for value in values)
    lines.extend(["  </xs:restriction>", "</xs:simpleType>"])
    return "\n".join(lines)


def render_xsd(spec: dict) -> str:
    namespace = spec["namespace"]
    enums = spec["enumerations"]
    enum_blocks = [
        enum_type("ModelClassType", enums["modelClass"]),
        enum_type("AbstractionLevelType", enums["abstractionLevel"]),
        enum_type("PowerDomainType", enums["powerDomain"]),
        enum_type("PowerStateType", enums["powerState"]),
        enum_type("ClockRefType", enums["clockRef"]),
        enum_type("ComponentType", enums["componentType"]),
        enum_type("ContributorType", enums["contributorType"]),
    ]

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="{XSD_NS}"
           targetNamespace="{namespace}"
           xmlns="{namespace}"
           elementFormDefault="qualified"
           attributeFormDefault="unqualified">
  <xs:annotation>
    <xs:documentation>{spec["description"]}</xs:documentation>
  </xs:annotation>

{indent(chr(10).join(enum_blocks), 2)}

  <xs:complexType name="NameValueParameterType">
    <xs:attribute name="name" type="xs:string" use="required"/>
    <xs:attribute name="value" type="xs:string" use="required"/>
    <xs:attribute name="unit" type="xs:string" use="optional"/>
  </xs:complexType>

  <xs:complexType name="MetadataType">
    <xs:sequence>
      <xs:element name="name" type="xs:string"/>
      <xs:element name="description" type="xs:string" minOccurs="0"/>
      <xs:element name="generator" type="xs:string" minOccurs="0"/>
      <xs:element name="source" type="xs:string" minOccurs="0"/>
      <xs:element name="provenance" type="xs:string" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="DesignType">
    <xs:sequence>
      <xs:element name="parameter" type="NameValueParameterType" minOccurs="0" maxOccurs="unbounded"/>
    </xs:sequence>
    <xs:attribute name="block" type="xs:string" use="required"/>
    <xs:attribute name="module" type="xs:string" use="required"/>
    <xs:attribute name="rtlPath" type="xs:string" use="required"/>
    <xs:attribute name="powerDomain" type="PowerDomainType" use="required"/>
    <xs:attribute name="clock" type="ClockRefType" use="required"/>
  </xs:complexType>

  <xs:complexType name="OperatingConditionsType">
    <xs:sequence>
      <xs:element name="process">
        <xs:complexType>
          <xs:attribute name="nodeNm" type="xs:decimal" use="required"/>
          <xs:attribute name="corner" type="xs:string" use="required"/>
        </xs:complexType>
      </xs:element>
      <xs:element name="temperature">
        <xs:complexType>
          <xs:attribute name="valueC" type="xs:decimal" use="required"/>
        </xs:complexType>
      </xs:element>
      <xs:element name="supply" minOccurs="1" maxOccurs="unbounded">
        <xs:complexType>
          <xs:attribute name="name" type="xs:string" use="required"/>
          <xs:attribute name="voltageV" type="xs:decimal" use="required"/>
        </xs:complexType>
      </xs:element>
      <xs:element name="clock" minOccurs="0" maxOccurs="unbounded">
        <xs:complexType>
          <xs:attribute name="name" type="ClockRefType" use="required"/>
          <xs:attribute name="frequencyMHz" type="xs:decimal" use="required"/>
        </xs:complexType>
      </xs:element>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="PowerStatesType">
    <xs:sequence>
      <xs:element name="state" minOccurs="1" maxOccurs="unbounded">
        <xs:complexType>
          <xs:attribute name="name" type="PowerStateType" use="required"/>
          <xs:attribute name="supply" type="xs:string" use="required"/>
          <xs:attribute name="clock" type="xs:string" use="required"/>
          <xs:attribute name="isolation" type="xs:boolean" use="required"/>
          <xs:attribute name="retention" type="xs:boolean" use="required"/>
          <xs:attribute name="leakageMw" type="xs:decimal" use="required"/>
        </xs:complexType>
      </xs:element>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="ActivityParametersType">
    <xs:sequence>
      <xs:element name="event" minOccurs="0" maxOccurs="unbounded">
        <xs:complexType>
          <xs:attribute name="name" type="xs:string" use="required"/>
          <xs:attribute name="source" type="xs:string" use="required"/>
          <xs:attribute name="description" type="xs:string" use="optional"/>
        </xs:complexType>
      </xs:element>
      <xs:element name="signalActivity" minOccurs="0" maxOccurs="unbounded">
        <xs:complexType>
          <xs:attribute name="name" type="xs:string" use="required"/>
          <xs:attribute name="source" type="xs:string" use="required"/>
        </xs:complexType>
      </xs:element>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="PowerComponentsType">
    <xs:sequence>
      <xs:element name="component" minOccurs="1" maxOccurs="unbounded">
        <xs:complexType>
          <xs:attribute name="type" type="ComponentType" use="required"/>
          <xs:attribute name="name" type="xs:string" use="required"/>
          <xs:attribute name="ref" type="xs:string" use="optional"/>
          <xs:attribute name="value" type="xs:decimal" use="required"/>
          <xs:attribute name="unit" type="xs:string" use="required"/>
          <xs:attribute name="voltageScaled" type="xs:boolean" use="optional"/>
        </xs:complexType>
      </xs:element>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="PowerContributorsType">
    <xs:sequence>
      <xs:element name="contributor" minOccurs="1" maxOccurs="unbounded">
        <xs:complexType>
          <xs:attribute name="name" type="xs:string" use="required"/>
          <xs:attribute name="type" type="ContributorType" use="required"/>
          <xs:attribute name="domain" type="PowerDomainType" use="required"/>
          <xs:attribute name="driver" type="xs:string" use="required"/>
          <xs:attribute name="componentRef" type="xs:string" use="required"/>
          <xs:attribute name="pvtDependency" type="xs:string" use="required"/>
          <xs:attribute name="voltageDependency" type="xs:string" use="required"/>
          <xs:attribute name="frequencyDependency" type="xs:string" use="required"/>
          <xs:attribute name="stateDependency" type="xs:string" use="required"/>
          <xs:attribute name="workloadDependency" type="xs:string" use="required"/>
        </xs:complexType>
      </xs:element>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="ScalingType">
    <xs:sequence>
      <xs:element name="voltage">
        <xs:complexType>
          <xs:attribute name="referenceV" type="xs:decimal" use="required"/>
          <xs:attribute name="dynamicExponent" type="xs:decimal" use="required"/>
          <xs:attribute name="leakageExponent" type="xs:decimal" use="required"/>
        </xs:complexType>
      </xs:element>
      <xs:element name="temperature">
        <xs:complexType>
          <xs:attribute name="referenceC" type="xs:decimal" use="required"/>
          <xs:attribute name="leakagePer10cFactor" type="xs:decimal" use="required"/>
        </xs:complexType>
      </xs:element>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="ValidityType">
    <xs:sequence>
      <xs:element name="voltageRange">
        <xs:complexType>
          <xs:attribute name="minV" type="xs:decimal" use="required"/>
          <xs:attribute name="maxV" type="xs:decimal" use="required"/>
        </xs:complexType>
      </xs:element>
      <xs:element name="temperatureRange">
        <xs:complexType>
          <xs:attribute name="minC" type="xs:decimal" use="required"/>
          <xs:attribute name="maxC" type="xs:decimal" use="required"/>
        </xs:complexType>
      </xs:element>
    </xs:sequence>
  </xs:complexType>

  <xs:element name="powerModel">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="metadata" type="MetadataType"/>
        <xs:element name="design" type="DesignType"/>
        <xs:element name="operatingConditions" type="OperatingConditionsType"/>
        <xs:element name="powerStates" type="PowerStatesType"/>
        <xs:element name="activityParameters" type="ActivityParametersType"/>
        <xs:element name="powerComponents" type="PowerComponentsType"/>
        <xs:element name="powerContributors" type="PowerContributorsType"/>
        <xs:element name="scaling" type="ScalingType"/>
        <xs:element name="validity" type="ValidityType"/>
      </xs:sequence>
      <xs:attribute name="standard" type="xs:string" use="required"/>
      <xs:attribute name="schemaVersion" type="xs:string" use="required"/>
      <xs:attribute name="modelClass" type="ModelClassType" use="required"/>
      <xs:attribute name="abstractionLevel" type="AbstractionLevelType" use="required"/>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=Path("legacy/simple_2416_schema/schema_profile.json"))
    parser.add_argument("--out", type=Path, default=Path("legacy/simple_2416_schema/generated_schema.xsd"))
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_xsd(spec), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
