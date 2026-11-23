# Attachments

`syc asset` moves file bytes between this machine and the selected instance.
The MCP `asset` tool's `upload` action reads paths on the SiYuan server's own
filesystem, so it cannot upload a file that exists only on this machine.

## Upload a local file into a note

1. Upload: `syc asset upload ./figure.png` returns
   `[{"file": "figure.png", "assetPath": "assets/figure-20250101120000-abcdefg.png"}]`.
2. Reference the returned `assetPath` in the note's markdown, for example with
   `block` `append`: `![figure](assets/figure-20250101120000-abcdefg.png)`.

SiYuan renames uploaded files. Always use the returned `assetPath`. Files in one
upload must have different basenames. Upload does not sync.

Good:

```sh
syc asset upload ./figure.png
```

Bad: the server looks for this path on its own disk.

```sh
syc call asset '{"action":"upload","id":"20250101120000-abcdefg","files":"/home/me/figure.png"}'
```

Bad: a guessed asset path. The uploaded file is not named `assets/figure.png`.

```markdown
![figure](assets/figure.png)
```

## Download or view an attachment

`syc asset get ASSET --temp` saves into a new temporary directory, and
`-o PATH` saves to that path. Neither overwrites an existing file:

```json
{"asset": "assets/example-20250101120000-abcdefg.png", "path": "/tmp/syc-asset-k2j9/example-20250101120000-abcdefg.png", "bytes": 125148, "mediaType": "image/png"}
```

To look at an image, pass `path` to the host's image reader. To find which
attachments a document references, query the `assets` table:

```sh
syc call sql - <<'JSON'
{"action":"query","stmt":"SELECT path FROM assets WHERE root_id = '20250101120000-abcdefg'"}
JSON
```

Bad: printing file bytes or base64 into the conversation.

```sh
base64 /tmp/syc-asset-k2j9/example-20250101120000-abcdefg.png
```

## DSH PTC

In a DSH `run_code` program, download and attach an image in one step. The
image reaches the model when the program finishes:

```ts
const got = await tools.bash({ description: "Fetch SiYuan asset", command: "syc asset get assets/example-20250101120000-abcdefg.png --temp" });
if (got.exitCode !== 0) throw new Error(got.stderr.text);
const { path } = JSON.parse(got.stdout.text);
await tools.read_image({ file_path: path });
```

Upload a generated file and keep its asset path in the same program:

```ts
const up = await tools.bash({ description: "Upload figure", command: "syc asset upload /tmp/plot.png" });
if (up.exitCode !== 0) throw new Error(up.stderr.text);
const [{ assetPath }] = JSON.parse(up.stdout.text);
```

Bad: one `run_code` call per step, copying the printed path into the next call
by hand. Each extra step costs a model round trip and invites copy mistakes.
