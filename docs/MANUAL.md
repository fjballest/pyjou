# DayJournal user manual

## Opening a journal

At start DayJournal opens the journal used last. The first time, it opens
the first `DayJournal*` directory in `/u/trade` (or `~/u/trade`). **Open**
picks another directory, and its drop down lists the recent journals and
the ones found there.

Images are found by their names: `day261014.png` for a day,
`day261014b.png` for another chart of that day, and `day261011weekprof.png`
for the week that starts on Sunday 11. Other files are left alone. New
images are picked up as they are saved into the directory; **Reload** (⌘R,
F5 elsewhere) looks again.

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

Words match whole words, ignoring case. A final lowercase `s` is optional,
so `EQL` finds *EQLs*, and `*` matches any letters within a word: `EQ*`
finds *EQL*, *EQH* and *EQLs*. A wrong search turns red and its tooltip
says why. Esc empties the box. **Days** and **Weeks** choose which kind of
image is listed.

## The list

The list groups the images by year, month and week (weeks start on Sunday,
as the week profiles do). Click a group, or use ←/→ on it, to open or close
it. The small triangle above the list opens all the groups, or closes them
all when some are open. At start only the last year, month and week are
open, and the week before too when the last one has a single day. Moving to
an image opens its groups, and a search opens the groups of what it finds.
A week that spans two months shows up in both, with the days of each.

## Moving around

- Click an image in the list, or use ↑/↓ there.
- With the image focused (click it): ←/→ or ↑/↓ for the previous or next
  image, Home/End for the first or last, W for the week or day.
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

## Notes

Write under the image. Notes are saved as you type, in a file with the
image's name and a `.txt` extension (`day261014.txt`). Emptying the notes
removes the file. Images with notes have a ✎ in the list, and their notes
show in its tooltip.
