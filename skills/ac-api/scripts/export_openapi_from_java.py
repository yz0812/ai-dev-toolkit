#!/usr/bin/env python3
import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import generate_openapi

BUSINESS_CENTER_PATTERN = re.compile(r"@BusinessCenterDescriptor\b")
PACKAGE_PATTERN = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
IMPORT_PATTERN = re.compile(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", re.MULTILINE)
TYPE_PATTERN = re.compile(r"\b(interface|class|enum|record)\s+([A-Za-z_][\w$]*)\b")
BUSINESS_DESCRIPTOR_PREFIX = "@BusinessDescriptor"
METHOD_MODIFIERS = {
    "public",
    "protected",
    "private",
    "abstract",
    "default",
    "static",
    "final",
    "synchronized",
    "native",
    "strictfp",
}
FIELD_MODIFIERS = {"public", "protected", "private", "final", "transient", "volatile"}
PRIMITIVE_EXAMPLES = {
    "boolean": False,
    "Boolean": False,
    "byte": 0,
    "Byte": 0,
    "short": 0,
    "Short": 0,
    "int": 0,
    "Integer": 0,
    "long": 0,
    "Long": 0,
    "float": 0.0,
    "Float": 0.0,
    "double": 0.0,
    "Double": 0.0,
    "BigDecimal": 0.0,
    "BigInteger": 0,
    "char": "",
    "Character": "",
    "String": "",
    "CharSequence": "",
    "LocalDate": "2026-04-21",
    "LocalDateTime": "2026-04-21T00:00:00",
    "OffsetDateTime": "2026-04-21T00:00:00+08:00",
    "Instant": "2026-04-21T00:00:00Z",
    "Date": "2026-04-21T00:00:00Z",
}
COLLECTION_TYPES = {"List", "Set", "Collection", "Iterable", "ArrayList", "LinkedList", "HashSet"}
MAP_TYPES = {"Map", "HashMap", "LinkedHashMap", "TreeMap"}
ANNOTATION_DESCRIPTION_KEYS = ("description", "value", "notes", "name")
DIRECT_DESCRIPTION_MAP = {
    "id": "ID",
    "ids": "ID列表",
    "projectid": "项目ID",
    "userid": "用户ID",
    "tenantid": "租户ID",
    "orgid": "组织ID",
    "stationid": "充电站ID",
    "deviceid": "设备ID",
    "pageno": "页码",
    "pagesize": "每页条数",
    "page": "页码",
    "sortno": "排序号",
    "sortnum": "排序号",
    "sortorder": "排序值",
    "total": "总数",
    "count": "数量",
    "list": "列表",
    "items": "列表项",
    "rows": "行数据",
    "records": "记录列表",
    "name": "名称",
    "status": "状态",
    "type": "类型",
    "code": "编码",
    "message": "消息",
    "success": "是否成功",
    "content": "内容",
    "description": "描述",
    "remark": "备注",
    "title": "标题",
    "keyword": "关键字",
    "data": "数据",
    "projectinfo": "项目信息",
    "projectdata": "项目数据",
    "constructioncontent": "建设内容",
    "starttime": "开始时间",
    "endtime": "结束时间",
    "createtime": "创建时间",
    "updatetime": "更新时间",
}
TOKEN_DESCRIPTION_MAP = {
    "project": "项目",
    "user": "用户",
    "tenant": "租户",
    "org": "组织",
    "station": "充电站",
    "device": "设备",
    "page": "页",
    "no": "码",
    "size": "大小",
    "count": "数量",
    "total": "总数",
    "name": "名称",
    "status": "状态",
    "type": "类型",
    "code": "编码",
    "message": "消息",
    "success": "成功标记",
    "data": "数据",
    "info": "信息",
    "detail": "详情",
    "content": "内容",
    "construction": "建设",
    "list": "列表",
    "record": "记录",
    "keyword": "关键字",
    "start": "开始",
    "end": "结束",
    "time": "时间",
    "date": "日期",
}
MAX_SCHEMA_DEPTH = 4


@dataclass
class ExtractedMethod:
    metadata: dict
    method_line: int
    source_file: Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract SKSPIOT business service metadata from Java and generate OpenAPI 3.1 JSON files."
    )
    parser.add_argument("--source", required=True, help="Java file or directory")
    parser.add_argument("--method", help="Filter by Java method name")
    parser.add_argument("--business-method", help="Filter by @BusinessDescriptor.name")
    parser.add_argument("--output-root", default=generate_openapi.DEFAULT_OUTPUT_ROOT, help="Output root directory")
    parser.add_argument("--server-url", default=generate_openapi.DEFAULT_SERVER_URL, help="Server URL")
    parser.add_argument("--path", dest="api_path", default=generate_openapi.DEFAULT_API_PATH, help="HTTP path")
    parser.add_argument("--timestamp", help="Timestamp override, format: YYYY-MM-DDTHH:MM or YYYY-MM-DD HH:MM")
    parser.add_argument(
        "--save-metadata",
        action="store_true",
        help="Save extracted metadata JSON next to the generated OpenAPI file",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Only print extracted metadata JSON; do not generate OpenAPI files",
    )
    return parser.parse_args()


