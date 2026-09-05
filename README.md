# Hon - Simple Apps GTK (PyGObject) Reader ZIP/CBZ/PDF


![Alt text](/photo/image.png)


What Hon? Hon is from japan language (本) the meaning Book 

This App just like Tachiyomi/Mihon/Komikku but only local and optimized for Linux mobile (Tested with Mi Max 2 Fedora). this is why i made it cause i not find any good Book/Comic reader on Linux mobile. I like Komikku but i try to made it of course semi-vibe code (Backend + OCR + Optimized) and i just Frontend. if you want try is okay but, i reminded you is semi-vibe coding.

## This app using PyGObject + Libadiwata with this list feature:

- Local-Only Comic
- OCR (Only Japan) (Thanks to [manga-ocr](https://github.com/kha-white/manga-ocr) + Translation (Required DeepL API))
- Favorite Single Page Chapter

For OCR i made 3 option:

- Single Page OCR (Not recommended)
- All Page OCR (Not recommended)
- Selection OCR (Recommended)

Why not recommended? I still find Good OCR Automation (for position) still not found but for now i using EasyOCR for auto location X/Y? Horizontal Japan still work but Vertical is not working so that why. I recommend use Selection OCR

## What best path folder?

here:

```
/library_root/
  ├── Title Book A/
  │     ├── Chapter 1/
  │     │     └── nama.cbz
  │     ├── Chapter 2/
  │     │     └── nama.pdf
  │     └── ... sampai Chapter 20/
  └── Title Book B/
        └── ...
```

Here my To-DO

- [X] OCR
- [ ] Find a good library OCR
- [x] Favorite Page Chapter
- [ ] History
- [ ] Favorite Book

