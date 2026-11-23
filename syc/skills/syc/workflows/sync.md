# Sync

Run `syc sync` once after a batch of writes, not after every write. With no
positional names it syncs the selected instance. Use `syc -i NAME sync` to
select one explicitly.

To push changes from a writer and then pull them on a replica that shares the
same cloud sync target, put the writer first and the replica second:

```sh
syc sync server desktop
```

`syc sync [INSTANCE ...]` processes positional names in order and stops at the
first failure. Do not combine positional names with `-i`.

1. Check the exit code. Stdout is one JSON result; `structuredContent.instances`
   lists attempted instances in order with `instance`, `ok`, and `message`.
2. Exit 0 means each attempted instance advanced its sync timestamp and
   reported successful sync statistics. It does not prove that replicas have
   identical data. Read back a specific note on the replica if you need to
   verify it arrived.
3. On exit 1, report the failed instance and its message to the user and stop.
   Do not loop or retry automatically. If sync did not appear to run, check
   that sync is enabled, the instance is logged in to a SiYuan account, and a
   sync provider is configured.

For a status-only check, use `syc call sync '{"action":"status"}'` on the
selected instance.
