# Sync

`syc sync` calls the MCP `sync` tool with `{"action":"perform"}` (full upload
and download) on the selected instance only.

- Exit 0 means this instance completed its sync request. It does not show that
  other replicas have the same data.
- To carry changes to another replica, sync the instance you wrote to, then
  sync the other one: `syc -i server sync`, then `syc -i desktop sync`.
- Sync once after a batch of writes, not after every write.
- `syc call sync '{"action":"status"}'` reports the instance's sync status.
- On failure, report the message and stop. Do not loop; repeated attempts can
  pile up sync conflicts.

Good: write on `server`, then carry the change to `desktop` as the user asked.

```sh
syc -i server sync
syc -i desktop sync
```

Bad: claiming more than the result shows.

> Synced, so both instances now have identical notes.

Bad: retrying until it passes.

```sh
until syc sync; do sleep 5; done
```