def normalize_space(value: str):
    return re.sub(r"\s+", " ", value).strip()


def normalize_name_key(value: str):
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def strip_method_modifiers(signature: str):
    cleaned = signature.strip()
    while True:
        matched = False
        for modifier in METHOD_MODIFIERS:
            prefix = modifier + " "
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :].lstrip()
                matched = True
                break
        if not matched:
            break
    cleaned = re.sub(r"^<[^>]+>\s+", "", cleaned)
    return cleaned


def strip_param_annotations(text: str):
    result = []
    index = 0
    while index < len(text):
        char = text[index]
        if char != "@":
            result.append(char)
            index += 1
            continue

        index += 1
        while index < len(text) and (text[index].isalnum() or text[index] in "._$"):
            index += 1
        while index < len(text) and text[index].isspace():
            index += 1
        if index < len(text) and text[index] == "(":
            depth = 1
            index += 1
            while index < len(text) and depth > 0:
                if text[index] == "(":
                    depth += 1
                elif text[index] == ")":
                    depth -= 1
                index += 1
        while index < len(text) and text[index].isspace():
            index += 1
    return "".join(result)


def split_top_level(text: str, delimiter: str = ","):
    parts = []
    current = []
    angle_depth = 0
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    for char in text:
        if char == "<":
            angle_depth += 1
        elif char == ">" and angle_depth > 0:
            angle_depth -= 1
        elif char == "(":
            paren_depth += 1
        elif char == ")" and paren_depth > 0:
            paren_depth -= 1
        elif char == "[":
            bracket_depth += 1
        elif char == "]" and bracket_depth > 0:
            bracket_depth -= 1
        elif char == "{":
            brace_depth += 1
        elif char == "}" and brace_depth > 0:
            brace_depth -= 1

        if (
            char == delimiter
            and angle_depth == 0
            and paren_depth == 0
            and bracket_depth == 0
            and brace_depth == 0
        ):
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(char)

    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def decode_java_string_literal(value: str):
    return json.loads(f'"{value}"')


def parse_annotation_arguments(annotation_text: str):
    match = re.search(r"\((.*)\)", annotation_text, re.DOTALL)
    if not match:
        return {}
    raw = match.group(1)
    values = {}
    for key, value in re.findall(r"(\w+)\s*=\s*\"((?:\\.|[^\"])*)\"", raw):
        values[key] = decode_java_string_literal(value)
    if values:
        return values
    direct = re.fullmatch(r"\s*\"((?:\\.|[^\"])*)\"\s*", raw)
    if direct:
        values["value"] = decode_java_string_literal(direct.group(1))
    return values


def simplify_java_type(java_type: str):
    cleaned = normalize_space(java_type)
    cleaned = cleaned.replace("...", "[]")
    cleaned = re.sub(r"<.*>", "", cleaned)
    return cleaned.rsplit(".", 1)[-1]


def extract_base_type(java_type: str):
    return simplify_java_type(java_type).replace("[]", "")


def extract_generic_arguments(java_type: str):
    match = re.search(r"<(.*)>", normalize_space(java_type))
    if not match:
        return []
    return split_top_level(match.group(1))


