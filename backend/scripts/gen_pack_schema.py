"""Write `packs/pack.schema.json` from the `Pack` model (plan 9, P9-1.1, registry entry I-1).

Run in the api container from the backend folder: `python -m scripts.gen_pack_schema`.
Owns: the one way the committed schema is produced (`test_schema_file_is_generated` compares it). Never edit the file
by hand.
"""

import json

from di.services.modeler.pack import PACKS_DIR, Pack

SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def main() -> None:
    schema = {"$schema": SCHEMA_DRAFT, **Pack.model_json_schema()}
    (PACKS_DIR / "pack.schema.json").write_text(json.dumps(schema, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
