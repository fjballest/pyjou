# DayJournal user manual

DayJournal browses a day journal: a directory with snapshots of day and
week charts. It reads the words written on each image to make tags you can
search, keeps notes for each image, and lets you draw on them. See
[DESIGN.md](DESIGN.md) for how it is built.

## Opening a journal

At start DayJournal opens the journal used last. The first time, it opens
the first `DayJournal*` directory in `/u/trade` (or `~/u/trade`). When there
is no `/u` or `~/u` directory, it looks in `trade` in your documents directory
(`~/Documents/trade` on macOS, `Documents\trade` on Windows), and in the
documents directory itself. **Open**
picks another directory, and its drop down lists the recent journals and
the ones found there. Journals in temporary directories (`/tmp`, or
`/var/folders` on macOS) are not kept as recent ones.

**File ▸ New Window** (⌥⌘N) opens another window on the same journal and
image. Use it to look at two images at once, or open another journal in it.
Each window has its own search, list and drawings; notes and drawings saved
in one show up in the others on the same journal. **Quit** closes them all.
The **Window** button in the toolbar does the same.

**Window** arranges the windows shown on the screen of the one you are in.
The main window goes first: the one you are in when it shows its list and
calendar, else the first one that does (the windows made with New Window
show only the image):

| Entry | What it does |
|-------|--------------|
| Minimize (⌘M) | minimizes this window |
| Tile (⌥⌘T) | all the windows as a mosaic: two side by side, three with one wide below, four in a 2×2 grid, and so on |
| Side by Side | all the windows in columns |
| Stacked | all the windows in rows |
| Main on the Left | the main window on the left half, the others one over the other on the right |
| Main on Top | the main window on the top half, the others side by side below |
| Cascade | all the windows a bit apart, one over the other |
| Fill the Screen, Left Half, Right Half, Top Half, Bottom Half, Center | this window alone |

At the end it lists the windows shown, to bring one to the front. The
other windows keep more or less their order on the screen. A window that
can't get as small as its place keeps its smallest size and stays on the
screen.

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
  A name left free by a capture you removed is used again before a new
  letter: with `day261014.png` and `day261014c.png` there, the next one is
  `day261014b.png`.
  Nothing already in the journal is replaced, unless you check the box
  below.
- **Replace** (unchecked at first, and only there when the day or week
  already has captures) saves this one as the only capture of that day or
  week profile, `day261014.png`, instead of adding another. The captures
  replaced are deleted with their drawings and tags; their notes go to the
  new one.

**Add** copies the capture into the journal with that name (as PNG if it was
another format), keeps what the OCR read as its tags, and shows it.
Dropping several captures asks for each one in turn.

A file dropped is then moved to the Trash (the Recycle Bin on Windows),
once its copy in the journal is written to the disk and reads back as the
same image, so the Desktop doesn't fill with captures already in the
journal. If the copy can't be checked, or the file can't be moved, it is
left where it was and DayJournal says so. **File ▸ Move Dropped Captures
to Trash** (on at first) turns this off: the dropped files are then left
where they were. Files added with **Add Capture…** and captures dragged
from another DayJournal window are never moved.

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

### Aliases

A word can stand for others too. The file `aliases.txt` in the journal
directory has a line for each word, the word, `:` and its aliases separated
by commas:

```
# news, and the reports that are news
news: NFP, PPI, CPI
FVG: IFVG, gap*
```

Searching `news` then also finds the images with *NFP*, *PPI* or *CPI*;
`!news` hides them all. The word and its aliases match as any search word
does: ignoring case, with an optional final `s` (`NEWS` and `new` use the
same aliases), and `*` within an alias. Aliases go one way only: `CPI`
finds just *CPI*, and a search word with `*` has no aliases. `#` starts a
comment, and a word with several lines gets all of them.

**Edit ▸ Aliases…** edits the file and searches again; you can also edit it
with any text editor, and the window reads it when the journal reloads. All
the windows of a journal share its aliases.

## The list

The list groups the images by year, month and week. Weeks start on Monday,
and each week profile is listed first in the week it is for. Click a
group, or use ←/→ on it, to open or close it. The small triangle above the list opens all the groups, or closes them
all when some are open. At start only the last year, month and week are
open, and the week before too when the last one has a single day. Moving to
an image opens its groups, and a search opens the groups of what it finds.
A week that spans two months shows up in both, with the days of each.

The thin line on the left of the list (and of the data list) has a circle
by each row that opens or closes. Scrolling on it zooms the list there:
scrolling up on a closed group opens it, and on an open one opens the
groups in it; scrolling down closes the groups open in the row, then the
row, then the group it is in. The row under the mouse stays where it is.
The calendar below the list goes to any date.

Weeks are numbered in calendar weeks from the first one in the journal,
which is 1: `5. Week 26 Oct` is the fifth week since then, counting weeks
without images too. Each day is one row. A day with several images shows
them side by side in its row, after the day, as compact names: its letters,
`a` for the first (`day261026.png`), then `b`, `c`... with ✎ on the ones
with notes or drawings, and the one shown highlighted. Click one to show
it, or use ← and → on the row to go along them; hover one to see its name,
notes and tags. Week profiles get a row of their own in the same way, taller, with the
profile of the week drawn at its right (see below). Above the list, the count says how many images are
shown, of how many, and how many weeks have images (`12 of 40, 9 weeks`).

The profile of a week is the line of the swings that frame it: Monday
up, Tuesday down, Wednesday up to the high of the week, Thursday down... It
is found in the week profile's image, a TradingView chart of the week: its
candles, from the dashed blue line where the week starts (Sunday evening)
to the end, with the dotted blue lines between days drawn faintly behind
the profile. Only the swings of about a third of the week's range or more
count. The images are only read, never changed; the profiles found are kept
in `.pyjou-weekprof.json` in the journal, and found again when an image
changes. A chart with other kinds of candles, or the whole screen captured,
may give a wrong profile or none.

**Edit ▸ Adjust Profile…** (⇧⌘R) draws the profile of the week shown
on its image, in red, to fix it by hand: drag a point to move it, click a
segment to add a point there, right click a point to remove it. A double
click (or Return) keeps the result, and Esc leaves the profile as it was. A
profile adjusted by hand is kept even if its image changes; the image
itself is never changed.

**Edit ▸ Match Week…** (⇧⌘M) compares the week shown, usually a week in
progress (a capture of the week so far, from Sunday to now), with the same
days of the other full weeks of the journal, each scaled to its own range so
the size of the moves does not matter. A window lists the closest weeks
first, with how well each matches; click one to show it. While the window
is open, the list shows the score of each week next to its profile, the
part matched drawn in red and the rest, what came after, in the usual
color. Closing the window ends the match.

