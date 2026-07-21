# Vehicle profile template

Copy this directory to:

```text
vehicles/<brand>/<model>/<generation-platform>/
```

Then:

1. rename `config.template.json` to `config.json`;
2. choose a stable lowercase profile ID such as `vauxhall-astra-h-delta`;
3. register the exact path and any genuine legacy aliases in
   `vehicles/catalogue.v1.json`;
4. map CAN frames to canonical events and statuses;
5. replace `fixtures/README.md` with `fixtures/mappings.v1.json` replay proof;
6. document qualification evidence and limitations;
7. run the maintained conformance and replay commands.

The template is guidance, not an allow-list. New brands, models and universal
concepts may be proposed in the same pull request as their first implementation.