def infer_java_example(java_type: str):
    base_type = extract_base_type(java_type)
    if java_type.endswith("[]") or java_type.endswith("...") or base_type in COLLECTION_TYPES:
        return []
    if base_type in MAP_TYPES:
        return {}
    if base_type in PRIMITIVE_EXAMPLES:
        return PRIMITIVE_EXAMPLES[base_type]
    if base_type == "Void" or base_type == "void":
        return None
    return {}


def parse_package_name(content: str):
    match = PACKAGE_PATTERN.search(content)
    return match.group(1) if match else ""


def parse_imports(content: str):
    imports = {"named": {}, "wildcards": []}
    for fqn in IMPORT_PATTERN.findall(content):
        if fqn.endswith(".*"):
            imports["wildcards"].append(fqn[:-2])
            continue
        imports["named"][fqn.rsplit(".", 1)[-1]] = fqn
    return imports


def collect_index_files(source: Path):
    if source.is_dir():
        return sorted(path for path in source.rglob("*.java") if path.is_file())
    for parent in [source.parent, *source.parents]:
        if parent.name == "java":
            return sorted(path for path in parent.rglob("*.java") if path.is_file())
    return [source]


def find_java_root(path: Path):
    for parent in [path.parent, *path.parents]:
        if parent.name == "java":
            return parent
    return None


def dedupe_paths(paths: list[Path]):
    unique = []
    seen = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def collect_search_roots(source: Path, java_files: list[Path] | None = None):
    if source.is_dir():
        roots = []
        if source.name == "java":
            roots.append(source)
        for candidate in (source / "src/main/java", source / "src/test/java"):
            if candidate.is_dir():
                roots.append(candidate)
        for java_file in java_files or []:
            root = find_java_root(java_file)
            if root:
                roots.append(root)
        roots = dedupe_paths(roots)
        return roots or [source]
    java_root = find_java_root(source)
    if java_root:
        return [java_root]
    return [source.parent]


def index_java_file(path: Path, index: dict):
    if path in index["contents"] or not path.is_file():
        return
    content = path.read_text(encoding="utf-8")
    package_name = parse_package_name(content)
    index["contents"][path] = content
    index["packages"][path] = package_name
    index["imports"][path] = parse_imports(content)
    for match in TYPE_PATTERN.finditer(content):
        type_name = match.group(2)
        index["simple"].setdefault(type_name, []).append(path)
        if package_name:
            index["fqn"][f"{package_name}.{type_name}"] = path


def build_type_index(java_files: list[Path], search_roots: list[Path]):
    index = {
        "contents": {},
        "packages": {},
        "imports": {},
        "simple": {},
        "fqn": {},
        "search_roots": search_roots,
        "simple_lookup_cache": {},
        "warnings": [],
    }
    for path in java_files:
        index_java_file(path, index)
    return index


def add_schema_warning(source_index: dict, message: str):
    warnings = source_index.setdefault("warnings", [])
    if message not in warnings:
        warnings.append(message)


def try_index_fqn(fqn: str, source_index: dict):
    if fqn in source_index["fqn"]:
        return source_index["fqn"][fqn]
    package_name, _, type_name = fqn.rpartition(".")
    if not package_name or not type_name:
        return None
    relative_path = Path(*package_name.split(".")) / f"{type_name}.java"
    for root in source_index.get("search_roots", []):
        candidate = root / relative_path
        if candidate.is_file():
            index_java_file(candidate, source_index)
            if fqn in source_index["fqn"]:
                return source_index["fqn"][fqn]
    return None


def ensure_simple_type_indexed(base_type: str, source_index: dict):
    cache = source_index.setdefault("simple_lookup_cache", {})
    if base_type in cache:
        for candidate in cache[base_type]:
            index_java_file(candidate, source_index)
        return cache[base_type]

    matches = []
    for root in source_index.get("search_roots", []):
        for candidate in root.rglob(f"{base_type}.java"):
            if candidate.is_file():
                matches.append(candidate)
    matches = dedupe_paths(matches)
    cache[base_type] = matches
    for candidate in matches:
        index_java_file(candidate, source_index)
    return matches