Beside the triangle, **m** closes the list down to the months, keeping the
last month open with its weeks and the days of its last week, and **w**
closes it down to the weeks, keeping the days of the last week.

Double click an image in the list to change its date, or whether it is a
week profile. The window is the one used when adding captures, titled
*Change Date*, with the dates read in the image. **Change** renames the
image, with its notes, drawings and tags, to the name shown in **Saved
as**; keeping the date keeps the name.

To move an image to another day, drag it from the list to that day in the
calendar (go to another month with the calendar's arrows first). The day
under the image is selected while you drag; dropping renames it, with its
notes, drawings and tags, to the next name free for that day. A week
profile dropped on any day goes to the week of that day, named on the
Sunday before it. Dragging an image to the Finder or to another DayJournal
window copies it there.

To change the order of the images of a day (or of the week profiles of a
week), drag one of its names in the row and drop it before or after another
one: a line shows where it goes. The images of that day are renamed, with
their notes, drawings and tags, to keep the new order with the usual names:
the first `day261014.png`, then `day261014b.png`, `day261014c.png`... with
no letters left out.

Right click an image in the list for **Cut**, **Copy** and **Paste**
(⌘X, ⌘C and ⌘V work too while the list has the focus). Copy an image, open
another journal (or keep this one) and paste: the image is copied there with
its notes, drawings and tags, keeping its date. It gets the next name free
for that date (`day261014b.png` when `day261014.png` is there), so nothing
is overwritten. Cut works the same, but the image leaves its journal when it
is pasted, and is shown in gray until then; pasting it in its own journal
does nothing. Paste also works between two DayJournal windows, and pasting
image files copied in the Finder adds them as captures.

**Delete Capture…** in the same menu (or Del, or ⌫, with the mouse on the
list, or while the list has the focus, or **Edit ▸ Delete Capture…**)
deletes the image selected with its
notes, drawings and tags, and shows the one after it. It asks first; check
**Don't ask again** to delete without asking from then on, and turn **Edit ▸
Ask Before Deleting** back on to be asked again. With the mouse on the image
and drawings selected, Del deletes those drawings instead, never the image. A deleted capture can't be
recovered from DayJournal.

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

**Fit** (a magnifier with a double arrow) fits the image in the window,
**Real Size** (a magnifier with =) shows it at its size, and **Zoom +**/**Zoom
−** (a magnifier with + or −) zoom. On a trackpad, a double tap with two
fingers zooms in, zooms in again, and fits again, keeping the point tapped
in place, and pinching zooms in and out. Drag to move around. **View ▸ Open
in Preview** opens it with the system viewer, with the drawings shown on
it: a PNG at the image's size, made in a temporary folder (the image itself
when nothing is drawn).

The cursor is a crosshair: a dashed horizontal and vertical line through
the mouse, across the whole image, so you can see the same level or time at
other places of the chart. It hides while you draw, drag the image or write
a text, and comes back when you move the mouse again. It is always on.

**Hide** on the drawing bar (or H with the image focused) hides all the
drawings, to see the image as it is; the button then says **Show**, and
pressing it (or H) brings them back. Hidden drawings are kept and saved, and
stay hidden as you go to other images, until you show them, draw something
new or paste drawings.

**Copy** on the drawing bar (⇧⌘C, **Edit ▸ Copy Image**, or **Copy Image**
when you right click an image in the list) copies the image with its
drawings to the clipboard, at its own size, to paste it in a message, a
document or another program. ⌘C in the list still copies the capture, to
paste it in another journal.

### Scaling one of two charts

Some captures hold two charts side by side, with different vertical scales.
**Edit ▸ Scale Panel…** (⇧⌘S) scales one of them vertically so its price
levels match the other one's. Click where the two charts meet (a blue line
follows the mouse), then click on the chart to scale, near its time axis:
below that line the chart stays as it is, so its times do too.

Then drag that chart up or down to put one of its prices on the level the
same price has in the other chart: a white line across the whole image
follows that price (and the mouse), so you can see whether they line up.
Then scale the chart with the scroll wheel (or the trackpad), or by dragging
up or down with shift held: it stretches or shrinks keeping that price where
you put it. Drag again to move it, from any price; that price is then the
one kept in place. The status bar says the scale.

Double click when done: DayJournal asks whether to replace the image with
the result. Yes saves it over the capture's PNG, at the same size (what goes
past the top is cut, and what is left empty is filled with the chart's
background), No puts the image back as it was. Clicking first beyond either
side of the image scales the whole image instead. Esc, or the right button,
cancels. The drawings on the chart scaled, above the line, move and scale
with it, so they stay on the same prices; the others stay where they are.
They are saved with the image.

**View ▸ Toolbar** shows the buttons of the toolbars with their icons and
text, their icons only, or their text only, in every window; the choice is
remembered. It applies to the drawing tools too, each with its own icon (an
arrow pointer for **Select**, a pencil, a line, an arrow, a circle, a
rectangle, a T and the Fibonacci levels). A button without an icon keeps
its text. The gear at the end of
the toolbar is a menu with **Swing Times**, **Strategy Tester**, **Queries**, **Match
Day** and **Match Week**. In the drawing tools, **Copy** (two sheets) copies
the image with its drawings, and the eye hides the drawings; it is struck
out while they are hidden, and a click shows them again.

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
A line (not an arrow) also has **Extend across the image**: a horizontal
line then goes from the left edge to the right one, a vertical one from top
to bottom, and any other to where it meets the edges. Its ends stay where
they were, for its handles. Extended, **Left** and **Right** put the label
at that end of the line, across it, and the line stops before it (for a
vertical line the form says **Top** and **Bottom**); **Center** keeps it in
the middle of its two points.

To copy drawings, select them and press ⌘C (Ctrl+C elsewhere). ⌘V pastes
them under the mouse, selected, on this image or on another one (in
DayJournal or RoadBook); with the mouse off the image they go a little to
the side of where they were. **Undo** removes them.

**Rect** draws a rectangle, just its border at first. Double click its
border (anywhere on it once filled) to set:

- **Width** and **Style** (solid, dashed or dotted) of its border;
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

In these windows the drawing shows each change at once, colors too while
you pick them; **OK** keeps the result and **Cancel** puts it back as it
was.


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
from the first point to the second; the other sets never draw it. Its
**From 2** box starts the lines at the second point instead of the first, so
they go from the second point to where you clicked the third; while you
draw it they still start at the first point, so you see the levels. Picking a
set with fibs selected changes their levels instead. Double click a fib
(on one of its lines) to open its levels, checked, and change them, or
draw its diagonal, or set the **Width**, **Style** and **Color** of its lines; a name there keeps them in the menu too. The fib shows
the levels as you check or type them, and so do the fibs selected while the
custom form is open; **OK** keeps them, **Cancel** puts them back, and
**Undo** puts the old ones back. A color picked from the bar's **Color…**
shows on what is selected while you pick it, the same way.

**Clear** in the custom form unchecks all the levels, to start a set from
scratch. Type a short **Name** before OK to keep the levels in the Fib menu,
after the built-in sets. A name already in the menu, built-in or saved,
asks whether to replace that one; **No** goes back to the form to pick
another. This goes for the looks saved from the other forms too, and for
renaming in **Edit Saved…**; only Plain and Custom can't be used.

Rectangles, lines, arrows and circles can be kept the same way: double click
one, set how it looks, and type a name in **Save as**. Its color, width,
style, fill, middle line and label (not its size or place) go to the menu of
its tool, and picking it there draws the next ones like it (or changes the
ones selected). **Plain**, first in each menu, draws with the color, width
and style chosen on the bar. **Edit Saved…** at the end of each menu lists
the ones saved there, to change (**Edit…** opens its form: the levels of
a fib, or the color, style, label... of a rectangle, line, arrow or
circle), rename (double click), remove or move them up and down. They are
shared by DayJournal and RoadBook. Lines keep **Extend** too. A fib set's
form there also has its line **Width**, **Style** and **Color**, and so does
the custom form; once a set has its own, the fibs drawn with it use them
instead of the bar's.

The built-in ones (the OTE, Quadrants and PO3 fib sets, and the BRK, MB,
FVG... rectangles) are listed there first, marked built-in: **Edit…**
changes them like the saved ones, and **Remove** puts one back as it came
instead of taking it out of the menu. They can't be renamed or moved.

Click a drawing with the right mouse button for a menu of the
configurations of its kind: the fib sets, or the rectangle looks and the
ones saved for lines, arrows and circles. The one it has is checked, and
picking another changes it to that one (and the others of its kind
selected with it), in one **Undo** step. The bar keeps what it draws next.

The **Detach** button (a window with an arrow out of it) at the start of the drawing buttons detaches them as a
small floating bar that stays on top of every window, so you can keep it
where it suits you. Click it again, or close the bar, to put it back.

**Select** (the usual tool) clicks a drawing to select it, drags it to move
it, and Del or **Delete** removes the ones selected. Shift-click selects
more than one. A drawing selected shows small squares (handles) where it can
be reshaped: the two ends of a line or arrow, the corners and the middle of
the sides of a rectangle or circle, and the two points and the right end of
a fib. Drag one to move just that point: a side's handle moves only that
side (the right one widens a box keeping its top and bottom). With shift, a
line's end stays level or plumb with the other, and a corner moves only
across or only up and down, as the mouse goes most. **Undo** puts it back. Double click a text box to change its text; emptying it
removes it. Dragging the image itself moves around it, as before.

The color button, the width list, the line style list (solid, dashed,
dotted) and the text size list (**Aa 16** by default, for text boxes, labels
and fib numbers) set how new drawings look, and change the ones selected.
**Clear** deletes every drawing on the image; **Undo** brings them back. **Undo** and **Redo** (⌘Z, ⇧⌘Z) undo and redo the
drawing changes of the image shown. On the bar, Undo, Redo and Delete are
icons: the curved arrows and the bin.

Drawings are kept until you **Save** them (⌘S, or the Save button in the
toolbar); meanwhile the window title says *(unsaved)*. You can go to other
images and draw there too before saving, and Save writes them all.
Quitting or opening another journal with unsaved drawings asks whether to
save them. They go in a file with the image's name and a `.drw` extension
(`day261014.drw`), and saving an image without drawings removes its file.
Notes are still saved as you type.

Drawings are kept in image coordinates, so they stay in place when zooming.
The words in the text boxes and labels are found by the search, as the notes are.

## The data view (m15 data)

Besides the captures, a journal can keep the 15 minute candles of its
market, exported from TradingView as a CSV (`time,open,high,low,close`, the
time in seconds, as TradingView writes it). **File ▸ Import Data…**, or
dropping the `.csv` (or a `.zip` with it) on the window, adds them to
compressed files in the journal directory named after the day of their first
candle, `MNQ-260102.m15.csv.gz`. A file is not made larger than about 512 KB
(a year and a half of m15 candles): when it is full, the candles that come
after start a new file. Data files named otherwise, from before, are renamed
so when the journal opens. A file imported later adds only
the candles after the last one kept (and any before the first), so
exports that overlap don't make duplicates.

**View ▸ Data View** (⇧⌘D, **Data** in the toolbar, which says **Captures**
while in the data view, to go back) shows, instead of the
captures, the weeks with data by month, each with its days, and at the right of each
row its profile. The **Weeks** and **Days** boxes list only the weeks or
only the days, and **+**/**−**, **m** and **w** open and close the groups as in
the list of captures: the swings that frame it, as in the week profiles. Picking
one draws its candles where the capture goes, in New York time: a week from
Sunday 18:00 to Friday 17:00 with its days, a day from 18:00 the day before
to 17:00 with its Asia (20:00–00:00), London (02:00–05:00), NY AM
(07:00–11:30) and NY PM (13:30–16:00) sessions, the times of the ICTlevels indicator, as boxes from their high to their low. The profile
is drawn over the candles, and the notes area says the open, high, low,
close and range, and each session's range. Previous, Next, First, Last and
Week (day ⇄ its week) move through the data, and the calendar goes to a day.

Switching the data view on goes to the day or week of the capture shown;
switching it off (or **Captures** over the list) goes back to the capture of
the day or week the data view was on, or the nearest one.

You can draw on the charts of the data view as on a capture. **Save** keeps
the drawing of each day or week in a file of its own, in the journal's
`m15draw` folder (`d261117.drw`, `w261116.drw`), and the list marks those
rows with ✎. The chart of a week or day still going on changes its price
scale as candles are added, so what is drawn on it may no longer sit on the
same prices.

**Edit ▸ Adjust Profile…** (⇧⌘R) on the chart of a day or week of the data
adjusts its profile as on a week capture: drag its points, click a segment
to add one, right click one to remove it, double click or Return to keep
it. It is kept in `m15draw` (`d261117.prof`) and used from then on, in the
list and by Match Week and Match Day; **Edit ▸ Find the Data Profile Again**
forgets it.

**Edit ▸ Match Week** also uses the data: it compares the week with the week
profiles of the captures and with the weeks of the data, marked *(m15
data)*. The week is the week profile shown, or, on a day (a capture or a day
of the data), its week from the data up to the end of that day. Picking one
shows it.

**Edit ▸ Match Day** (⇧⌘Y) compares the day shown, a capture's day or a day
of the data, with the other whole days of the data, from 18:00 the day
before. On a capture of an m15 chart in New York time it reads the day so far
from the capture itself: the day starts at the last dotted blue line
(midnight) with candles after it, and the candles are placed by the line
before it (a day is 92 candles) or the dashed line of the week, so take the
capture with the previous Asia session and the midnight line before it.
When the capture can't be read so (another time frame, no lines) or you pick
**the m15 data** in its window, the day comes from the data, up to the time
picked (New York time; the end of the data for a day still going on).
Picking a day shows its capture, or its chart in the data view when there is
none (in the data view, always its chart).

### Lower time frames

**File ▸ Import Data…** also takes candles of a lower time frame, such as an
m1 dump (`time_utc_close;open;high;low;close;volume`, with `;` or `,`, the time
as a number or a UTC date, and as the candle's close when the column says
so). They are kept in files of their own (`MNQ-220103.m1.csv.gz`, at most
about 2 MB each), and made into m15 candles that the m15 data takes as any
other import: only those after its last candle or before its first.

Another feed may quote another contract, so its prices can differ from
those already there by a few points, and by a different amount after each
contract roll. When the candles imported overlap the m15 data there, each
contract's offset is found from the candles in common (the median close
difference, from the first day of a run of days that agree), and the
imported prices are moved by it: the earliest offset for the candles before
the data there, the latest for those after. The status bar says the offsets
used. Roll days and a bad tick may still differ.

