"""
Tests for database models and operations.

Validates SQLAlchemy models, database connections, and async operations.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import (
    Base,
    NotebookEntry,
    FeedbackEntry,
    MCPResource,
    MCPTool,
    init_database,
    close_database
)


class TestDatabaseModels:
    """Test suite for database models."""

    @pytest.mark.asyncio
    async def test_notebook_entry_creation(self, test_db_session: AsyncSession):
        """Test creating a notebook entry."""
        entry = NotebookEntry(
            entry_id="2024-01-15_test-recipe",
            title="Test Recipe",
            date=datetime(2024, 1, 15),
            tags=["test", "sample"],
            servings=4,
            prep_time_minutes=15,
            cook_time_minutes=30,
            total_time_minutes=45,
            protocol="Test cooking instructions",
            content={"test": "data"}
        )

        test_db_session.add(entry)
        await test_db_session.commit()

        # Query the entry back
        result = await test_db_session.execute(
            select(NotebookEntry).where(NotebookEntry.entry_id == "2024-01-15_test-recipe")
        )
        saved_entry = result.scalar_one()

        assert saved_entry.title == "Test Recipe"
        assert saved_entry.servings == 4
        assert saved_entry.tags == ["test", "sample"]
        assert saved_entry.created_at is not None

    @pytest.mark.asyncio
    async def test_feedback_entry_creation(self, test_db_session: AsyncSession):
        """Test creating a feedback entry."""
        # First create a notebook entry
        notebook_entry = NotebookEntry(
            entry_id="2024-01-15_test-recipe",
            title="Test Recipe",
            date=datetime(2024, 1, 15),
            content={}
        )
        test_db_session.add(notebook_entry)
        await test_db_session.commit()

        # Create feedback entry
        feedback = FeedbackEntry(
            entry_id="2024-01-15_test-recipe",
            who="testuser",
            rating_10=8,
            axes={
                "doneness": "perfect",
                "salt": "just right"
            },
            notes="Great recipe!",
            feedback_data={"additional": "data"}
        )
        test_db_session.add(feedback)
        await test_db_session.commit()

        # Query the feedback back
        result = await test_db_session.execute(
            select(FeedbackEntry).where(FeedbackEntry.entry_id == "2024-01-15_test-recipe")
        )
        saved_feedback = result.scalar_one()

        assert saved_feedback.who == "testuser"
        assert saved_feedback.rating_10 == 8
        assert saved_feedback.axes["doneness"] == "perfect"
        assert saved_feedback.notes == "Great recipe!"

    @pytest.mark.asyncio
    async def test_mcp_resource_creation(self, test_db_session: AsyncSession):
        """Test creating an MCP resource."""
        resource = MCPResource(
            uri="lab://entries",
            name="Notebook Entries",
            description="List of all notebook entries",
            mime_type="application/json",
            last_accessed=datetime.now(timezone.utc)
        )
        test_db_session.add(resource)
        await test_db_session.commit()

        # Query the resource back
        result = await test_db_session.execute(
            select(MCPResource).where(MCPResource.uri == "lab://entries")
        )
        saved_resource = result.scalar_one()

        assert saved_resource.name == "Notebook Entries"
        assert saved_resource.mime_type == "application/json"

    @pytest.mark.asyncio
    async def test_mcp_tool_creation(self, test_db_session: AsyncSession):
        """Test creating an MCP tool."""
        tool = MCPTool(
            name="append_observation",
            description="Append an observation to a notebook entry",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "note": {"type": "string"}
                }
            },
            last_used=datetime.now(timezone.utc),
            usage_count=0
        )
        test_db_session.add(tool)
        await test_db_session.commit()

        # Query the tool back
        result = await test_db_session.execute(
            select(MCPTool).where(MCPTool.name == "append_observation")
        )
        saved_tool = result.scalar_one()

        assert saved_tool.description == "Append an observation to a notebook entry"
        assert saved_tool.usage_count == 0
        assert "properties" in saved_tool.input_schema

    @pytest.mark.asyncio
    async def test_notebook_entry_with_relationships(self, test_db_session: AsyncSession):
        """Test notebook entry with feedback relationships."""
        # Create notebook entry
        entry = NotebookEntry(
            entry_id="2024-01-15_test-recipe",
            title="Test Recipe",
            date=datetime(2024, 1, 15),
            content={}
        )
        test_db_session.add(entry)

        # Create multiple feedback entries
        feedback1 = FeedbackEntry(
            entry_id="2024-01-15_test-recipe",
            who="user1",
            rating_10=8,
            feedback_data={}
        )
        feedback2 = FeedbackEntry(
            entry_id="2024-01-15_test-recipe",
            who="user2",
            rating_10=9,
            feedback_data={}
        )
        test_db_session.add(feedback1)
        test_db_session.add(feedback2)
        await test_db_session.commit()

        # Query entry with feedback
        result = await test_db_session.execute(
            select(NotebookEntry).where(NotebookEntry.entry_id == "2024-01-15_test-recipe")
        )
        saved_entry = result.scalar_one()

        # Check relationships
        feedbacks = await test_db_session.execute(
            select(FeedbackEntry).where(FeedbackEntry.entry_id == saved_entry.entry_id)
        )
        feedback_list = feedbacks.scalars().all()

        assert len(feedback_list) == 2
        assert feedback_list[0].who in ["user1", "user2"]
        assert feedback_list[1].who in ["user1", "user2"]

    @pytest.mark.asyncio
    async def test_database_constraints(self, test_db_session: AsyncSession):
        """Test database constraints and validations."""
        from sqlalchemy.exc import IntegrityError

        # Test unique constraint on entry_id
        entry1 = NotebookEntry(
            entry_id="2024-01-15_duplicate",
            title="Entry 1",
            date=datetime(2024, 1, 15),
            content={}
        )
        entry2 = NotebookEntry(
            entry_id="2024-01-15_duplicate",  # Same ID
            title="Entry 2",
            date=datetime(2024, 1, 15),
            content={}
        )

        test_db_session.add(entry1)
        await test_db_session.commit()

        test_db_session.add(entry2)
        with pytest.raises(IntegrityError):
            await test_db_session.commit()

        await test_db_session.rollback()

    @pytest.mark.asyncio
    async def test_json_field_handling(self, test_db_session: AsyncSession):
        """Test JSON field storage and retrieval."""
        complex_data = {
            "ingredients": [
                {"name": "flour", "amount": "500g"},
                {"name": "water", "amount": "300ml"}
            ],
            "steps": ["mix", "knead", "bake"],
            "nested": {
                "deeply": {
                    "nested": "value"
                }
            }
        }

        entry = NotebookEntry(
            entry_id="2024-01-15_json-test",
            title="JSON Test",
            date=datetime(2024, 1, 15),
            content=complex_data
        )
        test_db_session.add(entry)
        await test_db_session.commit()

        # Query back and verify JSON integrity
        result = await test_db_session.execute(
            select(NotebookEntry).where(NotebookEntry.entry_id == "2024-01-15_json-test")
        )
        saved_entry = result.scalar_one()

        assert saved_entry.content["ingredients"][0]["name"] == "flour"
        assert saved_entry.content["nested"]["deeply"]["nested"] == "value"
        assert len(saved_entry.content["steps"]) == 3

    @pytest.mark.asyncio
    async def test_timestamp_fields(self, test_db_session: AsyncSession):
        """Test automatic timestamp fields."""
        entry = NotebookEntry(
            entry_id="2024-01-15_timestamp-test",
            title="Timestamp Test",
            date=datetime(2024, 1, 15),
            content={}
        )
        test_db_session.add(entry)
        await test_db_session.commit()

        assert entry.created_at is not None
        assert entry.updated_at is not None
        assert entry.created_at <= entry.updated_at

        # Update the entry
        original_updated = entry.updated_at
        entry.title = "Updated Title"
        await test_db_session.commit()

        # updated_at should change
        assert entry.updated_at > original_updated

    @pytest.mark.asyncio
    async def test_query_pagination(self, test_db_session: AsyncSession):
        """Test database query pagination."""
        # Create multiple entries
        for i in range(10):
            entry = NotebookEntry(
                entry_id=f"2024-01-{i:02d}_test",
                title=f"Test Recipe {i}",
                date=datetime(2024, 1, i + 1),
                content={}
            )
            test_db_session.add(entry)
        await test_db_session.commit()

        # Test pagination
        result = await test_db_session.execute(
            select(NotebookEntry)
            .order_by(NotebookEntry.date)
            .limit(5)
            .offset(0)
        )
        first_page = result.scalars().all()
        assert len(first_page) == 5

        result = await test_db_session.execute(
            select(NotebookEntry)
            .order_by(NotebookEntry.date)
            .limit(5)
            .offset(5)
        )
        second_page = result.scalars().all()
        assert len(second_page) == 5

        # Verify no overlap
        first_ids = [e.entry_id for e in first_page]
        second_ids = [e.entry_id for e in second_page]
        assert len(set(first_ids) & set(second_ids)) == 0


class TestDatabaseOperations:
    """Test suite for database operations."""

    @pytest.mark.asyncio
    async def test_init_database_creates_tables(self, test_db_engine):
        """Test that init_database creates all tables."""
        from sqlalchemy import inspect

        async with test_db_engine.connect() as conn:
            def check_tables(connection):
                inspector = inspect(connection)
                return inspector.get_table_names()

            tables = await conn.run_sync(check_tables)

        expected_tables = [
            "notebook_entries",
            "feedback_entries",
            "mcp_resources",
            "mcp_tools"
        ]

        for table in expected_tables:
            assert table in tables

    @pytest.mark.asyncio
    async def test_database_transaction_rollback(self, test_db_session: AsyncSession):
        """Test database transaction rollback."""
        entry = NotebookEntry(
            entry_id="2024-01-15_rollback-test",
            title="Rollback Test",
            date=datetime(2024, 1, 15),
            content={}
        )
        test_db_session.add(entry)

        # Don't commit, just rollback
        await test_db_session.rollback()

        # Entry should not exist
        result = await test_db_session.execute(
            select(NotebookEntry).where(NotebookEntry.entry_id == "2024-01-15_rollback-test")
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_concurrent_database_access(self, test_db_engine):
        """Test concurrent database access."""
        from sqlalchemy.ext.asyncio import async_sessionmaker

        async_session = async_sessionmaker(test_db_engine, expire_on_commit=False)

        async def create_entry(session, entry_id):
            entry = NotebookEntry(
                entry_id=entry_id,
                title=f"Concurrent {entry_id}",
                date=datetime(2024, 1, 15),
                content={}
            )
            session.add(entry)
            await session.commit()

        # Create multiple sessions and entries concurrently
        import asyncio
        tasks = []
        for i in range(5):
            async with async_session() as session:
                task = create_entry(session, f"2024-01-15_concurrent-{i}")
                tasks.append(task)

        await asyncio.gather(*tasks)

        # Verify all entries were created
        async with async_session() as session:
            result = await session.execute(
                select(NotebookEntry).where(
                    NotebookEntry.entry_id.like("2024-01-15_concurrent-%")
                )
            )
            entries = result.scalars().all()
            assert len(entries) == 5