def score_type_candidate(candidate: Path, current_file: Path, imports: dict, package_name: str):
    score = 0
    named_imports = imports.get("named", {}) if isinstance(imports, dict) else {}
    wildcard_imports = imports.get("wildcards", []) if isinstance(imports, dict) else []
    candidate_package = package_name
    if candidate.parent == current_file.parent:
        score += 4
    for imported_fqn in named_imports.values():
        imported_package, _, _ = imported_fqn.rpartition(".")
        if imported_package and candidate.as_posix().endswith(imported_package.replace(".", "/") + f"/{candidate.name}"):
            score += 3
    for wildcard_package in wildcard_imports:
        if candidate.as_posix().endswith(wildcard_package.replace(".", "/") + f"/{candidate.name}"):
            score += 2
    if package_name and candidate.as_posix().endswith(package_name.replace(".", "/") + f"/{candidate.name}"):
        score += 2
    return score


def resolve_type_file(java_type: str, current_file: Path, source_index: dict):
    base_type = extract_base_type(java_type)
    if (
        not base_type
        or base_type in PRIMITIVE_EXAMPLES
        or base_type in COLLECTION_TYPES
        or base_type in MAP_TYPES
        or base_type in {"Object", "Void", "void"}
    ):
        return None

    index_java_file(current_file, source_index)
    normalized = normalize_space(java_type).replace("...", "[]")
    raw_type = normalized.split("<", 1)[0].strip().replace("[]", "")
    if "." in raw_type:
        resolved = try_index_fqn(raw_type, source_index)
        if resolved:
            return resolved

    imports = source_index["imports"].get(current_file, {})
    named_imports = imports.get("named", {}) if isinstance(imports, dict) else {}
    wildcard_imports = imports.get("wildcards", []) if isinstance(imports, dict) else []

    imported = named_imports.get(base_type)
    if imported:
        resolved = try_index_fqn(imported, source_index)
        if resolved:
            return resolved

    package_name = source_index["packages"].get(current_file) or ""
    if package_name:
        same_package = f"{package_name}.{base_type}"
        resolved = try_index_fqn(same_package, source_index)
        if resolved:
            return resolved

    for wildcard_package in wildcard_imports:
        resolved = try_index_fqn(f"{wildcard_package}.{base_type}", source_index)
        if resolved:
            return resolved

    candidates = ensure_simple_type_indexed(base_type, source_index)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    scored = sorted(
        ((score_type_candidate(candidate, current_file, imports, package_name), candidate) for candidate in candidates),
        key=lambda item: item[0],
        reverse=True,
    )
    top_score = scored[0][0]
    top_candidates = [candidate for score, candidate in scored if score == top_score]
    if top_score > 0 and len(top_candidates) == 1:
        return top_candidates[0]

    add_schema_warning(
        source_index,
        f"Type resolution is ambiguous for {base_type} referenced from {display_path(current_file)}; candidates: "
        + ", ".join(display_path(candidate) for candidate in candidates),
    )
    return None


def clean_comment_text(comment_lines: list[str]):
    cleaned = []
    for line in comment_lines:
        text = line.strip()
        text = re.sub(r"^/\*\*?", "", text)
        text = re.sub(r"\*/$", "", text)
        text = re.sub(r"^\*", "", text)
        text = re.sub(r"^//", "", text)
        text = text.strip()
        if text:
            cleaned.append(text)
    text = normalize_space(" ".join(cleaned))
    if not text:
        return None
    return {
        "text": text,
        "source": "comment",
    }


def extract_annotation_description(annotation_texts: list[str]):
    for annotation in annotation_texts:
        if not annotation.startswith("@Schema") and not annotation.startswith("@ApiModelProperty"):
            continue
        values = parse_annotation_arguments(annotation)
        for key in ANNOTATION_DESCRIPTION_KEYS:
            value = normalize_space(str(values.get(key, "")))
            if value:
                return {
                    "text": value,
                    "source": "annotation",
                }
    return None


def tokenize_identifier(name: str):
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name or "")
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    value = re.sub(r"[_\-\s]+", " ", value)
    return [token.lower() for token in value.split() if token]