The time frame box on the toolbar (or View ▸ Time Frame), in the data
view, picks the time frame of the charts: m15 and
above (m30, h1, h4) always, and with m1 data also m1, m3 and m5, drawn the same
size as the others: zoom in or scroll on its time axis to see
their candles. The profiles, the sessions and the summary still come from
the m15 data. A day without data in the time frame picked is drawn in m15.
**D**, **W** and **M** chart days, weeks and months, made from the m15 data:
the last 130 days, 104 weeks or 120 months up to the day picked (or the
Friday of the week picked), the last one as far as it got by then, with
their months or years on the time axis. Each candle takes the same width,
so there are no gaps for weekends, and scrolling on the time axis shows ten
of them at least. They have no profile, sessions or news lines; the
indicators, the crosshair of synced windows and drawing work there as in
the others.
**File ▸ New Window** in the data view opens another window on the same day
or week, to look at it in another time frame. What is drawn on a chart is
kept for its time frame (`d261117-m5.drw`).

**File ▸ Add Chart as Capture** (⇧⌘K, **Capture** over the list) adds the
chart shown, in its time frame, to the captures of its day (or as the week
profile of its week), with what is drawn on it, which can still be edited
there.

### Scaling a chart

A data chart is as wide as its window: a wider window shows the hours wider
instead of leaving room at the sides, and it is drawn again when the window
changes size. Drawings stay at their times and prices.

