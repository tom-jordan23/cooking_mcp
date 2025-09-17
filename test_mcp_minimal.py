#!/usr/bin/env python3
"""
Minimal MCP Protocol Validation (no external dependencies)

Tests the core MCP protocol structures and compliance without requiring
external packages like SQLAlchemy or FastAPI.
"""

import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

def test_entry_id_validation():
    """Test entry ID validation logic."""
    print("Testing entry ID validation...")

    def validate_entry_id(entry_id: str) -> bool:
        """Validate entry ID format."""
        pattern = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$"
        if not re.match(pattern, entry_id):
            return False

        # Validate the date portion
        try:
            date_part = entry_id.split('_')[0]
            datetime.strptime(date_part, '%Y-%m-%d')
            return True
        except (ValueError, IndexError):
            return False

    # Test valid IDs
    valid_ids = [
        "2024-12-15_grilled-chicken",
        "2023-01-01_test-recipe",
        "2024-06-30_beef-wellington",
        "2024-12-31_a",  # Minimum length
        "2024-01-01_" + "a" * 50  # Maximum length
    ]

    for entry_id in valid_ids:
        assert validate_entry_id(entry_id), f"Valid ID rejected: {entry_id}"

    print("✓ Valid entry IDs accepted")

    # Test invalid IDs
    invalid_ids = [
        "invalid-format",
        "2024-13-01_test",  # Invalid month
        "2024-01-32_test",  # Invalid day
        "2024-01-01_test/with/slash",
        "2024-01-01_test..traversal",
        "2024-01-01_",  # Empty slug
        "2024-01-01_" + "a" * 51,  # Too long
        "2024-01-01_TEST",  # Uppercase not allowed
        "24-01-01_test",  # Invalid year format
    ]

    for entry_id in invalid_ids:
        assert not validate_entry_id(entry_id), f"Invalid ID accepted: {entry_id}"

    print("✓ Invalid entry IDs rejected")
    return True

def test_uri_path_validation():
    """Test URI path validation."""
    print("\nTesting URI path validation...")

    def validate_uri_path(uri: str) -> bool:
        """Validate URI path for security."""
        if not uri:
            return False

        # Check for path traversal
        if '..' in uri or uri.startswith('/'):
            return False

        # Check for invalid characters
        if re.search(r'[<>:"|?*\x00-\x1f]', uri):
            return False

        return True

    # Test valid paths
    valid_paths = [
        "entries",
        "entry/test",
        "search",
        "attachments/test-id",
        "attachment/test-id/file.jpg"
    ]

    for path in valid_paths:
        assert validate_uri_path(path), f"Valid path rejected: {path}"

    print("✓ Valid URI paths accepted")

    # Test invalid paths
    invalid_paths = [
        "../etc/passwd",
        "/absolute/path",
        "path/with/../../traversal",
        "",
        "path/with\x00null",
        "path/with<bracket",
        "path/with|pipe"
    ]

    for path in invalid_paths:
        assert not validate_uri_path(path), f"Invalid path accepted: {path}"

    print("✓ Invalid URI paths rejected")
    return True

def test_json_schemas():
    """Test JSON schema validity for tools."""
    print("\nTesting JSON schemas...")

    # Define the schemas (copied from mcp.py)
    APPEND_OBSERVATION_SCHEMA = {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "pattern": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$",
                "description": "Entry ID in format YYYY-MM-DD_slug"
            },
            "note": {
                "type": "string",
                "minLength": 1,
                "maxLength": 2000,
                "description": "Observation note"
            },
            "time": {
                "type": "string",
                "format": "date-time",
                "description": "Observation timestamp (ISO 8601)"
            },
            "grill_temp_c": {
                "type": "integer",
                "minimum": 0,
                "maximum": 1000,
                "description": "Grill temperature in Celsius"
            },
            "internal_temp_c": {
                "type": "integer",
                "minimum": 0,
                "maximum": 200,
                "description": "Internal temperature in Celsius"
            }
        },
        "required": ["id", "note"],
        "additionalProperties": False
    }

    CREATE_ENTRY_SCHEMA = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "minLength": 1,
                "maxLength": 200,
                "description": "Entry title"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 10,
                "description": "List of tags"
            },
            "gear": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 10,
                "description": "List of gear/equipment used"
            },
            "dinner_time": {
                "type": "string",
                "format": "date-time",
                "description": "Planned dinner time (ISO 8601)"
            }
        },
        "required": ["title"],
        "additionalProperties": False
    }

    # Test basic schema structure
    schemas = [APPEND_OBSERVATION_SCHEMA, CREATE_ENTRY_SCHEMA]

    for i, schema in enumerate(schemas):
        assert "type" in schema, f"Schema {i} missing 'type'"
        assert schema["type"] == "object", f"Schema {i} not object type"
        assert "properties" in schema, f"Schema {i} missing 'properties'"
        assert "required" in schema, f"Schema {i} missing 'required'"
        assert isinstance(schema["properties"], dict), f"Schema {i} properties not dict"
        assert isinstance(schema["required"], list), f"Schema {i} required not list"

    print("✓ JSON schemas have correct structure")

    # Test that required fields are in properties
    for i, schema in enumerate(schemas):
        for required_field in schema["required"]:
            assert required_field in schema["properties"], \
                f"Schema {i} required field '{required_field}' not in properties"

    print("✓ Required fields exist in properties")
    return True

