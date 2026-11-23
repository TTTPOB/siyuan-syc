# Attachments

Use `syc asset upload FILE...` for local files with distinct basenames. Insert
the returned `assetPath` in the note. An upload error can leave files on the
server; inspect before retrying manually.

Use `syc asset get assets/example.png --temp` to save an existing asset, or
use `-o PATH` for a specific location. Neither overwrites files. For an image,
pass the returned local `path` to the host's image reader.

## DSH PTC
