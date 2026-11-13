"""Attaching images to a message, from the home page and in the conversation."""

from nicegui import ElementFilter, ui
from nicegui.testing import User

from manyminds.core.services import Services
from support import RecordingModel

TEXT = "Is this screenshot real?"
PNG = b"\x89PNG-one"


async def attach(user: User, name: str, media_type: str, data: bytes) -> None:
    """Hand a file to the page's uploader, as the browser does after one is picked or pasted."""
    with user:
        (box,) = list(ElementFilter(kind=ui.upload))
        await box.handle_uploads([ui.upload.SmallFileUpload(name, media_type, data)])


def pictures(user: User) -> list[str]:
    with user:
        return [str(image.source) for image in ElementFilter(kind=ui.image)]


async def test_an_attached_image_waits_by_the_box_and_goes_with_the_message(
    user: User, model: RecordingModel, services: Services
) -> None:
    model.image_description = "A chat screenshot dated 3 May."
    await user.open("/")
    await user.should_see("Attach an image")

    await attach(user, "shot.png", "image/png", PNG)
    await user.should_see(marker="attachment-0")
    user.find(marker="composer").type(TEXT)
    user.find("Generate leads").click()

    await user.should_see(marker="lead-list")
    await user.should_see("Read as: A chat screenshot dated 3 May.")
    assert pictures(user) == ["data:image/png;base64,iVBORy1vbmU="]  # base64 of the bytes
    assert model.image_calls == [("image/png", PNG, "vendor/fast-model")]


async def test_an_image_alone_can_be_sent_from_the_home_page(
    user: User, model: RecordingModel
) -> None:
    await user.open("/")

    await attach(user, "shot.png", "image/png", PNG)
    await user.should_see(marker="attachment-0")  # the upload is handled in the background
    user.find("Generate leads").click()

    await user.should_see(marker="lead-list")
    assert len(pictures(user)) == 1


async def test_an_attached_image_can_be_taken_off_before_sending(
    user: User, model: RecordingModel
) -> None:
    await user.open("/")
    await attach(user, "shot.png", "image/png", PNG)
    await user.should_see(marker="attachment-0")

    user.find(marker="remove-attachment-0").click()
    await user.should_not_see(marker="attachment-0")
    user.find(marker="composer").type(TEXT)
    user.find("Generate leads").click()

    await user.should_see(marker="lead-list")
    assert model.image_calls == []
    assert pictures(user) == []


async def test_a_file_that_is_not_an_image_is_refused_with_a_reason(user: User) -> None:
    await user.open("/")

    await attach(user, "notes.pdf", "application/pdf", b"%PDF")

    await user.should_see("Only PNG, JPEG, WebP and GIF images can be attached.")
    await user.should_not_see(marker="attachment-0")


async def test_a_fifth_image_is_refused(user: User) -> None:
    await user.open("/")
    for n in range(4):
        await attach(user, f"{n}.png", "image/png", PNG)
        await user.should_see(marker=f"attachment-{n}")

    await attach(user, "4.png", "image/png", PNG)

    await user.should_see("Attach at most 4 images to a message.")
    await user.should_not_see(marker="attachment-4")


async def test_an_image_can_be_sent_in_the_conversation_without_any_words(
    user: User, model: RecordingModel
) -> None:
    await user.open("/")
    user.find(marker="composer").type(TEXT)
    user.find("Generate leads").click()
    await user.should_see(marker="lead-list")
    model.image_description = "A receipt for 40 euros."

    await attach(user, "receipt.jpg", "image/jpeg", b"\xff\xd8-two")
    await user.should_see(marker="attachment-0")
    user.find("Send").click()

    await user.should_see(marker="reply", content="A reply")
    await user.should_see("Read as: A receipt for 40 euros.")
    await user.should_not_see(marker="attachment-0")
    assert model.converse_images[0] == ["A receipt for 40 euros."]


async def test_a_file_name_with_markup_is_shown_as_plain_text(user: User) -> None:
    await user.open("/")

    await attach(user, "<img src=x onerror=alert(1)>.png", "image/png", PNG)

    await user.should_see(kind=ui.label, content="<img src=x onerror=alert(1)>.png")
