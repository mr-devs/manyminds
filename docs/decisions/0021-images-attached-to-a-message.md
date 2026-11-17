# 21. Images can be attached to a message

- Status: Accepted
- Date: 2026-11-12

## Context

Images could only be given by a public web address. A screenshot, the most common thing a
person wants checked, could not be given at all. The owner asked for pasting an image into
the box and for an ordinary attach button.

## Decision

- An image can be **pasted** into the message box or picked with an **attach button**, on the
  home page and in the conversation. Both routes hand the file to one hidden uploader. Up to
  four images a message, 5 MB each, PNG, JPEG, WebP or GIF. A message may be an image alone.
- Images are **kept with the message** in the database (`attachments`, schema version 5) and
  shown in the conversation. Deleting the check deletes them.
- Before the leads or a reply are written, each image is **shown to the model itself** (the
  bytes are sent, as a data address) and described under the same instructions as linked
  images (decision 19). The description is saved and shown under the image as "Read as: …".
- Everything downstream is given the user's words and, **apart from them**, what each image
  was said to show, labelled as a model's reading that may be wrong. A description is never
  placed inside what the user said: words or an address visible in an image must not be
  taken for a request or a link of the user's, so nothing in an image is opened or obeyed.
  No call other than the describing one receives the image.
- An image that cannot be described is said to be so, and the work goes on.

## Consequences

- Attached images are sent to OpenRouter and the model's provider. They are not sent to the
  search engine. The README says so.
- Research agents work from the description, not the picture, so they cannot match the image
  itself against the web. Reverse image search is still unavailable through OpenRouter.
- The database grows with each image.
- Two small pieces of fixed browser-side code are involved: one opens the file picker on the
  button's click, one passes pasted image files to the uploader. Neither handles model text.
- Pasting and the file picker happen in the browser, so they are checked by hand; the tests
  cover everything from the uploader onwards.
