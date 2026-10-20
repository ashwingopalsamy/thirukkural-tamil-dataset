# Release configs declared by spec

Each `<name>.json` here adds one config to the Hugging Face release, built by `python -m tkcore.release` with no code change.

```json
{
 "name": "sound_index",                 // = file name; lower_snake_case
 "layer": "derived",                    // derived | evidence | tasks | agents
 "license": "CC0-1.0",                  // CC0-1.0 (default) | MIT | CC-BY-SA-4.0
 "rows": "not_share_alike_only",        // optional row filter, a name in tkcore.release.ROW_FILTERS
 "description": "...",                  // shown on the card and in Croissant
 "data": "data/signature/sound_index.jsonl",
 "key": ["kural_id"],
 "references": {"kural_id": "kurals/id"},
 "fields": [{"name": "kural_id", "type": "string", "description": "..."}]
}
```

Types: `string`, `bool`, `int8`, `int16`, `int32`, `int64`, `float32`, `float64`, `{"list": T}`, `{"struct": [{"name", "type"}]}`. A field with `"from_object": true` and type list-of-struct with two fields turns a JSON object into a list of `{key, value}` structs. Every key in the data must be a declared field; a field missing from a row is null. Translations and commentary cannot be declared here.
