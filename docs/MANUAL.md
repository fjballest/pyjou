# DayJournal user manual

DayJournal browses a day journal: a directory with snapshots of day and
week charts. It reads the words written on each image to make tags you can
search, keeps notes for each image, and lets you draw on them. See
[DESIGN.md](DESIGN.md) for how it is built.

## Opening a journal

At start DayJournal opens the journal used last. The first time, it opens
the first `DayJournal*` directory in `/u/trade` (or `~/u/trade`). **Open**
picks another directory, and its drop down lists the recent journals and
the ones found there.

Images are found by their names: `day261014.png` for a day,
`day261014b.png` for another chart of that day, and `day261011weekprof.png`
for a week profile. A week profile dated a Sunday (11 Oct) is for the week
that starts the next day (Monday 12 Oct); one dated another day is for the
week of that day. Other files are left alone. New images are picked up as
they are saved into the directory; **Reload** (⌘R, F5 elsewhere) looks again.

## Adding captures

Drop a capture (a PNG, JPEG or other image) anywhere on the window, or use
**File ▸ Add Capture…** (⌘I), to add it to the journal. A window shows the
capture and asks for its date:

- At first the date is the day the file was made. Meanwhile the OCR reads
  the dates written in the image (`mié 26-10-14`, `14/10/2026`,
  `29 sept 2026`...), and when it is done it proposes the last day in the
  image that is not after the day the file was made: charts show the
  days before too.
- **Dates found** lists every date considered, those in the image (and how
  many times), one in the file name, and the file's own date. Pick one to
  use it, or set the date by hand. Picking a Saturday or Sunday checks
  **Week profile** (named on that Sunday), and picking another day unchecks
  it; you can still change the box afterwards.
- Captures made on a Saturday or Sunday are taken as week profiles, named on
  that Sunday. Check or uncheck **Week profile** to change it; a week
  profile is named on the Sunday before its week.
- **Saved as** shows the name it gets: the first capture of a day is
  `day261014.png`, and the next ones `day261014b.png`, `day261014c.png`...
  Nothing already in the journal is replaced.

**Add** copies the capture into the journal with that name (as PNG if it was
another format), keeps what the OCR read as its tags, and shows it. The
dropped file is left where it was. Dropping several captures asks for each
one in turn.

## Tags

The first time an image is seen, DayJournal reads its text with OCR in the
background; the status bar shows how many are left. This takes a few
seconds per image, and only happens once: the results are kept in
`.pyjou-tags.json` in the journal directory. An image that changes on disk
is read again.

Of the text read, the tags are what looks like words. Prices, numbers,
dates, short Spanish and English words (*de*, *en*, *the*), letters with no
vowels and other OCR noise are dropped; trading terms in capitals (*RTHOG*,
*SMT*, *ES*) and time frames (*m15*) are kept. The tags show under the
image; click one to search for it.

**Edit ▸ Read Tags Again** (⌘T) reads the image shown again, and **Read All Tags
Again** all of them.

## Searching

Type in the search box to show only the images whose tags or notes match:

| Search | Images shown |
|--------|--------------|
| `judas swing` | with both words |
| `judas \| silver` | with either word |
| `!judas` | without the word |
| `(silver bullet) \| !(EQL EQH)` | parentheses group |

Words match tags and whole words of the notes and of the text boxes drawn,
ignoring case. A final lowercase `s` is optional, so `EQL` finds *EQLs*, and `*` matches any letters within a word: `EQ*`
finds *EQL*, *EQH* and *EQLs*. A wrong search turns red and its tooltip
says why. Esc empties the box. **Days** and **Weeks** choose which kind of
image is listed.

## The list

The list groups the images by year, month and week. Weeks start on Monday,
and each week profile is listed first in the week it is for. Click a
group, or use ←/→ on it, to open or close it. The small triangle above the list opens all the groups, or closes them
all when some are open. At start only the last year, month and week are
open, and the week before too when the last one has a single day. Moving to
an image opens its groups, and a search opens the groups of what it finds.
A week that spans two months shows up in both, with the days of each.

