# 19. Understanding what was shared: unopened links and images

- Status: Accepted
- Date: 2026-11-12
- Changes: the "held to the linked sites" rule of decision 17, for links that fail to open

## Context

An X link gave generic leads: the post would not open, so the lead generator saw only its
address. A research thread later found the post through a public mirror, using the ordinary
page-opening tool, but could not look at its images, because that tool returns text only.
The owner decided that the first step should do its best to understand what was pasted,
using only what OpenRouter offers and without relying on any named mirror.

A live trial showed that a model given an image's address as an image input describes it
correctly, for about a hundredth of a cent.

## Decision

Before leads are written (and before a chat reply, for links in the new message):

1. **Open the linked pages**, held to the linked sites, as before.
2. **If a link will not open, look for it another way.** One further call may search and open
   up to three pages anywhere, and is told to find a mirror, an archive, an embed or coverage
   that reproduces the material. No mirror is named in the code. This call is given **only
   the addresses** that failed, never what the user wrote. If it fails, leads are written
   without it.
3. **Look at the images.** Image addresses in the user's text and on the opened pages (up to
   four; profile pictures and icons are skipped) are each sent to the model as an image, with
   instructions to describe only what is visible, copy visible text, and not name people from
   their appearance. An image that cannot be shown to the model is noted and skipped.
4. **Say what was read.** The opening reply lists what was opened, what could not be, and
   each image's description, as plain text, so the user can see and correct the app's
   understanding.

Research agents are told to do the same kind of thing: find another way into a page that
will not open, and follow a video or image to where it was first published.

## How a model's reading of an image is kept from becoming a finding

- A description steers **what is looked for**. It cannot be **evidence**: every evidence item
  in a report must still be a quoted passage from a page the search or fetch tool returned,
  and is flagged when it is not.
- Research agents receive the descriptions labelled as a model's reading that may be wrong
  and is not evidence.
- The user sees every description above the leads.

## Consequences

- The call in step 2 can be steered by a hostile page into opening an address of its
  choosing. It holds nothing of the user's but the failed links, so there is little for such
  an address to carry.
- Image addresses taken from a page are fetched by the model provider.
- **Cost.** A link that opens costs about a tenth of a cent before leads. The trial X link,
  which needed step 2 and had four images, cost about five cents.
- Video is not watched. A video's still frame is looked at when its address appears as an
  image. Reverse image search is not available through OpenRouter.
- Models that do not accept images simply produce "could not be looked at".
