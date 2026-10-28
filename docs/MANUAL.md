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

- At first the date is the day the file was last changed. Meanwhile the OCR
  reads the dates written in the image (`mié 26-10-14`, `14/10/2026`,
  `29 sept 2026`...), and when it is done it proposes the last one that
  isn't after the day the file was changed (charts show the days before
  too), or that day when all of them are after it. If the image has a
  Sunday and the Friday after it, it is taken as the week profile of that
  Sunday.
- **Week profile** starts checked when the date proposed is a Saturday or
  Sunday (the profile is then named on that Sunday), and unchecked for any
  other day. Check or uncheck it to change it; a week profile is named on
  the Sunday before its week.
- **Dates found** lists the date proposed first, then the other dates in
  the image, in the order they were found (and how many times), and the day
  the file was changed. Pick
  one to use it, or set the date by hand. Picking one sets **Week profile**
  the same way; you can still change the box afterwards.
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

Right click an image in the list for **Cut**, **Copy** and **Paste**
(⌘X, ⌘C and ⌘V work too while the list has the focus). Copy an image, open
another journal (or keep this one) and paste: the image is copied there with
its notes, drawings and tags, keeping its date. It gets the next name free
for that date (`day261014b.png` when `day261014.png` is there), so nothing
is overwritten. Cut works the same, but the image leaves its journal when it
is pasted, and is shown in gray until then; pasting it in its own journal
does nothing. Paste also works between two DayJournal windows, and pasting
image files copied in the Finder adds them as captures.

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
and **Zoom +**/**Zoom −** zoom. On a trackpad, a double tap with two
fingers zooms in, zooms in again, and fits again, keeping the point tapped
in place, and pinching zooms in and out. Drag to move around. **View ▸ Open
in Preview** opens it with the system viewer.

The **List** and **Notes** buttons, at the left of the toolbar (**View ▸ Show List**, ⇧⌘L, and **View ▸
Show Notes**, ⇧⌘N) hide and show the panel on the left (the search, the
list and the calendar) and the tags and notes under the image, so the image
gets the room. The window remembers them. **Search** (⌘F) and **Edit
Notes** (⌘N) show their panel again.

## Drawing

The buttons above the image, on the left, draw on it: **Pencil** (free hand), **Line**,
**Arrow**, **Circle**, **Rect**, **Text** and **Fib**. Pick one and drag on the image (for
Text, click where the box goes and type; click elsewhere or press Esc when
done). Hold Shift while placing the end of a line or an arrow to keep it
horizontal or vertical. With the image focused the keys S, P, L, A, C, R,
T and F pick the tools too.

**Line**, **Arrow** and **Circle** open a window when you double click
them, to change their **Color**, **Width** and **Style** (solid, dashed,
dotted) and give them a **Label**, with its **Text size** and **Label
color**. The label goes **Above**, **Center** (across it; the line stops
around the label) or **Below**, and **Left** (at its left end), **Center**
(in its middle) or **Right**. For lines and arrows, **Right** puts the label
past the right end of the line, kept inside the image.

**Rect** draws a rectangle, just its border at first. Double click its
border (anywhere on it once filled) to set:

- **Fill**, with its color and **Transparency** (0% hides what is under it);
- **Line across the middle**, dashed, with its color;
- **Label** (FVG, OB...), aligned **Center**, **Left** or **Right**, written
  across the middle of the rectangle (the middle line stops around it), with
  its **Label color**.

The arrow next to **Rect** picks the kind of rectangle to draw: **Plain**
(just the border, in the drawing color) or one already set up, with its
colors, fill, middle line and label:

| Kind | Looks like |
|------|------------|
| BRK | green border and fill, green middle line |
| MB | green border and fill, green middle line |
| FVG | black border, light orange fill, black middle line |
| IFVG+ | orange border and fill, red middle line |
| IFVG- | blue border, light cyan fill, black middle line |

Picking a kind with rectangles selected changes them to it instead.

In these windows the drawing shows each change at once; **Cancel** puts it
back as it was.


**Fib** draws Fibonacci levels. Press on the first point (level 1) and drag
to the second one (level 0), or click one and then the other. Then move the
mouse and click where the lines end, or double click on the second point to
take them to the right edge of the image. While you draw it, a dashed line
shows where the second point (level 0) is. Esc or the right button drops a
fib not finished. Each level has its number just past the right end of its
line, centered on it; lines taken to the edge of the image stop short of it
to leave room for the numbers.
The arrow next to **Fib** picks the levels:

| Set | Levels |
|-----|--------|
| OTE (the default) | 0.5, 0.62, 0.705, 0.79 |
| Quadrants | 0, 0.25, 0.5, 0.75, 1 |
| PO3 | the quadrants and −0.5, −1, −1.5, −2, −2.5, 1.5, 2, 2.5, 3, 3.5 |
| Custom… | a form with 20 levels in two columns: check the ones to draw and type their values |

The custom form starts with all the levels above, and two blank ones, and
remembers what you set. Its **Draw the diagonal** box adds the dashed line
from the first point to the second; the other sets never draw it. Picking a
set with fibs selected changes their levels instead.

The **⧉** button at the start of the drawing buttons detaches them as a
small floating bar that stays on top of every window, so you can keep it
where it suits you. Click **⧉** again, or close the bar, to put it back.

**Select** (the usual tool) clicks a drawing to select it, drags it to move
it, and Del or **Delete** removes the ones selected. Shift-click selects
more than one. Double click a text box to change its text; emptying it
removes it. Dragging the image itself moves around it, as before.

The color button, the width list, the line style list (solid, dashed,
dotted) and the text size list (**Aa 16** by default, for text boxes, labels
and fib numbers) set how new drawings look, and change the ones selected.
**Clear** deletes every drawing on the image; **Undo** brings them back. **Undo** and **Redo** (⌘Z, ⇧⌘Z) undo and redo the
drawing changes of the image shown.

Drawings are kept until you **Save** them (⌘S, or the Save button in the
toolbar); meanwhile the window title says *(unsaved)*. You can go to other
images and draw there too before saving, and Save writes them all.
Quitting or opening another journal with unsaved drawings asks whether to
save them. They go in a file with the image's name and a `.drw` extension
(`day261014.drw`), and saving an image without drawings removes its file.
Notes are still saved as you type.

Drawings are kept in image coordinates, so they stay in place when zooming.
The words in the text boxes and labels are found by the search, as the notes are.

## Notes

Write under the image. Notes are saved as you type, in a file with the
image's name and a `.txt` extension (`day261014.txt`). Emptying the notes
removes the file. Images with notes have a ✎ in the list, and their notes
show in its tooltip.
