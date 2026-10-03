from datetime import UTC, datetime
from uuid import uuid4, uuid7

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from satara.domain import (
    AllFilesReceived,
    Archive,
    ArchiveID,
    ArchiveName,
    ArchiveStatus,
    EntryName,
)

# A small pool makes collisions, and collisions with generated names, common. The pool spells
# some names in two cases or two Unicode forms; escapes show the forms apart.
pooled_names = st.builds(
    lambda stem, extensions: stem + extensions,
    st.sampled_from(
        ["foo", "Foo", "foo-2", "FOO-2", "bar", ".bashrc", "caf\u00e9", "cafe\u0301"]
    ),
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


@given(st.tuples(st.text(), st.characters(categories=["Cc"]), st.text()).map("".join))
def test_entry_name_refuses_a_name_holding_a_control_character(value):
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
        (["Report.txt", "report.txt"], ["Report.txt", "report-2.txt"]),
        (["caf\u00e9.txt", "cafe\u0301.txt"], ["caf\u00e9.txt", "cafe\u0301-2.txt"]),
        (["a.txt", "A-2.txt", "A.txt"], ["a.txt", "A-2.txt", "A-3.txt"]),
    ],
    ids=[
        "extension",
        "no extension",
        "two extensions",
        "leading dot",
        "already numbered",
        "numbered name taken first",
        "differing in case",
        "differing in Unicode form",
        "numbered name differing in case",
    ],
)
def test_archive_numbers_a_name_it_already_holds(memory_content, added, expected):
    archive = Archive()

    for value in added:
        archive.add(EntryName.model_validate(value), 0, memory_content(b""))

    assert [str(entry.name) for entry in archive.entries] == expected


@given(names)
def test_archive_keeps_every_file_in_the_order_it_was_added(memory_content, added):
    archive = Archive()
    contents = [memory_content(b"") for _ in added]

    for entry_name, content in zip(added, contents, strict=True):
        archive.add(entry_name, 0, content)

    assert len(archive) == len(added)
    assert [entry.content for entry in archive.entries] == contents


@given(names)
def test_archive_never_holds_two_files_under_one_name(memory_content, added):
    archive = Archive()

    for entry_name in added:
        archive.add(entry_name, 0, memory_content(b""))

    held = [entry.name.folded for entry in archive.entries]
    assert len(set(held)) == len(held)


@given(names)
def test_archive_renames_a_file_only_when_its_name_is_taken(memory_content, added):
    archive = Archive()
    taken, renamed = [], []

    for entry_name in added:
        taken.append(entry_name in archive)
        entry = archive.add(entry_name, 0, memory_content(b""))
        renamed.append(entry.name != entry_name)

    assert renamed == taken


@pytest.mark.parametrize("value", [uuid7(), str(uuid7())], ids=["a UUID", "its text"])
def test_archive_ID_accepts_a_version_7_UUID_or_its_text(value):
    archive_id = ArchiveID.model_validate(value)

    assert str(archive_id) == str(value)


@pytest.mark.parametrize(
    "value",
    # A bare number is refused before it reaches the ID's own validation, so it goes in a dict.
    [{"id": 7}, "not a UUID", str(uuid4())],
    ids=["neither a UUID nor text", "text that is no UUID", "a version 4 UUID"],
)
def test_archive_ID_refuses_anything_but_a_version_7_UUID(value):
    with pytest.raises(ValidationError):
        ArchiveID.model_validate(value)


def test_each_archive_gets_a_new_identity():
    first, second = Archive(), Archive()

    assert first.archive_id.id.version == 7
    assert first != second


def test_archive_keeps_its_identity_as_files_are_added(memory_content):
    archive = Archive()
    known = {archive}

    archive.add(EntryName.model_validate("foo.txt"), 0, memory_content(b""))

    assert archive in known


@pytest.fixture
def archive_of_two(memory_content):
    archive = Archive()
    archive.add(EntryName.model_validate("a.txt"), 1, memory_content(b"a"))
    archive.add(EntryName.model_validate("b.txt"), 1, memory_content(b"b"))
    return archive


def summarise(events):
    return [(type(event), event.archive_id) for event in events]


def test_archive_records_that_all_files_were_received_once_each_has_arrived(archive_of_two):
    archive_of_two.receive(EntryName.model_validate("a.txt"))
    archive_of_two.receive(EntryName.model_validate("B.TXT"))

    archive_of_two.check_complete()

    events = archive_of_two.pull_events()
    assert summarise(events) == [(AllFilesReceived, archive_of_two.archive_id)]


def test_archive_records_nothing_while_a_file_is_missing(archive_of_two):
    archive_of_two.receive(EntryName.model_validate("a.txt"))

    archive_of_two.check_complete()

    assert archive_of_two.pull_events() == []


def test_archive_records_nothing_once_it_is_built(archive_of_two):
    for entry in archive_of_two.entries:
        archive_of_two.receive(entry.name)
    archive_of_two.mark_built()

    archive_of_two.check_complete()

    assert archive_of_two.pull_events() == []


def test_archive_hands_out_each_recorded_event_once(archive_of_two):
    for entry in archive_of_two.entries:
        archive_of_two.receive(entry.name)
    archive_of_two.check_complete()
    archive_of_two.pull_events()

    events = archive_of_two.pull_events()

    assert events == []


def test_archive_refuses_to_receive_a_file_it_does_not_hold(archive_of_two):
    with pytest.raises(KeyError):
        archive_of_two.receive(EntryName.model_validate("c.txt"))


def test_archive_lists_the_files_received_in_the_order_they_were_added(archive_of_two):
    archive_of_two.receive(EntryName.model_validate("b.txt"))
    archive_of_two.receive(EntryName.model_validate("a.txt"))

    received = archive_of_two.received

    assert [str(entry.name) for entry in received] == ["a.txt", "b.txt"]


def test_archive_is_pending_until_built_and_ready_after(archive_of_two):
    before = archive_of_two.status

    archive_of_two.mark_built()

    assert (before, archive_of_two.status) == (ArchiveStatus.PENDING, ArchiveStatus.READY)


def test_archive_is_failed_once_its_build_has_failed(archive_of_two):
    archive_of_two.mark_failed()

    status = archive_of_two.status

    assert status == ArchiveStatus.FAILED


def test_archive_is_ready_once_built_even_after_a_failed_build(archive_of_two):
    archive_of_two.mark_failed()

    archive_of_two.mark_built()

    assert archive_of_two.status == ArchiveStatus.READY


def test_archive_records_that_all_files_were_received_after_a_failed_build(archive_of_two):
    """Records the event again, so a later attempt can still build the archive."""
    for entry in archive_of_two.entries:
        archive_of_two.receive(entry.name)
    archive_of_two.mark_failed()

    archive_of_two.check_complete()

    events = archive_of_two.pull_events()
    assert summarise(events) == [(AllFilesReceived, archive_of_two.archive_id)]
