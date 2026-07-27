"""Tests for artifact store."""

import pytest

from artifacts.store import FileArtifactStore
from utils.exceptions import ArtifactNotFoundError


def test_write_and_read_latest(temp_artifact_store):
    store = temp_artifact_store
    ref = store.write("proj1", "job1", "Understanding.md", "# Understanding\nTest")
    assert ref.version == 1

    content = store.read_latest("proj1", "job1", "Understanding.md")
    assert "Understanding" in content


def test_version_increment(temp_artifact_store):
    store = temp_artifact_store
    ref1 = store.write("proj1", "job1", "Understanding.md", "v1 content")
    ref2 = store.write("proj1", "job1", "Understanding.md", "v2 content")

    assert ref1.version == 1
    assert ref2.version == 2

    latest = store.read_latest("proj1", "job1", "Understanding.md")
    assert latest == "v2 content"


def test_read_specific_version(temp_artifact_store):
    store = temp_artifact_store
    store.write("proj1", "job1", "Understanding.md", "v1 content")
    store.write("proj1", "job1", "Understanding.md", "v2 content")

    content = store.read_version("proj1", "job1", "Understanding.md", 1)
    assert content == "v1 content"


def test_list_versions(temp_artifact_store):
    store = temp_artifact_store
    store.write("proj1", "job1", "Understanding.md", "v1")
    store.write("proj1", "job1", "Understanding.md", "v2")

    versions = store.list_versions("proj1", "job1", "Understanding.md")
    assert len(versions) == 2


def test_content_hash_stored(temp_artifact_store):
    store = temp_artifact_store
    ref = store.write("proj1", "job1", "Understanding.md", "test content")
    assert len(ref.content_hash) == 64


def test_artifact_not_found(temp_artifact_store):
    store = temp_artifact_store
    with pytest.raises(ArtifactNotFoundError):
        store.read_latest("proj1", "job1", "Understanding.md")
