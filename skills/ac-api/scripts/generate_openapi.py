#!/usr/bin/env python3
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_OUTPUT_ROOT = ".claude/OpenAPI"
DEFAULT_SERVER_URL = "http://127.0.0.1:8888"
DEFAULT_API_PATH = "/json-adapter"
NAME_BASED_INTEGER_KEYS = {"id", "ids", "projectid", "userid", "tenantid", "orgid", "page", "pageno", "pagenum", "index", "offset", "size", "pagesize", "limit", "total", "count", "code", "sort", "order"}
NAME_BASED_BOOLEAN_KEYS = {"flag", "enabled", "enable", "disabled", "success", "ok", "deleted", "valid", "visible"}
NAME_BASED_ARRAY_KEYS = {"ids", "list", "items", "records", "rows", "data", "children"}
NAME_BASED_TIME_KEYS = {"time", "date", "datetime", "start", "end", "begin", "finish", "createdat", "updatedat"}
NAME_BASED_STRING_KEYS = {"name", "title", "type", "status", "state", "code", "message", "remark", "description", "content", "keyword", "sn", "no"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a single-endpoint OpenAPI 3.1 JSON file for SKSPIOT business services."
    )
    parser.add_argument("--input", required=True, help="Metadata JSON file path, or - for stdin")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, help="Output root directory")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL, help="Server URL")
    parser.add_argument("--path", dest="api_path", default=DEFAULT_API_PATH, help="HTTP path")
    parser.add_argument("--timestamp", help="Timestamp override, format: YYYY-MM-DDTHH:MM or YYYY-MM-DD HH:MM")
    parser.add_argument(
        "--save-metadata",
        action="store_true",
        help="Save the normalized metadata JSON next to the generated OpenAPI file",
    )
    return parser.parse_args()


