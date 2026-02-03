from collections import defaultdict
from pathlib import Path
import json, re
from openai import OpenAI

client = OpenAI()

DATA_DIR = Path("modules.data")
STATE_FILE = Path(".vs_map.json")  # mağaza-id haritasını saklarız

# Hangi dosyalar yüklenmeyecek?
def is_excluded(fp: Path) -> bool:
    name = fp.name.lower()
    if "tablerow_dump" in name or ("table" in name and "dump" in name):
        return True  # dump'ları tamamen hariç tut
    if name.startswith("test_"):
        return True
    return False

# Model eşlemesi
MODEL_ALIASES = {
    "ELROQ":  ["elroq"],
    "KODIAQ": ["kodiaq"],
    "KAROQ":  ["karoq"],
    "KAMIQ":  ["kamiq"],
    "ENYAQ":  ["enyaq"],
    "SCALA":  ["scala"],
    "OCTAVIA":["octavia"],
    "SUPERB": ["superb"],
    "FABIA":  ["fabia"],
}
ALL_MODELS = list(MODEL_ALIASES.keys())
GENERIC = "GENERIC"  # model belirsiz / ortak içerik için

def detect_model_from_path(fp: Path) -> str:
    low = fp.name.lower()
    for canon, aliases in MODEL_ALIASES.items():
        for a in aliases:
            if a in low:
                return canon
    return GENERIC

def collect_files_by_model():
    groups = defaultdict(list)
    for fp in DATA_DIR.glob("**/*.md"):
        if is_excluded(fp):
            continue
        model = detect_model_from_path(fp)
        groups[model].append(fp)
    return groups

def create_vector_store(name: str, files: list[Path], *, client: OpenAI) -> str:
    file_objs = []
    for fp in files:
        file_objs.append(client.files.create(file=fp.open("rb"), purpose="assistants"))
    vs = client.beta.vector_stores.create(name=name)
    client.beta.vector_stores.file_batches.upload_and_poll(
        vector_store_id=vs.id,
        files=[f.id for f in file_objs]
    )
    return vs.id


def ensure_vector_stores_by_model() -> dict[str, str]:
    """Her model için ayrı VS kurar veya mevcutları kullanır. {MODEL: vs_id} döner."""
    existing = {}
    if STATE_FILE.exists():
        existing = json.loads(STATE_FILE.read_text())

    groups = collect_files_by_model()
    vs_map: dict[str, str] = {}

    for model, files in groups.items():
        key = f"vs_{model.lower()}"
        vs_id = existing.get(key)
        if not vs_id:
            vs_id = create_vector_store(name=f"{model} KB", files=files)
            existing[key] = vs_id
        vs_map[model] = vs_id

    # Hiç ortak içerik yoksa GENERIC’i model mağazasıyla aynı yapmayın; atlayın
    if GENERIC in groups:
        key = f"vs_{GENERIC.lower()}"
        if key not in existing:
            existing[key] = create_vector_store(name="GENERIC KB", files=groups[GENERIC])
        vs_map[GENERIC] = existing[key]

    STATE_FILE.write_text(json.dumps(existing, indent=2))
    return vs_map
