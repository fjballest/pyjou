# DayJournal

Still in alpha. Just born for personal use. Provided AS-IS.

DayJournal browses a day journal: a directory with snapshots of day and
week charts. It reads the text written in each image with OCR and uses the
words as tags, so the images can be searched. Each image can have notes of
its own, kept in a `.txt` file next to it. See the [user manual](docs/MANUAL.md) and the
[design notes](docs/DESIGN.md); there are PDFs of both in `docs`.

Uses PySide6 Qt for widgets and easyocr for the OCR, the same tools as
[rb](https://github.com/fjballest/rb).

## Running

    pip install -r requirements.txt
    python3 dj.py [journaldir]

Without a directory it opens the journal used last, or the first
`DayJournal*` directory found in `/u/trade` or `~/u/trade`.

## Building the app

    pyinstaller --noconfirm dj.spec

makes `dist/DayJournal.app` on macOS. The GitHub workflow
`.github/workflows/python-app.yml` builds it for Linux, Windows and macOS.

## The journal directory

| File | What it is |
|------|------------|
| `dayYYMMDD.png` | the chart of a day |
| `dayYYMMDDb.png` | another chart of the same day (any letter) |
| `dayYYMMDDweekprof.png` | a week profile: dated a Sunday, it is for the week starting the next day |
| `dayYYMMDD….txt` | the notes for the image with the same name |
| `dayYYMMDD….drw` | what is drawn on the image with the same name (JSON) |
| `.pyjou-tags.json` | the text read from each image, so OCR runs once per image |

## Source

| File | What it does |
|------|--------------|
| `dj.py` | starts the app |
| `mainwin.py` | the main window: list, search, calendar, image, tags and notes |
| `journal.py` | the journal directory: images, notes, the tags cache, dates |
| `tags.py` | turns OCR text into tags, dropping what isn't a word |
| `ocr.py` | easyocr, loaded on first use; `python3 ocr.py x.png` prints what it reads |
| `ocrworker.py` | runs the OCR in a thread |
| `search.py` | search expressions |
| `viewer.py` | the image view: zoom, and the drawing tools |
| `drawing.py` | the shapes drawn, their undo commands and their JSON form |

Tests: `QT_QPA_PLATFORM=offscreen python3 tests/test_journal.py` and
`tests/test_drawing.py` (the OCR is faked, so they run without easyocr).