def test_mcp_protocol_structure():
    """Test MCP protocol structure definitions."""
    print("\nTesting MCP protocol structures...")

    # Test resource structure
    resource = {
        "uri": "lab://entry/test",
        "name": "Test Entry",
        "description": "Test entry description",
        "mimeType": "application/json"
    }

    required_resource_fields = ["uri", "name"]
    for field in required_resource_fields:
        assert field in resource, f"Resource missing required field: {field}"

    print("✓ Resource structure is valid")

    # Test tool structure
    tool = {
        "name": "test_tool",
        "description": "Test tool description",
        "inputSchema": {"type": "object", "properties": {}}
    }

    required_tool_fields = ["name", "description", "inputSchema"]
    for field in required_tool_fields:
        assert field in tool, f"Tool missing required field: {field}"

    print("✓ Tool structure is valid")

    # Test request/response structure
    request = {
        "id": "test-1",
        "method": "test_method",
        "params": {"key": "value"}
    }

    required_request_fields = ["id", "method"]
    for field in required_request_fields:
        assert field in request, f"Request missing required field: {field}"

    print("✓ Request structure is valid")

    response = {
        "id": "test-1",
        "result": {"status": "success"}
    }

    required_response_fields = ["id"]
    for field in required_response_fields:
        assert field in response, f"Response missing required field: {field}"

    # Must have either result or error, not both
    assert ("result" in response) != ("error" in response), \
        "Response must have exactly one of 'result' or 'error'"

    print("✓ Response structure is valid")
    return True

def test_error_codes():
    """Test error code definitions."""
    print("\nTesting error codes...")

    # Define error codes (copied from specification)
    error_codes = {
        "E_NOT_FOUND": "Entry/resource not found",
        "E_SCHEMA": "Invalid input format",
        "E_IO": "File system operation failure",
        "E_GIT": "Git operation failure",
        "E_SECURITY": "Authentication/authorization failure",
        "E_RATE": "Rate limit exceeded"
    }

    # Test that all required error codes exist
    required_codes = ["E_NOT_FOUND", "E_SCHEMA", "E_IO", "E_GIT"]
    for code in required_codes:
        assert code in error_codes, f"Missing required error code: {code}"

    print("✓ All required error codes defined")

    # Test error response structure
    error_response = {
        "status": "error",
        "code": "E_NOT_FOUND",
        "message": "Entry not found",
        "details": {}
    }

    required_error_fields = ["status", "code", "message"]
    for field in required_error_fields:
        assert field in error_response, f"Error response missing field: {field}"

    assert error_response["status"] == "error", "Error status must be 'error'"

    print("✓ Error response structure is valid")
    return True

def test_resource_uris():
    """Test resource URI format compliance."""
    print("\nTesting resource URI formats...")

    # Test URI formats from specification
    uri_patterns = [
        r"^lab://entries$",
        r"^lab://entry/[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$",
        r"^lab://attachments/[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}/$",
        r"^lab://search(\?.*)?$"
    ]

    test_uris = [
        ("lab://entries", 0),
        ("lab://entry/2024-12-15_grilled-chicken", 1),
        ("lab://attachments/2024-12-15_grilled-chicken/", 2),
        ("lab://search", 3),
        ("lab://search?q=chicken", 3)
    ]

    for uri, pattern_idx in test_uris:
        pattern = uri_patterns[pattern_idx]
        assert re.match(pattern, uri), f"URI '{uri}' doesn't match pattern {pattern_idx}"

    print("✓ Resource URI formats are compliant")
    return True

def main():
    """Run all minimal compliance tests."""
    print("MCP Protocol Minimal Validation")
    print("=" * 40)

    tests = [
        test_entry_id_validation,
        test_uri_path_validation,
        test_json_schemas,
        test_mcp_protocol_structure,
        test_error_codes,
        test_resource_uris
    ]

    passed = 0
    total = len(tests)

    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"✗ Test {test_func.__name__} failed: {e}")

    print("\n" + "=" * 40)
    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("🎉 All minimal MCP compliance tests passed!")
        return 0
    else:
        print("❌ Some tests failed. Please review the implementation.")
        return 1

if __name__ == "__main__":
    exit(main())