"""Images attached to a message: kept with it, looked at, and read as part of what was said."""

import pytest

from manyminds.core.checks import CheckService
from manyminds.core.errors import ModelError
from manyminds.core.jobs import JobManager
from manyminds.core.models import ErrorKind, ImageFile, JobEventKind, MessageRole
from manyminds.core.ports import PastTurn
from manyminds.core.storage import Store
from support import RecordingModel

TEXT = "Is this screenshot real?"
PNG = ImageFile("image/png", b"\x89PNG-one")
JPEG = ImageFile("image/jpeg", b"\xff\xd8-two")
NOTE = (
    "[Attached image {n}, as described by a model that looked at it (the description may be "
    "wrong): {said}]"
)


async def test_attached_images_are_kept_with_the_message_and_described(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.image_description = "A chat screenshot dated 3 May."

    check = service.start_check(TEXT, images=[PNG, JPEG])
    await jobs.wait_until_idle()

    said = store.list_messages(check.id)[0]
    kept = store.list_attachments(said.id)
    assert [(a.media_type, a.data, a.description) for a in kept] == [
        ("image/png", b"\x89PNG-one", "A chat screenshot dated 3 May."),
        ("image/jpeg", b"\xff\xd8-two", "A chat screenshot dated 3 May."),
    ]
    assert model.image_calls == [
        ("image/png", b"\x89PNG-one", "vendor/fast-model"),
        ("image/jpeg", b"\xff\xd8-two", "vendor/fast-model"),
    ]


async def test_leads_are_written_from_the_text_and_what_the_images_show(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.image_description = "A chat screenshot dated 3 May."

    check = service.start_check(TEXT, images=[PNG])
    await jobs.wait_until_idle()

    assert model.decompose_calls[0]["text"] == (
        TEXT + "\n\n" + NOTE.format(n=1, said="A chat screenshot dated 3 May.")
    )
    reply = store.list_messages(check.id)[1]
    assert [(s.kind, s.detail) for s in store.list_message_steps(reply.id)] == [
        (JobEventKind.NOTE, "Looking at attached image 1")
    ]


async def test_an_image_alone_is_enough_to_start_a_check(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.hold_decompose = True

    check = service.start_check("", images=[PNG])

    assert store.get_check(check.id).title == "Image"
    model.release_decompose()
    await jobs.wait_until_idle()
    assert model.decompose_calls[0]["text"] == NOTE.format(n=1, said="A described image.")
    assert len(store.list_leads(check.id)) == 2


async def test_an_image_that_cannot_be_looked_at_is_said_so_and_leads_are_still_written(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.image_error = ModelError(ErrorKind.PROVIDER, "This model does not accept images.")

    check = service.start_check(TEXT, images=[PNG])
    await jobs.wait_until_idle()

    assert model.decompose_calls[0]["text"] == (
        TEXT + "\n\n[Attached image 1 could not be looked at.]"
    )
    assert store.list_attachments(store.list_messages(check.id)[0].id)[0].description is None
    assert len(store.list_leads(check.id)) == 2


async def test_trying_again_does_not_look_at_an_image_twice(
    service: CheckService, model: RecordingModel, jobs: JobManager
) -> None:
    model.decompose_error = ModelError(ErrorKind.RATE_LIMIT, "Too many requests.")
    check = service.start_check(TEXT, images=[PNG])
    await jobs.wait_until_idle()
    model.decompose_error = None

    service.regenerate(check.id)
    await jobs.wait_until_idle()

    assert len(model.image_calls) == 1
    assert "A described image." in model.decompose_calls[1]["text"]


async def test_an_image_sent_later_is_read_by_the_reply_and_remembered(
    service: CheckService, store: Store, model: RecordingModel, jobs: JobManager
) -> None:
    model.leads = ["Lead A"]
    check = await service.create_check(TEXT)
    model.image_description = "A receipt for 40 euros."
    model.proposed = ["The receipt is genuine."]

    await service.send(check.id, "And this one?", images=[JPEG])
    await service.send(check.id, "Thanks.")

    seen = "And this one?\n\n" + NOTE.format(n=1, said="A receipt for 40 euros.")
    assert model.converse_calls[0]["message"] == seen
    assert PastTurn(MessageRole.USER, seen) in model.converse_calls[1]["context"].turns

    proposed = store.list_leads(check.id)[1]
    service.launch_lead(proposed.id, ["vendor/model-a"])
    await jobs.wait_until_idle()
    assert model.research_calls[0]["source_text"] == TEXT + "\n\n" + seen


async def test_a_message_with_only_an_image_can_be_sent(
    service: CheckService, store: Store, model: RecordingModel
) -> None:
    check = await service.create_check(TEXT)

    reply = await service.send(check.id, "  ", images=[PNG])

    assert reply.body == "A reply"
    assert model.converse_calls[0]["message"] == NOTE.format(n=1, said="A described image.")


@pytest.mark.parametrize(
    ("images", "problem"),
    [
        ([PNG] * 5, "Attach at most 4 images to a message."),
        ([ImageFile("image/png", b"x" * (5 * 1024 * 1024 + 1))], "An image can be 5 MB at most."),
        ([ImageFile("image/svg+xml", b"<svg/>")], "Only PNG, JPEG, WebP and GIF images"),
        ([ImageFile("image/png", b"")], "An attached image is empty."),
    ],
)
async def test_images_that_cannot_be_taken_are_refused_before_anything_is_saved(
    service: CheckService, store: Store, images: list[ImageFile], problem: str
) -> None:
    with pytest.raises(ValueError, match=problem):
        service.start_check(TEXT, images=images)

    assert store.list_checks() == []


async def test_deleting_a_check_removes_its_images(
    service: CheckService, store: Store, jobs: JobManager
) -> None:
    check = service.start_check(TEXT, images=[PNG])
    await jobs.wait_until_idle()
    said = store.list_messages(check.id)[0]

    service.delete_check(check.id)

    assert store.list_attachments(said.id) == []