Scrolling over the price axis of a data chart (its right edge), or inside
the chart by its left or right edge, shows more or fewer prices around the
one under the mouse; scrolling over the time axis (its bottom edge), or
inside by the top or bottom edge, shows more or fewer hours, down to half
an hour of a day or two hours of a week, which then label their hours.
Scrolling around the center of the chart zooms in or out on both, there.
Scrolling anywhere else moves the chart: up and down over its prices,
sideways (or with ⇧) over its times. A double click on an axis shows all of
it again.

Zooming in a data chart (**Zoom +**/**Zoom −**, a double click, pinching
on a trackpad) scales its prices and times instead of enlarging the image,
so its axes are always in the window; **Fit** shows all of it again.
Dragging a chart scaled so moves it over its data, to the times and prices
out of view. Each window keeps the scale of each chart while it is open.
What is drawn stays at its prices and times, and is saved as on the whole
chart, so it shows right at any scale. Hiding the drawings (**Hide**, or H
on the image) hides the profile line too; **View ▸ Profile Lines** (on by
default) shows or hides the profile lines on their own, so the drawings
can be shown without them.

### Synced windows

**File ▸ New Window** opens a window with the image taking almost all of
it: its list and notes are closed (**List** and **Notes** open them). Its
**Sync** button (**File ▸ Sync with Other Windows**) makes it move with the
main window and the other synced ones: going to a day or week in any of
them takes the others there, each staying on days or on weeks as it shows
them, and on the data charts the crosshair of one shows in the others at
the same time and price. A new window on the data is synced; one on a
capture is not. In the data view, the menu of the **Window** button on the
toolbar opens a new window in another time frame, on the same chart: this
window and those it opened so are then laid out together, this one on the
left half and the others on the right, when the screen has room.

**View ▸ Session Rectangles**, on by default, draws the Asia, London, NY AM and NY
PM sessions of the days as rectangles; turned off, the charts show the
candles alone (or the sessions the indicators draw).

### News days

The days of FOMC decisions (14:00 New York), and of CPI, PPI and NFP
releases (08:30), from 2022 to 2027, are built in, from the Federal
Reserve's and the BLS's calendars. **File ▸ Update News Dates** reads those
calendars again for the dates scheduled since, and keeps them for every
journal. The data list names them after their day and week, the
charts mark them with an orange line at their time, the summary lists them,
and the captures of those days have them as tags, so searching `CPI` or
`FOMC` finds them. A `news.txt` in the journal adds others, one a line:
`2027-01-08 NFP 08:30` (the time is 08:30 when left out), and a line that
starts with `-` takes one away (`-2026-12-10 CPI`), for a date that moves.

Holidays and special days are marked too: the days the markets close or
close early (New Year's Day, MLK Day, Presidents Day, Good Friday, Memorial
Day, Juneteenth, Independence Day, Labor Day, Thanksgiving, Christmas, the
day after Thanksgiving, Christmas Eve, July 3) and the bank holidays
(Columbus Day, Veterans Day), reckoned from their rules, as the NYSE keeps
them. Their captures have the holiday's name as a tag (`Thanksgiving`),
and `Holiday`; the data and capture lists show it abbreviated after the
day (`Thu 26 · Thksg`), the chart's title names it, and **File ▸ Update
News Dates** also reads the NYSE's and the Federal Reserve's holiday
calendars. In `news.txt`, a holiday's name adds one (`2027-01-09
Mourning`, or just `Hday`) and `-` takes one away. The captures list shows
the news days as well. In the calendar, holidays have a red background
and news days a green one.

### Indicators

TradingView Pine indicators can be drawn on the data charts. **View ▸
Indicators ▸ Import Indicators…** takes their source (the `.txt` or `.pine`
files of the script, as copied from the Pine editor), keeps a copy for
every journal and turns them on; the menu lists them, checked when on in
the window, and remembers which are for the windows opened next.

Each window shows its own indicators: the **Ind** menu at the end of the
drawing bar, in the data view, lists them, checked when shown in the
window. Clicking one shows or hides it there, and the menu stays open to
click more; a click outside closes it. A right click on one opens its
settings. A new window starts with the indicators of the one it was opened
from. **Remove** forgets one, and **Show Indicators Folder**
opens where they are kept. **Indicator Folders…** adds other folders to
look for indicators in (a folder of Pine scripts kept elsewhere, say): the
imported ones are looked for first, then those folders in the order listed
(**Up** and **Down** change it), and the first one found of a name is the
one used. Indicators of those folders are not removed from the menu; take
the folder out instead.

An indicator is run on the candles as if the last candle shown were the
last one: on the whole day or week, its last candle; zoomed in, the last
one at the right edge. It runs on up to 5000 candles of the chart's time
frame before that one (as TradingView does), with its default inputs, and
the time frames it asks for (`request.security`, `request.security_lower_tf`)
come from the journal's m15 and lower data, cut at the same candle. What
it draws (lines, boxes, labels, tables, shapes, backgrounds) goes on the
chart, its sharp redraw when zoomed in, and **Add Chart as Capture**.
Indicators run in the background: while a chart is scaled or moved, or
another day is shown, the chart keeps what its indicators drew last and is
drawn again when their new runs are done (a capture waits for them).
While a chart is being scrolled, scaled or dragged they are not run at
all: it shows what they drew last, runs going on are stopped, and they are
run where the chart went once it has been still for a second.
When an indicator draws past the last candle (a label or line ahead of
it), the chart keeps room for it right of that candle, up to a quarter of
the times shown, with no candles in it.

The small blue triangle on the time axis marks where the candles' times
end. Drag it left to keep more room right of the last candle, or right to
keep less: the room stays that share of the chart's width, zoomed or not,
in every window, and with or without indicators. A double click on it goes
back to the room the indicators need.

**Indicators ▸ Settings** shows the inputs of an indicator as TradingView
does, in their groups and rows, with their tooltips: numbers, choices,
checkboxes, colors (with their opacity), texts and times. **Restore
Defaults** puts back the script's values. The values changed are kept for
every journal, and the charts are drawn again with them.

Only the part of Pine the journal's indicators use is understood: a script
that uses something else, or fails as it runs, says why at the bottom of
the chart and in the status bar.

### Swing times

**View ▸ Swing Times…** looks at all the m15 data of the journal for the
times that usually start a significant move. A **swing** is a leg of the
zigzag of the candles that reverses at least **Swing ≥** times the average
range before it (of the 20 days before, for the day; 8 weeks, for the week;
6 months, for the month); a **retracement** is a pullback against a swing
of at least **Retracement ≥** times that range that does not end it. Each
one starts at the high or low it leaves from, and that candle's time is
counted.

- **Day**: the time of the trading day (18:00 to 17:00, New York time, in
  slots of 15, 30 or 60 minutes) with, as bars, the share of the days where
  a swing (blue) or a retracement (orange) started in that slot.
- **Week**: a grid of weekday and hour; the darker a cell, the more weeks a
  swing (or a retracement) started there.
- **Month**: the trading day of the month (1st, 2nd…), from the daily
  candles.

Pointing at a bar or cell tells its shares of swing and retracement starts and the mean
size of the swings that started there. The text below the chart names the
most likely times. The list at the top left takes only part of the data (the last 3 or 6
months, the last year…). With a search in the list, only the days (and,
for the week, the weeks) it leaves are counted: search `CPI` to see when
swings start on CPI days. The swings are still found on all the candles,
and the window counts again when the search changes.

#### Macro times

**Macro Times…** turns the slots of the day most likely to start a swing (or
a retracement) into macro windows: the slots with at least the share set
(the slider), next ones joined, as `HHMM-HHMM` times, such as
`0930-1000,1030-1100`, which can be edited. **Set in Indicator…** writes
them in an indicator's source, after showing the change and asking: it
replaces the first string of each line of the script marked with a
`// @dj-macros` comment, and keeps the old source next to it, with `.bak`
added to its name. For example, a script with

    string djMacros = "0950-1010,1050-1110" // @dj-macros

gets the new times in that string; the script decides how to use them
(splitting them at the commas, say). Only indicators with such a line are
listed.

### Strategy Tester

**View ▸ Strategy Tester…** runs a Pine strategy (a script declaring
`strategy(...)`) on the journal's data, as TradingView's Strategy Tester
does on a chart. The indicators that are strategies are listed; **Add
File…** adds one kept elsewhere. Pick the **Time frame** of its candles
(those under m15 need the lower time frame data), the **Range** of days, and
**Run**: it runs in the background with a progress bar, and **Stop** ends it
with the trades made so far. **Settings…** shows its inputs, the same ones
the charts use.

Orders are filled as TradingView's broker emulator does: market orders at
the close of the candle when the strategy says `process_orders_on_close`,
or else at the next open; stops and limits (of entries and of
`strategy.exit`) on later candles, as the price goes from the open to the
nearest of the high and the low, to the other, and to the close; a candle
opening past one fills it at the open. An entry the other way reverses the
position. **Commission** (a contract, each side) and **Slippage** (ticks)
replace the strategy's own when set. Profits are in dollars at the
symbol's point value (2 for MNQ, 20 for NQ).

A range starts 5000 candles earlier, so the strategy has its history, and
only the trades entered in the range count. With a search in the list,
only the trades entered on the days it leaves count: the strategy still
runs on all the candles.

- **Overview**: the net profit as it went (closed trades and the one open)
  and the figures of all the trades, the longs and the shorts: net profit,
  profit factor, win rate, average and largest trades, max drawdown…
- **List of Trades**: each trade, with its run-up and drawdown. Clicking
  one shows it in the data view, in the time frame of the test, zoomed on
  it, and drawn as a long or short position: a green zone from the entry
  to the target and a red one to the stop (as the trade's exits first had
  them, with their distance in points), the entry (a blue dot), and a
  dashed line to the exit with the result in points and dollars. A trade
  without a stop or target gets a zone to its exit, green if it won. The
  drawing goes when the Strategy Tester is closed; double-click the chart
  to see the whole day again.
- **By Hour**: the trades by the hour they were entered.
- **By Period**: the trades by the year, month or weekday they were
  entered, or by the killzone (New York time: Asia 20:00-00:00, London
  02:00-05:00, NY AM 07:00-11:30, NY PM 13:30-16:00, or Other): trades,
  net profit and points, win rate and profit factor. A strategy that only
  makes money in one year or one session shows it here.
- **Compare**: runs the strategy once for each value of an input, or of
  two (every combination), with the time frame, range, commission and
  slippage above and the other inputs as set. Pick the input and write
  its values separated by commas (`10, 20, 30`, `true, false`, or options
  as the settings show them), and **Compare**. Each run adds a row: its
  values, trades, net points and points a trade, net profit, win rate,
  profit factor, max drawdown and the net points of each year. Clicking a
  row shows that run in the other tabs. **Stop** ends it with the runs
  made.

**Export Trades…** saves the list as CSV. While a strategy runs, the
indicators of the charts wait for it.

The same tests run without the window, from a terminal in the source
folder, for long runs or many of them:

    python3 backtest.py -t 5 -f 2022-01-01 -b year -b session ~/u/trade/DayJournalNQ ICTScalpStrategy.txt
    python3 backtest.py -t 5 -I Auto=true,false -I "Risk ratio=1.5,2,3" -q journal strategy.txt

`-t` is the time frame in minutes, `-f` and `-l` the first and last day,
`-i name=value` sets an input (by its title or the start of it, or by
its key, `group|title|inline`, when titles repeat), `-I name=v1,v2` compares values
(more than one `-I`: every combination), `-b` prints the trades by Year,
Month, Weekday, Session or Hour, `-c` and `-s` are the commission and
slippage, `-o` exports the trades to CSV and `-q` leaves out the list of
trades.

### Queries

**View ▸ Queries…**, also in the gear's menu, asks the data a question
in one line and answers with a table and a chart. Type the query and press
Return or **Run**, or pick one of the list at the left:

    share day takes asia.low then asia.high by weekday tf 5

reads "of the days, the share that took the Asia low and then its high, by
weekday, on m5 candles". A query is made of:

1. a **stat**, what to work out: `count`, `share`, `dist`, `avg`…;
2. **what it is about**: periods, and what they have or did;
3. then, in any order, **where** (which periods count), **by** (a row for
   each key), **in** (the dates) and **tf** (the time frame).

#### Periods

A period is a stretch of time with candles; the query names them:

| Write | It is |
|---|---|
| `year`, `month`, `week`, `day` | a year, a month, a week (Sunday 18:00 to Friday 17:00), a trading day (18:00 the day before to 17:00) |
| `mon`, `tue`, `wed`, `thu`, `fri` | that day of the week |
| `asia`, `london`, `nyam`, `nypm` | the sessions of a day: 20:00–00:00, 02:00–05:00, 07:00–11:30, 13:30–16:00 |
| `session` | any of those four: each session of each day is counted, in a row, and `prev session` is the one just before (London's is Asia, Asia's the NY PM of the day before) |
| `h9` | an hour of the day, 09:00–10:00 (`h20` is 20:00 the evening before) |
| `08:30-10:00` | any window of the day; `20:00-02:00` starts the evening before |
| `prev day`, `next week`, `prev 2 day` | the period before or after (the London before is `prev london`) |

All times are New York's. A dot goes into a period: `mon.asia` is the Asia
of Monday, `week.fri` the week's Friday.

**What is counted** is the smallest of the periods named: a query about
`asia` or `london` counts days (the Asia of each day), one about `mon`
counts weeks, one about `week` alone counts weeks, and one about `session`
counts sessions. `count day`, `list week`
and `among week` say it outright.

#### What a period has

After the period, a dot and what you want of it:

| Write | It is |
|---|---|
| `open`, `close`, `high`, `low`, `mid` | prices: its first and last, its highest and lowest, half way |
| `ce`, `dq`, `uq` | half way (as `mid`), a quarter of the way up, three quarters |
| `range` | high minus low |
| `move` | close minus open |
| `dir` | `up` or `down`: close above or below the open |
| `cond` | its condition (below): `uptrend`, `consolidation`… |
| `swings` | how many swings it made (back and forth), of at least half its range |
| `rel` | its range as a part of the average range of the periods before it (20 days, 8 weeks, 6 months): 0.5 is half the usual |

A high or a low is also *when* it was made, with a dot more:

| Write | It is |
|---|---|
| `.hour` | the hour, 18 to 16 in the order of the day |
| `.time` | the time of its candle, 09:35 |
| `.session` | `asia`, `london`, `nyam`, `nypm` or `other` |
| `.day` | `mon` to `fri` |
| `.date` | the day |

So `week.high.day` is the day of the week's high, `day.low.session` the
session of the day's low, `london.high` London's high (a price). Numbers can
be worked out with `+ - * /` and parentheses: `day.range / prev day.range`,
`nyam.high - asia.high`.

#### Conditions of a period

`cond` tells what price did in the period, from its open, high, low and
close and the order they came in; nothing before it matters. With *r* the
range, the first that fits:

| Condition | What price did |
|---|---|
| `consolidation` | closed near the open (within a quarter of *r*), up and down around it; or went back and forth across the range, wherever it closed: 4 swings of half *r* or more, with two of their lows in the lower third of the range and two of their highs in the upper third. Price that leaves the lower part and never goes back to it is not ranging, however much it swings above |
| `upreversal` | went down first, at least 0.4 *r* below the open, then turned and closed above the open |
| `downreversal` | went up first, at least 0.4 *r* above the open, then turned and closed below it |
| `upretrace` | went up, then gave back at least 0.4 *r* from the high, closing still above the open |
| `downretrace` | went down, then came back at least 0.4 *r* from the low, closing still below the open |
| `uptrend` | closed at least 0.6 *r* above the open, near its high |
| `downtrend` | closed at least 0.6 *r* below the open, near its low |
| `mixed` | none of those: up or down some, without the rest |

`trend` stands for either trend, `reversal` and `retrace` for either of
theirs. The numbers are the journal's: **Conditions…** opens its
`conditions.txt`, which has them as parts of the range: `flat` (0.25),
`swing` (0.5) and `swings` (4), `reversal` (0.4), `retrace` (0.4) and
`trend` (0.6). It also has `near` (0.02) and `bounce` (0.1) for
`rejects`, as parts of the average range of a day. A change is used by
the next query.

They work on any period: `asia.cond`, `week.cond`, `h9.cond`,
`08:30-10:00.cond`. Lower time frames see more of what price did inside
it: on m1 a day has more swings than on m15.

#### Conditions, to pick periods

After **where**, and in `share`, a condition says yes or no for each
period:

| Write | Yes when |
|---|---|
| `asia is consolidation` | Asia's condition is that; `is not` for the opposite |
| `mon is up`, `day.dir is down` | the direction |
| `day.high.session is london` | any value, by its name |
| `day.range > 300`, `nyam.high >= london.high`, `day.rel < 0.6` | a comparison: `>`, `<`, `>=`, `<=`, `=`, `!=` |
| `day takes asia.low` | in the day, after Asia, price went below Asia's low |
| `nyam takes prev day.high` | in New York's morning, price went above the day before's high |
| `nyam above london.mid`, `day below prev day.close` | price went past any level |
| `day closes above asia.high` | a candle closed past it |
| `day soups asia.low` | a turtle soup: price went below Asia's low, a candle closed back above it, and price did not go below the low of that take again in the day |
| `nyam touches rthog.ce` | a candle traded at the level, from either side |
| `day fills rthog`, `nyam fills london.lastfvg5` | price traded all the way across a gap or an FVG after it was made: down to the low of a gap up or a bullish FVG, up to the high of a gap down or a bearish one; a quarter (`fills rthog.q4`) is crossed from the side price is on |
| `nyam rejects rthog.ce`, `day rejects prev day.high` | price came to the level, wicking past it or stopping very near it, did not close past it, and then went away from it (a bounce) before any close past it |
| `asia.high inside prev day`, `day.close inside rthog.q4` | the price is within a period's range, a gap, an FVG or a quarter of one |
| `day takes asia.low then asia.high` | first one, later the other |

`rejects` works out the side from where price is when the search starts:
above the level it is a support tested from above, below it a resistance.
"Very near" is 0.02 of the average range of the days before (`near` in
`conditions.txt`) and the bounce 0.1 of it (`bounce`); on NQ, with days of
about 550 points in 2026, some 11 and 55 points. The time of a reject, for `(when
…)` and `then`, is the candle that came to the level.

`takes` goes above a high and below a low; `soups` is a take that failed:
price went past the level, closed back on the other side, and never went
past what it reached again (the first take of the level is the one that
counts; the soup happens when it closes back). `above` and `below` take
any level. A level of a period is looked for after that period ends: `day takes
asia.low` looks from 00:00, when Asia is over. `then` puts things one after
another, each after the candle of the one before: `day takes asia.low then
asia.high` is the Asia low taken first and its high later, the same day;
`london takes asia.high then nyam takes london.low` changes where the next
is looked for. With m1 candles (`tf 1`) what came first is found to the
minute.

Conditions join with `and`, `or`, `not` and parentheses:

    where asia is consolidation and not london takes asia.high
    where (mon is uptrend or mon is upreversal) and tue is down

`(when …)` is when the last of a `then` happened, with `.hour`, `.time`,
`.session`, `.day`: `(when day takes asia.low).session` is the session in
which the Asia low went; a day it didn't is counted as `none`.

#### Opening gaps

The gaps ICTlevels draws, worked out from the candles (nothing of
TradingView is needed):

| Write | The gap between |
|---|---|
| `rthog` | the close at 16:15 of the day before (the last candle before it) and the open at 09:30 |
| `ndog` | the close before 17:00 of the day before and the open at 18:00; there is none on Mondays |
| `nwog` | Friday's close before 17:00 and the open of the week, Sunday 18:00 |

They are of the day being counted: `rthog`, `prev day.rthog`,
`mon.rthog`, `week.nwog`. A query about `nwog` alone counts weeks. A gap
has:

| Write | It is |
|---|---|
| `high`, `low` | its top and bottom |
| `ce` | half way, the consequent encroachment |
| `dq`, `uq` | a quarter and three quarters of the way up |
| `q1`, `q2`, `q3`, `q4` | its quarters, from the bottom: zones of their own, with `high`, `low` and `ce` |
| `settle`, `open` | the close it starts from and the open it goes to |
| `dir` | `up` when the open is above the close, `down` below |
| `size` | high minus low |
| `start` | when it was made, with `.hour`, `.time`… |

A price followed by a gap says where it is in it: `above`, `q4` (the top
quarter) down to `q1`, or `below`. So `dist day.close.rthog` is where
days close, from the day's gap, and `nyam.open.rthog is above` picks
mornings opening over it. `inside` stands for any of the quarters,
`upper` for q3 and q4, `lower` for q1 and q2.

A level of a gap is looked for after the gap is made: `day touches
rthog.ce` looks from 09:30, `day takes nwog.high` from the open of the
week.

#### Fair value gaps

An FVG is three candles where the third's low is above the first's high
(bullish, the gap between them) or its high below the first's low
(bearish). A period has them:

| Write | It is |
|---|---|
| `fvg` | the first FVG made in the period |
| `lastfvg` | the last |
| `bullfvg`, `bearfvg`, `lastbullfvg`, `lastbearfvg` | of one kind only |
| `fvgs`, `bullfvgs`, `bearfvgs` | how many there are |

They have `high`, `low`, `ce`, `dq`, `uq`, `q1`…`q4`, `size`, `start` and
`dir` (`bull` or `bear`), as gaps do. A number after the name is the time
frame they are found in, whatever the query's: `fvg5` on m5, `fvg1` on m1,
`fvgh1` on h1; with none, the query's. So `london.lastbullfvg5.ce` is the
half way of the last bullish m5 FVG of London, and `nyam touches
london.lastbullfvg5.ce` asks if New York's morning came back to it, looking
from the third candle of that FVG.

#### Stats

| Stat | It gives |
|---|---|
| `count` *period* | how many there are (with where: that pass it) |
| `list` *period* | them, one a row; clicking one shows it in the data view |
| `share` *condition* | the part of them where it holds, in % |
| `dist` *value* | how many had each value: conditions, days, sessions, hours; numbers in ranges |
| `avg`, `median`, `min`, `max`, `sum` *number* | of the number, over them |

#### where, by, in, tf

- **where** *condition* keeps the periods where it holds; the stat is over
  those only.
- **by** *key* makes a row for each value of the key; **by** *key*, *key* a
  grid. Keys: `weekday`, `month` (2025-03), `monthname` (Mar, for seasons
  across years), `year`, `quarter`, `session` (its name, when counting
  sessions), or any value: `by asia.cond`, `by
  day.high.session`, `by mon.dir`.
- **in** `2025`, `2025-03`, `2025-03-14`, `2024-03..2025-06`, `last 6
  months` (or days, weeks, years).
- **tf** `5`, `tf m1`, `tf m2`, `tf h1` (or `on m5`): the candles the query uses,
  made from the lowest time frame kept in the journal that fits (m1 makes
  m2, m3 and m5; m15 makes h1). The box by **Run** sets it when the query has
  no tf. Highs, lows, their times and what was taken are found in those
  candles. The data under m15 often starts later, and only the periods it
  has are counted.

#### Examples

    dist day.cond                                     how days go
    dist day.cond by weekday                          and by day of the week
    dist day.cond by monthname in 2022..2026          by month of the year
    dist week.cond by year
    share day is consolidation by weekday             consolidating week days
    dist week.high.day where mon is uptrend           the day of the week's high, when Monday went up
    dist week.low.day where mon is downtrend and tue is down
    dist london.cond where asia is consolidation      London, when Asia was quiet
    dist day.cond by asia.cond                        a grid: the day by its Asia
    share day takes asia.low then asia.high tf 5      took Asia's low, then its high
    share day takes asia.high then asia.low by weekday tf 5
    dist (when day takes asia.low).session tf 5       when Asia's low goes
    share day soups asia.low by weekday tf 5          turtle soups of the Asia low
    dist (when day soups prev day.high).session tf 5  when the day before's high is souped
    dist (when nyam takes london.high).time tf 1 where london is uptrend
    share nyam takes london.high where asia is consolidation and london is uptrend
    share day closes above prev day.high by weekday
    dist day.high.hour in last 12 months              the hour of the day's high
    dist day.low.session where day is uptrend
    avg nyam.range by weekday in last 6 months
    avg day.range / prev day.range by weekday
    dist day.swings tf 5                              how much days go back and forth
    dist session.cond by session                      every session, by its name
    share session takes prev session.high by session tf 5
    avg session.range by session, weekday
    count day where day.rel < 0.6                     small days
    list day where day is downreversal and asia is consolidation in 2026
    list week where mon is upreversal and fri is uptrend

With the opening gaps and FVGs:

    dist rthog.dir                                    gaps up and down
    avg rthog.size by weekday                         how big the 09:30 gap is
    dist day.close.rthog                              where days close, from their gap
    dist day.close.rthog where rthog.dir is up
    share nyam touches rthog.ce                       the gap's half way, filled in the morning
    dist (when day touches rthog.ce).time tf 5        and when
    share nyam touches rthog.ce where nyam.open.rthog is above
    share day fills rthog                             the gap filled, all of it
    share nyam fills rthog by weekday
    dist (when day fills rthog).hour tf 5             and when
    share day fills rthog where rthog.size > 100      the big ones
    share week fills nwog by year
    share nypm fills nyam.lastbullfvg5 tf 5           the morning's last bullish FVG, filled after noon
    share day touches rthog.ce where not day fills rthog
    share nyam rejects rthog.ce then fills rthog
    share nyam rejects rthog.ce by weekday            the gap's half way held
    dist (when nyam rejects rthog.ce).time tf 5
    share nyam rejects prev day.high tf 5             the day before's high, rejected
    share nyam rejects asia.high then takes asia.low tf 5
    share week rejects nwog.ce by year
    share nyam rejects london.lastbullfvg5.ce tf 5    London's last bullish FVG held
    share day takes rthog.low where rthog.dir is up   the gap up filled all the way
    share asia.high inside rthog                      Asia's high within the gap
    share day closes above rthog.uq by weekday
    dist nyam.high.rthog where nyam is uptrend        where a rising morning tops
    avg ndog.size by weekday
    share day touches ndog.ce where ndog.size > 10
    dist week.close.nwog                              where weeks close, from theirs
    share week touches nwog.ce by year
    share mon takes nwog.high then nwog.low
    share rthog.dir is up where prev day.rthog.dir is up
    avg nyam.fvgs5                                    how many m5 FVGs in the morning
    dist nyam.fvg5.dir where asia is consolidation    the kind of the first one
    share nyam touches london.lastbullfvg5.ce tf 5    back to London's last bullish FVG
    share nyam takes london.lastbearfvg.high
    dist (when nypm touches nyam.lastfvg5.ce).hour tf 5
    avg day.fvgs by day.cond                          FVGs in trending days and the rest
    list day where day.close inside rthog.q4 and day is uptrend in 2026

The line offers words as they are typed: periods, stats and keywords, and
after a dot what the thing before has. Pick one with the arrows and Return,
or keep typing.

#### More

A query can also be typed in the search box of the main window, after a
**?**: `? share day takes asia.low` and Return runs it here, leaving the
search as it was (and the days it leaves still count).

A wrong query turns red, saying what was expected and where. With a search
in the list, only the days and weeks it leaves count, as in Swing Times:
search `CPI` to ask about CPI days. The text below the chart says how many
periods were counted and from when to when: a share of five weeks says
little. When **where** or a search leaves only some of them, it says how
many of how many: "on 60 of 256 weeks".

**Save…** keeps a query with a name in the journal's `queries.txt`
(`name: query` a line); the list shows examples until there is one.

The same queries run from a terminal in the source folder:

    python3 query.py ~/u/trade/DayJournalNQ "dist week.high.day where mon is uptrend"

### From RoadBook

The **Journal** button of RoadBook's graphics window shows the day of its
trade here: DayJournal finds, among the journals open and the recent ones,
the one with data of the trade's instrument (by its name, or the other
names RoadBook has for it: `MNQ*`, `NQ*`), opens it if it is not open,
and shows the day in the data view, zoomed on the trade, with a dashed line
at its entry and one at its exit. If DayJournal is not running, RoadBook
starts it. A journal not opened lately is not found: open it once with
File ▸ Open Journal.

## Exporting

**File ▸ Export All…** (⇧⌘E) saves the captures shown in the list, as the
search and the Days and Weeks boxes leave them, in one zip file you pick.
**File ▸ Export Selected…** (⌘E) saves only the capture selected in the
list, or, with a year, month or week selected, the captures shown in it.
Each one is a PNG with its drawings on it, at the image's size, named as
the capture (`day261014.png`); drawings not saved yet are included, and so
are hidden ones. A capture with nothing drawn goes as it is.

## Notes

Write under the image. Notes are saved as you type, in a file with the
image's name and a `.txt` extension (`day261014.txt`). Emptying the notes
removes the file. The days and weeks of the data view have notes too, kept
in the journal's `m15draw` folder (`d261117.txt`, `w261116.txt`), marked ¶
in the data list; their tags are their news (CPI, FOMC...), shown over the
notes with the summary of the day. The search box works in the data view as
well, finding days and weeks by their news and notes. Images with notes or drawings have a ✎ in the list, and
their notes show in its tooltip.

## Help

**Help ▸ DayJournal User Guide** (⌘?, F1 elsewhere) opens this guide in a window
of its own: its sections on the left, the text on the right. Type in the
search box to list only the sections that have all the words typed; they
are marked in the text, and Return (⇧Return back) or the arrows go from one
place found to the next. Click a section to go to it, and clear the search
to see all of them again.

**Help ▸ Guide Topics** lists the sections of the guide; pick one to open
the guide there. On macOS, the search box of the Help menu searches the
guide too: type a word and, besides the menu entries for it, **Help Topics**
lists the sections of the guide that have it (those whose titles have it
first). Pick one to open the guide there, or **Show All Help Topics** to
open it with that search.
