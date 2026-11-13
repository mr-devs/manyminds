"""Long leads are shown in full: each lead is a box that grows to fit its text."""

from nicegui import ui
from nicegui.testing import User

from support import RecordingModel

LONG_LEAD = (
    "Has any named person or organisation in the text confirmed or denied the central "
    "claim, and if so where, when, and in what exact words did they do it?"
)


async def test_each_lead_is_edited_in_a_box_that_grows_with_its_text(
    user: User, model: RecordingModel
) -> None:
    model.leads = [LONG_LEAD, "Short lead"]
    await user.open("/")
    user.find(marker="composer").type("The bridge opened in 1932.")
    user.find("Generate leads").click()
    await user.should_see(marker="lead-list")

    for row in ("lead-row-0", "lead-row-1"):
        with user.scope(marker=row):
            (box,) = user.find(kind=ui.textarea).elements
            assert box.props.get("autogrow") is True
    with user.scope(marker="lead-row-0"):
        await user.should_see(kind=ui.textarea, content=LONG_LEAD)
