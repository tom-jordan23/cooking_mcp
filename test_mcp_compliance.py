#!/usr/bin/env python3
"""
MCP Protocol Compliance Validation Script

This script validates the MCP server implementation against the MCP v0.1.0 protocol
specification to ensure compliance and correctness.
"""

import json
import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def test_mcp_models():
    """Test MCP protocol models for compliance."""
    print("Testing MCP protocol models...")

    try:
        from app.models.mcp import (
            MCPResource, MCPTool, MCPRequest, MCPResponse,
            ListResourcesResponse, ReadResourceResponse,
            CallToolResponse, ErrorCode,
            APPEND_OBSERVATION_SCHEMA, UPDATE_OUTCOMES_SCHEMA,
            CREATE_ENTRY_SCHEMA, GIT_COMMIT_SCHEMA, SYNTHESIZE_ICS_SCHEMA
        )
        print("✓ All MCP models imported successfully")

        # Test resource model
        resource = MCPResource(
            uri="lab://entry/test",
            name="Test Entry",
            description="Test entry description",
            mimeType="application/json"
        )
        assert resource.uri == "lab://entry/test"
        print("✓ MCPResource model works correctly")

        # Test tool model
        tool = MCPTool(
            name="test_tool",
            description="Test tool description",
            inputSchema={"type": "object", "properties": {}}
        )
        assert tool.name == "test_tool"
        print("✓ MCPTool model works correctly")

        # Test error codes
        assert ErrorCode.E_NOT_FOUND == "E_NOT_FOUND"
        assert ErrorCode.E_SCHEMA == "E_SCHEMA"
        print("✓ Error codes defined correctly")

        # Validate tool schemas
        required_schemas = [
            APPEND_OBSERVATION_SCHEMA,
            UPDATE_OUTCOMES_SCHEMA,
            CREATE_ENTRY_SCHEMA,
            GIT_COMMIT_SCHEMA,
            SYNTHESIZE_ICS_SCHEMA
        ]

        for schema in required_schemas:
            assert "type" in schema
            assert "properties" in schema
            assert "required" in schema
        print("✓ All tool schemas are valid JSON Schema")

        return True

    except Exception as e:
        print(f"✗ MCP models test failed: {e}")
        return False

def test_mcp_server_structure():
    """Test MCP server structure and interface."""
    print("\nTesting MCP server structure...")

    try:
        # Import without instantiation (avoid dependencies)
        import inspect
        from app.services.mcp_server import MCPServer

        # Check required methods exist
        required_methods = [
            'list_resources',
            'read_resource',
            'list_tools',
            'call_tool',
            'health_check'
        ]

        for method_name in required_methods:
            assert hasattr(MCPServer, method_name), f"Missing method: {method_name}"
            method = getattr(MCPServer, method_name)
            assert inspect.iscoroutinefunction(method), f"Method {method_name} should be async"

        print("✓ All required MCP server methods exist and are async")

        # Check tool handlers exist
        tool_handlers = [
            '_handle_append_observation',
            '_handle_update_outcomes',
            '_handle_create_entry',
            '_handle_git_commit',
            '_handle_synthesize_ics'
        ]

        for handler_name in tool_handlers:
            assert hasattr(MCPServer, handler_name), f"Missing tool handler: {handler_name}"

        print("✓ All tool handlers exist")

        return True

    except Exception as e:
        print(f"✗ MCP server structure test failed: {e}")
        return False

def test_search_service():
    """Test search service implementation."""
    print("\nTesting search service...")

    try:
        from app.services.search_service import SearchService, SearchFilter, SearchResult
        import inspect

        # Check main methods exist
        required_methods = [
            'search_entries',
            'get_popular_tags',
            'get_search_suggestions'
        ]

        for method_name in required_methods:
            assert hasattr(SearchService, method_name), f"Missing method: {method_name}"
            method = getattr(SearchService, method_name)
            assert inspect.iscoroutinefunction(method), f"Method {method_name} should be async"

        print("✓ Search service methods exist and are async")

        # Test filter model
        filter_obj = SearchFilter(
            cooking_method="grilling",
            difficulty_min=1,
            difficulty_max=5
        )
        assert filter_obj.cooking_method == "grilling"
        print("✓ SearchFilter model works correctly")

        return True

    except Exception as e:
        print(f"✗ Search service test failed: {e}")
        return False

