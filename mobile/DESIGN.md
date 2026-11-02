# AdenClean app design notes

## Direction

The app keeps the website's brand and makes it calm to use on a phone. One thing is
bold: the house. In the request flow its four windows light up lime as each part of the
request is finished (service, day and time, details, review), so progress is something you
see on the building. Everything else stays quiet.

## Tokens

| Role | Light | Dark |
| --- | --- | --- |
| Background | paper `#F3F1E8` | deep forest `#0F1F1A` |
| Surface | `#FBFAF4` | `#16302A` |
| Ink | forest ink `#1C3B32` | `#EEF2E4` |
| Primary action | forest `#244B3F` | lime `#D6E28E` |
| Accent | lime `#D6E28E` | lime `#D6E28E` |
| Error | `#A5472B` | `#F0A88E` |

All tokens live in `src/lib/theme.ts`. Clay, the website's warm accent, is not used
as a main colour; only the darker error tone appears, and only for problems.

Type: Bricolage Grotesque (headlines, 700 and 800) and Figtree (body, 400/500/600). Scale:
36, 27, 20 for headlines; 16 body; 14 small; 13 caption. Body line height is 1.5.

Shape: radii step down with importance (hero 30, cards 22, controls 16, chips 14, windows 6).
No shadows; layers are separated by tone and a hairline.

## Rules the screens follow

- Touch targets are at least 48 points.
- Colour is never the only signal: statuses and errors always carry words.
- Every control has a spoken label; groups of choices are radio groups.
- Motion: one intro on the home screen where the windows light in sequence, and the same
  windows responding as you complete steps. Reduced-motion settings are respected.
- Copy: sentence case, active verbs, buttons named for what they do ("Send request",
  "Remove request"), errors say what happened and what to do. The app never says a request
  is "booked" or "confirmed"; an approved request is "Approved for follow-up".
- Light and dark modes follow the phone's setting.

## Regenerating images

- `python scripts/generate-assets.py` redraws the icon, splash images and Play graphics.
- `python scripts/capture-screenshots.py` runs the real app against the real server on a
  throwaway database, goes through an actual request, and rebuilds the store screenshots. It
  also checks the add-by-link flow and fails if it breaks.