def load_metadata(input_path: str):
    if input_path == "-":
        return json.load(sys.stdin)
    with open(input_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_timestamp(raw: str | None):
    if not raw:
        return datetime.now()
    normalized = raw.strip().replace(" ", "T")
    return datetime.strptime(normalized, "%Y-%m-%dT%H:%M")


def sanitize_filename_part(value: str, fallback: str):
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", (value or "").strip())
    cleaned = cleaned.strip("._")
    return cleaned or fallback


def infer_schema(value):
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        items_schema = {}
        if value:
            first_schema = infer_schema(value[0])
            if all(infer_schema(item) == first_schema for item in value[1:]):
                items_schema = first_schema
        return {"type": "array", "items": items_schema}
    if isinstance(value, dict):
        properties = {}
        required = []
        for key, item in value.items():
            properties[key] = infer_schema(item)
            required.append(key)
        schema = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            schema["required"] = required
        return schema
    return {}


def ensure_required(metadata, field_name):
    value = metadata.get(field_name)
    if value in (None, ""):
        raise ValueError(f"Missing required field: {field_name}")
    return value


def normalize_name_key(value: str):
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def guess_value_from_name(name: str):
    key = normalize_name_key(name)
    if key in NAME_BASED_BOOLEAN_KEYS:
        return True
    if key in NAME_BASED_ARRAY_KEYS:
        return []
    if key in NAME_BASED_INTEGER_KEYS:
        if key in {"size", "pagesize", "limit"}:
            return 10
        if key in {"page", "pageno", "pagenum", "index", "offset"}:
            return 1
        if key == "code":
            return 200
        return 1
    if any(token in key for token in NAME_BASED_TIME_KEYS):
        return "2026-04-21T00:00:00"
    if key in NAME_BASED_STRING_KEYS:
        return name
    return None


def simplify_java_type(java_type: str):
    cleaned = (java_type or "").strip().replace("...", "[]")
    cleaned = re.sub(r"<.*>", "", cleaned)
    cleaned = cleaned.rsplit(".", 1)[-1]
    return cleaned


def guess_object_example(name: str, java_type: str):
    key = normalize_name_key(name)
    type_key = normalize_name_key(java_type)
    text = f"{key} {type_key}"
    example = {}

    if any(token in text for token in ["project", "station", "tenant", "org"]):
        example["projectId"] = 1
    if any(token in text for token in ["page", "query", "search", "list", "condition", "filter"]):
        example["pageNo"] = 1
        example["pageSize"] = 10
    if any(token in text for token in ["keyword", "search"]):
        example["keyword"] = "keyword"
    if any(token in text for token in ["time", "date", "start", "begin"]):
        example["startTime"] = "2026-04-21T00:00:00"
        example["endTime"] = "2026-04-21T23:59:59"
    if any(token in text for token in ["user", "member", "owner"]):
        example.setdefault("userId", 1)
    if not example and key in {"vo", "dto", "req", "request", "query", "param", "params", "body"}:
        example["id"] = 1
    return example


def guess_value_from_type(name: str, java_type: str):
    base_type = simplify_java_type(java_type)
    base_key = normalize_name_key(base_type)
    if java_type.endswith("[]"):
        return []
    if base_type in {"boolean", "Boolean"}:
        return True
    if base_type in {"byte", "Byte", "short", "Short", "int", "Integer", "long", "Long"}:
        return 1
    if base_type in {"float", "Float", "double", "Double", "BigDecimal"}:
        return 0.0
    if base_type in {"String", "CharSequence"}:
        return name or "value"
    if base_key.endswith(("list", "array", "set", "collection")):
        return []
    if base_key.endswith("map"):
        return {}
    guessed_object = guess_object_example(name, java_type)
    if guessed_object:
        return guessed_object
    return {}


def ensure_parameter_example(parameter):
    if "example" in parameter and parameter["example"] not in (None, "", {}, []):
        return parameter["example"]
    guessed = guess_value_from_name(parameter.get("name", ""))
    if guessed is not None:
        return guessed
    return guess_value_from_type(parameter.get("name", ""), parameter.get("type", ""))


def build_param_schema(parameter):
    if "schema" in parameter and isinstance(parameter["schema"], dict):
        return parameter["schema"]
    example = ensure_parameter_example(parameter)
    schema = infer_schema(example)
    if schema == {}:
        schema = {"type": "object", "additionalProperties": False}
    java_type = parameter.get("type")
    if java_type:
        schema["description"] = f"Java type: {java_type}"
    return schema


def build_example_from_schema(schema, name=""):
    if not isinstance(schema, dict):
        return {}

    schema_type = schema.get("type")
    schema_format = schema.get("format")
    key = normalize_name_key(name)

    if schema_type == "boolean":
        return True
    if schema_type == "integer":
        if key in {"status", "state", "sort", "order"}:
            return 0
        if key in {"size", "pagesize", "limit"}:
            return 10
        if key in {"page", "pageno", "pagenum", "index", "offset"}:
            return 1
        return 1
    if schema_type == "number":
        return 0.0
    if schema_type == "string":
        if schema_format == "date":
            return "2026-04-21"
        if schema_format == "date-time":
            return "2026-04-21T00:00:00"
        return name or "value"
    if schema_type == "array":
        items = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        item_example = build_example_from_schema(items, name)
        if item_example in (None, {}, []):
            return []
        return [item_example]
    if schema_type == "object":
        properties = schema.get("properties")
        if isinstance(properties, dict):
            return {
                key: build_example_from_schema(value, key)
                for key, value in properties.items()
            }
        return {}
    if schema_type == "null":
        return None
    return {}


def is_fixed_response_envelope_dict(value):
    return isinstance(value, dict) and {"code", "success", "data", "msg"}.issubset(value.keys())


def is_fixed_response_envelope_schema(schema):
    if not isinstance(schema, dict):
        return False
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return False
    return {"code", "success", "data", "msg"}.issubset(properties.keys())


def build_fixed_response_envelope(data_schema, data_example):
    envelope_schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "const": "success",
                "description": "Fixed success code",
            },
            "success": {
                "type": "boolean",
                "const": True,
                "description": "Fixed success flag",
            },
            "data": data_schema,
            "msg": {
                "type": "string",
                "const": "操作成功",
                "description": "Fixed success message",
            },
        },
        "required": ["code", "success", "data", "msg"],
        "additionalProperties": False,
    }
    envelope_example = {
        "code": "success",
        "success": True,
        "data": data_example,
        "msg": "操作成功",
    }
    return envelope_schema, envelope_example


def build_request(metadata, bid: str):
    parameters = metadata.get("parameters") or []
    params_properties = {}
    params_required = []
    params_example = {}

    for parameter in parameters:
        name = ensure_required(parameter, "name")
        example = ensure_parameter_example(parameter)
        if parameter.get("example") in (None, "", {}, []):
            parameter["example"] = example
        params_properties[name] = build_param_schema(parameter)
        params_required.append(name)
        params_example[name] = example

    params_schema = {
        "type": "object",
        "properties": params_properties,
        "additionalProperties": False,
    }
    if params_required:
        params_schema["required"] = params_required

    request_schema = {
        "type": "object",
        "properties": {
            "bid": {
                "type": "string",
                "const": bid,
                "description": "Business identifier",
            },
            "params": params_schema,
            "passport": {
                "type": "string",
                "description": "Access token",
            },
        },
        "required": ["bid", "params", "passport"],
        "additionalProperties": False,
    }

    request_example = {
        "bid": bid,
        "params": params_example,
        "passport": "{{access_token}}",
    }
    return request_schema, request_example