def guess_chinese_description(name: str, java_type: str = "", context: str = "field"):
    key = normalize_name_key(name)
    if key in DIRECT_DESCRIPTION_MAP:
        base = DIRECT_DESCRIPTION_MAP[key]
    else:
        text_key = normalize_name_key(f"{name} {extract_base_type(java_type)}")
        if context == "parameter":
            if any(token in text_key for token in ["query", "search", "filter", "condition"]):
                return "查询条件"
            if "page" in text_key:
                return "分页参数"
            if any(token in text_key for token in ["request", "req", "param", "body"]):
                return "请求参数"
        translated = "".join(TOKEN_DESCRIPTION_MAP.get(token, "") for token in tokenize_identifier(name or extract_base_type(java_type)))
        base = translated

    if base:
        if context == "parameter" and base not in {"ID", "页码", "每页条数", "查询条件", "分页参数", "请求参数"}:
            if not base.endswith("参数"):
                return f"{base}参数"
        return base

    base_type = extract_base_type(java_type)
    if context == "parameter":
        if re.search(r"(VO|DTO|Req|Request|Query|Param|Form)$", base_type):
            stem = re.sub(r"(VO|DTO|Req|Request|Query|Param|Form)$", "", base_type)
            translated = "".join(TOKEN_DESCRIPTION_MAP.get(token, "") for token in tokenize_identifier(stem))
            if translated:
                return f"{translated}参数"
        return f"{name or '请求'}参数"
    return f"{name or base_type or '字段'}字段"


def build_primitive_schema(java_type: str):
    base_type = extract_base_type(java_type)
    if base_type in {"boolean", "Boolean"}:
        return {"type": "boolean"}
    if base_type in {"byte", "Byte", "short", "Short", "int", "Integer", "long", "Long", "BigInteger"}:
        return {"type": "integer"}
    if base_type in {"float", "Float", "double", "Double", "BigDecimal"}:
        return {"type": "number"}
    if base_type in {"char", "Character", "String", "CharSequence"}:
        return {"type": "string"}
    if base_type == "LocalDate":
        return {"type": "string", "format": "date"}
    if base_type in {"LocalDateTime", "OffsetDateTime", "Instant", "Date"}:
        return {"type": "string", "format": "date-time"}
    if base_type == "Object":
        return {"type": "object", "additionalProperties": True}
    if base_type in {"Void", "void"}:
        return {"type": "object", "additionalProperties": False}
    return None


def collect_statement(lines: list[str], start_index: int):
    parts = []
    index = start_index
    while index < len(lines):
        chunk = lines[index].strip()
        if not chunk:
            index += 1
            continue
        parts.append(chunk)
        if ";" in chunk or "{" in chunk:
            break
        index += 1
    return " ".join(parts), index


