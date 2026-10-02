from datetime import UTC, datetime

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from satara.domain import Archive, ArchiveName, EntryName

# A small pool makes collisions, and collisions with generated names, common.
pooled_names = st.builds(
    lambda stem, extensions: stem + extensions,
    st.sampled_from(["foo", "foo-2", "bar", ".bashrc"]),
    st.sampled_from(["", ".txt", ".tar.gz"]),
)
free_names = st.text(
    alphabet=st.characters(categories=["L", "N"], include_characters=" .-_"),
    min_size=1,
).filter(lambda value: value not in {".", ".."})
names = st.lists(st.one_of(pooled_names, free_names).map(EntryName.model_validate), max_size=30)


@pytest.mark.parametrize(
    "value",
    ["", ".", "..", "dir/foo.txt", "dir\\foo.txt", "C:foo.txt"],
    ids=["empty", "current directory", "parent directory", "slash", "backslash", "drive"],
)
def test_entry_name_refuses_anything_but_a_single_file_name(value):
    with pytest.raises(ValidationError):
        EntryName.model_validate(value)


def test_entry_name_accepts_any_characters_a_file_name_may_hold():
    entry_name = EntryName.model_validate("naïve résumé (1).txt")

    assert str(entry_name) == "naïve résumé (1).txt"


def test_archive_name_accepts_ascii_letters_digits_and_three_punctuation_marks():
    archive_name = ArchiveName.model_validate("Report_2026-10.final")

    assert str(archive_name) == "Report_2026-10.final"


def test_archive_name_accepts_up_to_a_hundred_characters():
    archive_name = ArchiveName.model_validate("x" * 100)

    assert str(archive_name) == "x" * 100


@pytest.mark.parametrize(
    "value",
    ["", ".hidden", "-option", "two words", "dir/report", "naïve", "x" * 101],
    ids=[
        "empty",
        "leading dot",
        "leading dash",
        "space",
        "slash",
        "letter outside ascii",
        "over a hundred characters",
    ],
)
def test_archive_name_refuses_anything_outside_its_rules(value):
    with pytest.raises(ValidationError):
        ArchiveName.model_validate(value)


def test_an_unnamed_archive_is_named_after_the_time_it_was_created():
    before = datetime.now(UTC).replace(microsecond=0)
    archive = Archive()
    after = datetime.now(UTC)

    created = datetime.strptime(str(archive.name), "archive-%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    assert before <= created <= after


@pytest.mark.parametrize(
    ("added", "expected"),
    [
        (["foo.txt", "foo.txt"], ["foo.txt", "foo-2.txt"]),
        (["foo", "foo", "foo"], ["foo", "foo-2", "foo-3"]),
        (["foo.tar.gz", "foo.tar.gz"], ["foo.tar.gz", "foo-2.tar.gz"]),
        ([".bashrc", ".bashrc"], [".bashrc", ".bashrc-2"]),
        (["foo-2.txt", "foo-2.txt"], ["foo-2.txt", "foo-2-2.txt"]),
        (["foo.txt", "foo.txt", "foo-2.txt"], ["foo.txt", "foo-2.txt", "foo-2-2.txt"]),
    ],
    ids=[
        "extension",
        "no extension",
        "two extensions",
        "leading dot",
        "already numbered",
        "numbered name taken first",
    ],
)
def test_archive_numbers_a_name_it_already_holds(memory_content, added, expected):
    archive = Archive()

    for value in added:
        archive.add(EntryName.model_validate(value), memory_content(b""))

    assert [str(entry.name) for entry in archive.entries] == expected


@given(names)
def test_archive_keeps_every_file_in_the_order_it_was_added(memory_content, added):
    archive = Archive()
    contents = [memory_content(b"") for _ in added]

    for entry_name, content in zip(added, contents, strict=True):
        archive.add(entry_name, content)

    assert len(archive) == len(added)
    assert [entry.content for entry in archive.entries] == contents


@given(names)
def test_archive_never_holds_two_files_under_one_name(memory_content, added):
    archive = Archive()

    for entry_name in added:
        archive.add(entry_name, memory_content(b""))

    held = [entry.name for entry in archive.entries]
    assert len(set(held)) == len(held)


@given(names)
def test_archive_renames_a_file_only_when_its_name_is_taken(memory_content, added):
    archive = Archive()
    taken, renamed = [], []

    for entry_name in added:
        taken.append(entry_name in archive)
        entry = archive.add(entry_name, memory_content(b""))
        renamed.append(entry.name != entry_name)

    assert renamed == taken


def test_each_archive_gets_a_new_identity():
    first, second = Archive(), Archive()

    assert first.archive_id.id.version == 7
    assert first != second


def test_archive_keeps_its_identity_as_files_are_added(memory_content):
    archive = Archive()
    known = {archive}

    archive.add(EntryName.model_validate("foo.txt"), memory_content(b""))

    assert archive in known