Double click an image in the list to change its date, or whether it is a
week profile. The window is the one used when adding captures, titled
*Change Date*, with the dates read in the image. **Change** renames the
image, with its notes, drawings and tags, to the name shown in **Saved
as**; keeping the date keeps the name.

## Moving around

- Click an image in the list, or use ↑/↓ there.
- With the image focused (click it): ←/→ or ↑/↓ for the previous or next
  image, Home/End for the first or last, W for the week or day. While
  writing in a text box the keys go to the text.
- PgUp/PgDown anywhere for the previous or next image, ⌘Home/⌘End for the
  first and last.
- **Week** (⌘W) goes from a day to the profile of its week, and back to
  the first day of the week.
- Click a day in the calendar to see it. Days with images are in bold
  blue, and the ones the search hides are grey; a day without an image
  goes to the next one that has one.

Searching, the arrows and the calendar move through the images listed.

## The image

**Fit** fits the image in the window, **Real Size** shows it at its size,
and **Zoom +**/**Zoom −** zoom. Double clicks zoom in, zoom in again, and
fit again. Drag to move around. **View ▸ Open in Preview** opens it with
the system viewer.

## Drawing

The buttons above the image draw on it: **Pencil** (free hand), **Line**,
**Arrow**, **Circle**, **Rect**, **Text** and **Fib**. Pick one and drag on the image (for
Text, click where the box goes and type; click elsewhere or press Esc when
done). Hold Shift while placing the end of a line or an arrow to keep it
horizontal or vertical. With the image focused the keys S, P, L, A, C, R,
T and F pick the tools too.

**Rect** draws a rectangle, just its border at first. Double click its
border (anywhere on it once filled) to set:

- **Fill**, with its color and **Transparency** (0% hides what is under it);
- **Line across the middle**, dashed;
- **Label** (FVG, OB...), aligned **Center**, **Left** or **Right**, written
  inside the top of the rectangle, or above it when it is too low.


**Fib** draws Fibonacci levels. Press on the first point (level 1) and drag
to the second one (level 0), or click one and then the other. Then move the
mouse and click where the lines end, or double click on the second point to
take them to the right edge of the image. Esc drops a fib not finished. The
arrow next to **Fib** picks the levels:

| Set | Levels |
|-----|--------|
| OTE (the default) | 0.5, 0.62, 0.705, 0.79 |
| Quadrants | 0, 0.25, 0.5, 0.75, 1 |
| PO3 | the quadrants and −0.5, −1, −1.5, −2, −2.5, 1.5, 2, 2.5, 3, 3.5 |
| Custom… | asks for the levels, starting with all the above; they are remembered |

Picking a set with fibs selected changes their levels instead.

**Select** (the usual tool) clicks a drawing to select it, drags it to move
it, and Del or **Delete** removes the ones selected. Shift-click selects
more than one. Double click a text box to change its text; emptying it
removes it. Dragging the image itself moves around it, as before.

The color button and the width list set how new drawings look, and change
the ones selected. **Undo** and **Redo** (⌘Z, ⇧⌘Z) undo and redo the
drawing changes of the image shown.

Drawings are kept until you **Save** them (⌘S, or the Save button in the
toolbar); meanwhile the window title says *(unsaved)*. You can go to other
images and draw there too before saving, and Save writes them all.
Quitting or opening another journal with unsaved drawings asks whether to
save them. They go in a file with the image's name and a `.drw` extension
(`day261014.drw`), and saving an image without drawings removes its file.
Notes are still saved as you type.

Drawings are kept in image coordinates, so they stay in place when zooming.
The words in the text boxes and rectangle labels are found by the search, as the notes are.

## Notes

Write under the image. Notes are saved as you type, in a file with the
image's name and a `.txt` extension (`day261014.txt`). Emptying the notes
removes the file. Images with notes have a ✎ in the list, and their notes
show in its tooltip.