def test_router_endpoints():
    """Test MCP router endpoints structure."""
    print("\nTesting MCP router endpoints...")

    try:
        from app.routers.mcp import router

        # Get all routes
        routes = [route for route in router.routes if hasattr(route, 'path')]
        route_paths = [route.path for route in routes]

        # Check required endpoints exist
        required_endpoints = [
            '/mcp/append_observation',
            '/mcp/update_outcomes',
            '/mcp/create_entry',
            '/mcp/git_commit',
            '/mcp/synthesize_ics',
            '/mcp/entry/{entry_id}',
            '/mcp/resources',
            '/mcp/resource',
            '/mcp/tools',
            '/mcp/health'
        ]

        for endpoint in required_endpoints:
            # Check if any route matches (handles path parameters)
            found = any(
                endpoint.replace('{entry_id}', 'test') in path.replace('{entry_id}', 'test')
                for path in route_paths
            )
            assert found, f"Missing endpoint: {endpoint}"

        print("✓ All required MCP endpoints exist")

        return True

    except Exception as e:
        print(f"✗ MCP router test failed: {e}")
        return False

def test_protocol_compliance():
    """Test MCP protocol compliance specifics."""
    print("\nTesting MCP protocol compliance...")

    try:
        from app.models.mcp import (
            MCPRequest, MCPResponse, MCPError,
            ListResourcesRequest, ReadResourceRequest,
            CallToolRequest
        )

        # Test request/response structure
        request = MCPRequest(id="test-1", method="test_method", params={"key": "value"})
        assert request.id == "test-1"
        assert request.method == "test_method"
        print("✓ MCPRequest structure is compliant")

        response = MCPResponse(id="test-1", result={"status": "success"})
        assert response.id == "test-1"
        assert response.result["status"] == "success"
        print("✓ MCPResponse structure is compliant")

        error = MCPError(code="E_TEST", message="Test error")
        assert error.code == "E_TEST"
        print("✓ MCPError structure is compliant")

        # Test specific request types
        list_req = ListResourcesRequest()
        assert list_req.method == "resources/list"
        print("✓ ListResourcesRequest is compliant")

        read_req = ReadResourceRequest(params={"uri": "lab://test"})
        assert read_req.method == "resources/read"
        print("✓ ReadResourceRequest is compliant")

        call_req = CallToolRequest(params={"name": "test_tool"})
        assert call_req.method == "tools/call"
        print("✓ CallToolRequest is compliant")

        return True

    except Exception as e:
        print(f"✗ Protocol compliance test failed: {e}")
        return False

def test_uri_validation():
    """Test URI validation functions."""
    print("\nTesting URI validation...")

    try:
        from app.models.mcp import validate_entry_id, validate_uri_path

        # Test valid entry IDs
        valid_ids = [
            "2024-12-15_grilled-chicken",
            "2023-01-01_test-recipe",
            "2024-06-30_beef-wellington"
        ]

        for entry_id in valid_ids:
            assert validate_entry_id(entry_id), f"Valid ID rejected: {entry_id}"

        print("✓ Valid entry IDs accepted")

        # Test invalid entry IDs
        invalid_ids = [
            "invalid-format",
            "2024-13-01_test",  # Invalid month
            "2024-01-01_test/with/slash",
            "2024-01-01_test..traversal"
        ]

        for entry_id in invalid_ids:
            assert not validate_entry_id(entry_id), f"Invalid ID accepted: {entry_id}"

        print("✓ Invalid entry IDs rejected")

        # Test URI path validation
        valid_paths = [
            "entries",
            "entry/test",
            "search"
        ]

        for path in valid_paths:
            assert validate_uri_path(path), f"Valid path rejected: {path}"

        print("✓ Valid URI paths accepted")

        # Test invalid URI paths
        invalid_paths = [
            "../etc/passwd",
            "/absolute/path",
            "path/with/../../traversal",
            ""
        ]

        for path in invalid_paths:
            assert not validate_uri_path(path), f"Invalid path accepted: {path}"

        print("✓ Invalid URI paths rejected")

        return True

    except Exception as e:
        print(f"✗ URI validation test failed: {e}")
        return False

def main():
    """Run all compliance tests."""
    print("MCP Protocol Compliance Validation")
    print("=" * 40)

    tests = [
        test_mcp_models,
        test_mcp_server_structure,
        test_search_service,
        test_router_endpoints,
        test_protocol_compliance,
        test_uri_validation
    ]

    passed = 0
    total = len(tests)

    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"✗ Test {test_func.__name__} crashed: {e}")

    print("\n" + "=" * 40)
    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("🎉 All MCP compliance tests passed!")
        return 0
    else:
        print("❌ Some tests failed. Please review the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())