def build_response(metadata):
    response_example = metadata.get("responseExample")
    response_schema = metadata.get("responseSchema")

    if is_fixed_response_envelope_dict(response_example) and is_fixed_response_envelope_schema(response_schema):
        return response_schema, response_example

    if isinstance(response_schema, dict):
        data_schema = response_schema
    else:
        if response_example in (None, "", {}):
            data_schema = {
                "type": "object",
                "additionalProperties": True,
            }
        else:
            data_schema = infer_schema(response_example)
            if data_schema == {}:
                data_schema = {
                    "type": "object",
                    "additionalProperties": True,
                }

    return_type = metadata.get("returnType")
    return_desc = metadata.get("returnDesc")
    if return_type and "title" not in data_schema:
        data_schema["title"] = return_type
    if return_desc and "description" not in data_schema:
        data_schema["description"] = return_desc

    if response_example in (None, "", {}):
        data_example = build_example_from_schema(data_schema, "data")
    else:
        data_example = response_example

    envelope_schema, envelope_example = build_fixed_response_envelope(data_schema, data_example)
    metadata["responseExample"] = envelope_example
    metadata["responseSchema"] = envelope_schema
    return envelope_schema, envelope_example


def build_description(metadata, bid: str):
    if metadata.get("description"):
        return str(metadata["description"])
    if metadata.get("summary"):
        return str(metadata["summary"])
    return ""


def build_openapi(metadata, server_url: str, api_path: str):
    service_fqcn = ensure_required(metadata, "serviceFqcn")
    method_name = ensure_required(metadata, "methodName")
    business_method = metadata.get("businessMethod") or method_name
    service_name = metadata.get("serviceName") or service_fqcn.rsplit(".", 1)[-1]
    bid = f"{service_fqcn}.{business_method}"
    summary = metadata.get("summary") or metadata.get("description") or business_method
    request_schema, request_example = build_request(metadata, bid)
    response_schema, response_example = build_response(metadata)

    openapi = {
        "openapi": "3.1.0",
        "info": {
            "title": metadata.get("title") or f"{service_name}.{business_method}",
            "version": metadata.get("version") or "1.0.0",
            "description": build_description(metadata, bid),
        },
        "servers": [
            {
                "url": server_url,
            }
        ],
        "paths": {
            api_path: {
                "post": {
                    "tags": metadata.get("tags") or [service_name],
                    "summary": summary,
                    "description": build_description(metadata, bid),
                    "operationId": metadata.get("operationId") or f"{service_name}.{business_method}",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": request_schema,
                                "example": request_example,
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": metadata.get("responseDescription")
                            or metadata.get("returnDesc")
                            or metadata.get("returnType")
                            or "Success",
                            "content": {
                                "application/json": {
                                    "schema": response_schema,
                                }
                            },
                        }
                    },
                }
            }
        },
    }

    openapi["paths"][api_path]["post"]["responses"]["200"]["content"]["application/json"][
        "example"
    ] = response_example

    return openapi, service_name, business_method


def build_output_paths(output_root: str, timestamp: datetime, service_name: str, business_method: str):
    dated_dir = Path(output_root) / timestamp.strftime("%Y-%m-%d")
    dated_dir.mkdir(parents=True, exist_ok=True)
    service_part = sanitize_filename_part(service_name, "Service")
    method_part = sanitize_filename_part(business_method, "method")
    base_name = f"{timestamp.strftime('%H-%M')}_{service_part}.{method_part}"
    return dated_dir, dated_dir / f"{base_name}.openapi.json", dated_dir / f"{base_name}.metadata.json"


def write_json_file(path: Path, payload):
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main():
    args = parse_args()
    metadata = load_metadata(args.input)
    timestamp = parse_timestamp(args.timestamp)
    server_url = metadata.get("serverUrl") or args.server_url
    api_path = metadata.get("path") or args.api_path
    openapi_doc, service_name, business_method = build_openapi(metadata, server_url, api_path)
    _, output_path, metadata_path = build_output_paths(args.output_root, timestamp, service_name, business_method)
    write_json_file(output_path, openapi_doc)
    if args.save_metadata:
        write_json_file(metadata_path, metadata)
    print(output_path)


if __name__ == "__main__":
    main()