def find_type_body(content: str, target_type: str):
    match = re.search(rf"\b(class|interface|enum|record)\s+{re.escape(target_type)}\b", content)
    if not match:
        return ""
    start = content.find("{", match.end())
    if start == -1:
        return ""
    depth = 1
    index = start + 1
    while index < len(content) and depth > 0:
        char = content[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    return content[start + 1 : index - 1]


def parse_field_declaration(statement: str):
    if "(" in statement:
        return None
    if re.search(r"\bstatic\b", statement):
        return None
    cleaned = statement.split("=", 1)[0].strip().rstrip(";")
    for modifier in FIELD_MODIFIERS:
        cleaned = re.sub(rf"\b{modifier}\b", "", cleaned)
    cleaned = normalize_space(cleaned)
    if not cleaned or "," in cleaned:
        return None
    pieces = cleaned.split()
    if len(pieces) < 2:
        return None
    name = pieces[-1]
    java_type = " ".join(pieces[:-1])
    if name.endswith("[]"):
        name = name[:-2]
        java_type = f"{java_type}[]"
    if name == "serialVersionUID":
        return None
    return {"name": name, "type": java_type}


def build_field_description(annotation_texts: list[str], comment_lines: list[str], field_name: str, field_type: str):
    annotation_description = extract_annotation_description(annotation_texts)
    if annotation_description:
        return annotation_description
    comment_description = clean_comment_text(comment_lines)
    if comment_description:
        return comment_description
    return {
        "text": "",
        "source": "missing",
        "fallback": guess_chinese_description(field_name, field_type),
    }


def extract_fields_from_type(source_file: Path, target_type: str, source_index: dict):
    content = source_index["contents"].get(source_file, "")
    body = find_type_body(content, target_type)
    if not body:
        return []

    lines = body.splitlines()
    fields = []
    pending_comments: list[str] = []
    pending_annotations: list[str] = []
    depth = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if depth == 0:
            if not stripped:
                index += 1
                continue
            if stripped.startswith("/**") or stripped.startswith("/*"):
                comment_lines = [stripped]
                while "*/" not in comment_lines[-1] and index + 1 < len(lines):
                    index += 1
                    comment_lines.append(lines[index].strip())
                pending_comments = comment_lines
                index += 1
                continue
            if stripped.startswith("//"):
                if pending_comments and all(item.strip().startswith("//") for item in pending_comments):
                    pending_comments.append(stripped)
                else:
                    pending_comments = [stripped]
                index += 1
                continue
            if stripped.startswith("@"):
                annotation_text, annotation_end = collect_annotation(lines, index)
                pending_annotations.append(annotation_text)
                index = annotation_end + 1
                continue
            if re.search(r"\b(class|interface|enum|record)\s+[A-Za-z_][\w$]*\b", stripped):
                depth += line.count("{") - line.count("}")
                pending_comments = []
                pending_annotations = []
                index += 1
                continue

            statement, statement_end = collect_statement(lines, index)
            if statement.endswith(";") and "(" not in statement:
                field = parse_field_declaration(statement)
                if field:
                    description_meta = build_field_description(
                        pending_annotations,
                        pending_comments,
                        field["name"],
                        field["type"],
                    )
                    if description_meta.get("source") == "missing":
                        add_schema_warning(
                            source_index,
                            f"Missing field description evidence for {target_type}.{field['name']} in {display_path(source_file)}",
                        )
                    fields.append(
                        {
                            "name": field["name"],
                            "type": field["type"],
                            "description": description_meta.get("text", ""),
                            "descriptionSource": description_meta.get("source", "missing"),
                            "descriptionFallback": description_meta.get("fallback", ""),
                        }
                    )
                pending_comments = []
                pending_annotations = []
                index = statement_end + 1
                continue

            pending_comments = []
            pending_annotations = []

        depth += line.count("{") - line.count("}")
        if depth < 0:
            depth = 0
        index += 1
    return fields


def build_java_schema(
    java_type: str,
    current_file: Path,
    source_index: dict,
    description: str | None = None,
    description_source: str | None = None,
    seen_types: set[str] | None = None,
    depth: int = 0,
):
    seen_types = seen_types or set()
    primitive_schema = build_primitive_schema(java_type)
    if primitive_schema is not None:
        schema = primitive_schema
    else:
        base_type = extract_base_type(java_type)
        generic_arguments = extract_generic_arguments(java_type)
        if java_type.endswith("[]") or java_type.endswith("...") or base_type in COLLECTION_TYPES:
            item_type = generic_arguments[0] if generic_arguments else "Object"
            schema = {
                "type": "array",
                "items": build_java_schema(item_type, current_file, source_index, seen_types=seen_types, depth=depth + 1),
            }
        elif base_type in MAP_TYPES:
            value_type = generic_arguments[1] if len(generic_arguments) > 1 else "Object"
            schema = {
                "type": "object",
                "additionalProperties": build_java_schema(
                    value_type, current_file, source_index, seen_types=seen_types, depth=depth + 1
                ),
            }
        elif depth >= MAX_SCHEMA_DEPTH or base_type in seen_types:
            add_schema_warning(
                source_index,
                f"Schema depth fallback applied to {base_type} referenced from {display_path(current_file)}",
            )
            schema = {"type": "object", "additionalProperties": True}
        else:
            source_file = resolve_type_file(java_type, current_file, source_index)
            if not source_file:
                add_schema_warning(
                    source_index,
                    f"Unable to resolve Java type {base_type} referenced from {display_path(current_file)}",
                )
                schema = {"type": "object", "additionalProperties": True}
            else:
                fields = extract_fields_from_type(source_file, base_type, source_index)
                if not fields:
                    add_schema_warning(
                        source_index,
                        f"No fields extracted from {base_type} in {display_path(source_file)}",
                    )
                    schema = {"type": "object", "additionalProperties": True}
                else:
                    properties = {}
                    required = []
                    next_seen = set(seen_types)
                    next_seen.add(base_type)
                    for field in fields:
                        child_schema = build_java_schema(
                            field["type"],
                            source_file,
                            source_index,
                            description=field["description"],
                            description_source=field.get("descriptionSource"),
                            seen_types=next_seen,
                            depth=depth + 1,
                        )
                        if field.get("descriptionSource") in {"annotation", "comment"} and field.get("description"):
                            child_schema["description"] = field["description"]
                        properties[field["name"]] = child_schema
                        required.append(field["name"])
                    schema = {
                        "type": "object",
                        "properties": properties,
                        "additionalProperties": False,
                    }
                    if required:
                        schema["required"] = required
    if description and description_source != "missing" and "description" not in schema:
        schema["description"] = description
    return schema


def enrich_parameters(parameters: list[dict], java_file: Path, source_index: dict):
    enriched = []
    for parameter in parameters:
        item = dict(parameter)
        item["description"] = guess_chinese_description(item["name"], item["type"], context="parameter")
        item["schema"] = build_java_schema(
            item["type"],
            java_file,
            source_index,
            description=item["description"],
            description_source="parameter",
        )
        enriched.append(item)
    return enriched


def parse_parameters(parameters_text: str):
    parameters_text = parameters_text.strip()
    if not parameters_text:
        return []

    parameters = []
    for raw_param in split_top_level(parameters_text):
        cleaned = strip_param_annotations(raw_param)
        cleaned = re.sub(r"\bfinal\s+", "", cleaned)
        cleaned = normalize_space(cleaned)
        if not cleaned:
            continue
        pieces = cleaned.split()
        if len(pieces) < 2:
            continue
        name = pieces[-1]
        java_type = " ".join(pieces[:-1])
        parameters.append(
            {
                "name": name,
                "type": java_type,
                "example": infer_java_example(java_type),
            }
        )
    return parameters


def parse_method_signature(signature_text: str):
    signature = normalize_space(signature_text)
    signature = re.sub(r"\s*throws\s+[^;{]+(?=[;{])", "", signature)
    signature = strip_method_modifiers(signature)
    match = re.match(
        r"(?P<return_type>.+?)\s+(?P<method_name>[A-Za-z_][\w$]*)\s*\((?P<params>.*)\)\s*[;{]?$",
        signature,
    )
    if not match:
        raise ValueError(f"Unsupported method signature: {signature_text}")
    return {
        "returnType": match.group("return_type").strip(),
        "methodName": match.group("method_name").strip(),
        "parameters": parse_parameters(match.group("params")),
    }


def collect_annotation(lines: list[str], start_index: int):
    parts = [lines[start_index].strip()]
    depth = parts[0].count("(") - parts[0].count(")")
    index = start_index
    while depth > 0 and index + 1 < len(lines):
        index += 1
        chunk = lines[index].strip()
        parts.append(chunk)
        depth += chunk.count("(") - chunk.count(")")
    return " ".join(parts), index


def collect_signature(lines: list[str], start_index: int):
    parts = []
    depth = 0
    index = start_index
    started = False
    while index < len(lines):
        chunk = lines[index].strip()
        if not chunk:
            index += 1
            continue
        if chunk.startswith("@") and not started:
            index += 1
            continue
        started = True
        parts.append(chunk)
        depth += chunk.count("(") - chunk.count(")")
        if depth <= 0 and (chunk.endswith(";") or chunk.endswith("{") or ";" in chunk or "{" in chunk):
            break
        index += 1
    return " ".join(parts), index


def display_path(path: Path):
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def enrich_method_metadata(item: ExtractedMethod, source_index: dict):
    metadata = item.metadata
    warnings_before = len(source_index.get("warnings", []))
    parameters = enrich_parameters(metadata.get("parameters") or [], item.source_file, source_index)
    response_schema = build_java_schema(
        metadata["returnType"],
        item.source_file,
        source_index,
        description=metadata.get("returnDesc"),
        description_source="returnDesc",
    )
    response_example = infer_java_example(metadata["returnType"])
    if response_example in (None, {}, []):
        response_example = generate_openapi.build_example_from_schema(response_schema, "data")

    metadata["parameters"] = parameters
    metadata["responseSchema"] = response_schema
    metadata["responseExample"] = response_example
    warnings_after = source_index.get("warnings", [])
    metadata["schemaWarnings"] = warnings_after[warnings_before:]
    return item


def extract_from_java_file(java_file: Path, source_index: dict):
    index_java_file(java_file, source_index)
    content = source_index["contents"][java_file]
    if not BUSINESS_CENTER_PATTERN.search(content):
        return []

    package_match = PACKAGE_PATTERN.search(content)
    type_match = TYPE_PATTERN.search(content)
    if not package_match or not type_match:
        return []

    package_name = package_match.group(1)
    service_name = type_match.group(2)
    service_fqcn = f"{package_name}.{service_name}"

    lines = content.splitlines()
    results: list[ExtractedMethod] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if BUSINESS_DESCRIPTOR_PREFIX not in stripped:
            index += 1
            continue

        annotation_text, annotation_end = collect_annotation(lines, index)
        annotation_values = parse_annotation_arguments(annotation_text)
        signature_text, signature_end = collect_signature(lines, annotation_end + 1)
        signature_line = annotation_end + 2
        method_info = parse_method_signature(signature_text)
        method_name = method_info["methodName"]
        business_method = annotation_values.get("name") or method_name
        summary = annotation_values.get("desc") or business_method
        return_desc = annotation_values.get("returnDesc") or method_info["returnType"]
        evidence = [f"{display_path(java_file)}:{signature_line}"]

        metadata = {
            "serviceFqcn": service_fqcn,
            "serviceName": service_name,
            "methodName": method_name,
            "businessMethod": business_method,
            "summary": summary,
            "description": summary,
            "returnType": method_info["returnType"],
            "returnDesc": return_desc,
            "parameters": method_info["parameters"],
            "evidence": evidence,
        }
        results.append(ExtractedMethod(metadata=metadata, method_line=signature_line, source_file=java_file))
        index = signature_end + 1
    return results


def collect_java_files(source: Path):
    if source.is_file():
        return [source]
    return sorted(path for path in source.rglob("*.java") if path.is_file())


def filter_methods(methods: Iterable[ExtractedMethod], method_name: str | None, business_method: str | None):
    filtered = []
    for item in methods:
        if method_name and item.metadata["methodName"] != method_name:
            continue
        if business_method and item.metadata["businessMethod"] != business_method:
            continue
        filtered.append(item)
    return filtered


def generate_files(items: list[ExtractedMethod], args, timestamp: datetime):
    generated = []
    for item in items:
        metadata = item.metadata
        server_url = metadata.get("serverUrl") or args.server_url
        api_path = metadata.get("path") or args.api_path
        openapi_doc, service_name, business_method = generate_openapi.build_openapi(metadata, server_url, api_path)
        _, openapi_path, metadata_path = generate_openapi.build_output_paths(
            args.output_root, timestamp, service_name, business_method
        )
        generate_openapi.write_json_file(openapi_path, openapi_doc)
        if args.save_metadata:
            generate_openapi.write_json_file(metadata_path, metadata)
        generated.append(openapi_path)
    return generated


def main():
    args = parse_args()
    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"Source not found: {source}")

    timestamp = generate_openapi.parse_timestamp(args.timestamp)
    java_files = collect_java_files(source)
    source_index = build_type_index(java_files if source.is_file() else [], collect_search_roots(source, java_files))
    extracted: list[ExtractedMethod] = []
    for java_file in java_files:
        extracted.extend(extract_from_java_file(java_file, source_index))

    extracted = filter_methods(extracted, args.method, args.business_method)
    if not extracted:
        raise SystemExit("No matching @BusinessDescriptor methods found")

    extracted = [enrich_method_metadata(item, source_index) for item in extracted]

    if args.metadata_only:
        payload = [item.metadata for item in extracted]
        if len(payload) == 1:
            json.dump(payload[0], sys.stdout, ensure_ascii=False, indent=2)
        else:
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    for path in generate_files(extracted, args, timestamp):
        print(path)


if __name__ == "__main__":
    main()
