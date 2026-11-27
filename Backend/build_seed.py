"""Builds hdt.db (SQLite) + seed.json from the team's master crops CSV.
Run:  python3 build_seed.py [path-to-csv] [out-dir] [homegarden_data.db]
Principle: nothing is invented. Fields the sources don't state stay NULL.
Rules/extra species taken from the team's AI-written summary docs are labelled 'hypothesis'."""
import sys, re, csv, json, sqlite3, os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "data", "horta-crops.csv")
OUT = sys.argv[2] if len(sys.argv) > 2 else HERE
HG = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "homegarden_data.db")

LAYERS = [
    ("ground", "Camada rasteira", "Ground layer", 1),
    ("lower_mid", "Camada média-baixa", "Lower mid-layer", 2),
    ("mid", "Camada média", "Mid-layer", 3),
    ("canopy", "Dossel", "Canopy layer", 4),
    ("emergent", "Camada emergente", "Emergent layer", 5),
]
LAYER_MAP = {
    "Ground Layer": "ground",
    "Lower Mid-Layer": "lower_mid",
    "Mid-Layer": "mid",
    "Canopy Layer": "canopy",
    "Emergent Layer": "emergent",
}

SOURCES = [
    ("SRC-T01", "Crops Horta da Terra spreadsheet (team research + EcoCrop/Embrapa)", "Team research",
     "Layer, light, soil, EcoCrop ranges, pathogens, layout, intercropping",
     "Compiled by students from FAO EcoCrop and Embrapa; not yet field-validated with Horta da Terra",
     "https://gaez.fao.org/pages/ecocrop-find-plant"),
    ("SRC-T02", "How El Niño Changes the Agroforestry Plan (team doc, AI-assisted summary)", "Team doc",
     "Scenario rules for drought", "AI-assisted summary; hypothesis until validated with Horta da Terra technicians", None),
    ("SRC-T03", "La Niña Affects Agroforestry (team doc, AI-assisted summary)", "Team doc",
     "Scenario rules for heavy rain", "AI-assisted summary with unverified citations; hypothesis", None),
    ("SRC-T04", "Simple Agroforestry Guide (team doc, AI-assisted summary)", "Team doc",
     "General layering/soil guidance, extra species", "AI-assisted summary; hypothesis", None),
]

def slug(s):
    return re.sub(r"\s+", " ", str(s)).strip() if s is not None else ""

def to_float(v):
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return float(s)
    except ValueError:
        return None

def to_int(v):
    f = to_float(v)
    return int(f) if f is not None else None

def norm_key(s):
    s = slug(s).lower()
    for a, b in [("á","a"),("à","a"),("â","a"),("ã","a"),("é","e"),("ê","e"),
                 ("í","i"),("ó","o"),("ô","o"),("õ","o"),("ú","u"),("ç","c")]:
        s = s.replace(a, b)
    return s

sources = list(SOURCES)

# --- 1. Load species directly from CSV (no hardcoded overrides) ---
rows = []
with open(CSV_PATH, mode="r", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        crop_raw = slug(r.get("Crop"))
        if not crop_raw:
            continue
        m = re.match(r"(.*?)\s*\((.*)\)\s*$", crop_raw)
        common = slug(m.group(1)) if m else crop_raw
        sci = slug(r.get("Scientific Name")) or (slug(m.group(2)) if m else None)
        layer_raw = slug(r.get("Stratum Layer"))
        if layer_raw not in LAYER_MAP:
            raise ValueError(f"Unknown Stratum Layer '{layer_raw}' for crop '{crop_raw}'")
        rows.append(dict(layer=LAYER_MAP[layer_raw], common=common, sci=sci, raw=r))

# Keep SP-0001..0006 aligned with partner report species
PRESET = {
    "Acmella oleracea": "SP-0001",
    "Eryngium foetidum": "SP-0002",
    "Eryngium foetidum L.": "SP-0002",
    "Talinum triangulare": "SP-0003",
    "Talinum triangulare (syn. Talinum fruticosum)": "SP-0003",
    "Pereskia aculeata": "SP-0004",
    "Hibiscus sabdariffa": "SP-0005",
    "Xanthosoma sagittifolium": "SP-0006",
}
GROWN = set(PRESET)
PT_NAMES = {"Chicoria": "Chicória", "Parica": "Paricá", "Espinafre": "Espinafre", "Batata Aria": "Batata-ariá"}

species = []
n = 7
for d in rows:
    sid = PRESET.get(d["sci"]) or f"SP-{n:04d}"
    if sid.startswith("SP-") and sid not in PRESET.values():
        n += 1
    r = d["raw"]
    is_panc = 1 if slug(r.get("Is PANC")).lower() == "yes" else 0
    opt_rain_min = to_float(r.get("Opt. Rain Min (mm)"))
    default_water = "high" if (opt_rain_min and opt_rain_min >= 1800) else ("medium" if (opt_rain_min and opt_rain_min >= 1000) else "unknown")

    light_txt = slug(r.get("Ideal Light Conditions")) or None
    soil_txt = slug(r.get("Ideal Soil Conditions")) or None
    harvest_txt = slug(r.get("Harvest Time")) or None
    yield_txt = slug(r.get("Yield / Year")) or None

    species.append(dict(
        id=sid,
        common_name_pt=PT_NAMES.get(d["common"], d["common"]),
        scientific_name=d["sci"],
        layer_id=d["layer"],
        succession_stage=slug(r.get("Succession Stage")) or None,
        role_in_system=slug(r.get("Soil & Farm Role")) or None,
        is_panc=is_panc,
        grown_by_hdt=int(d["sci"] in GROWN),
        ecocrop_id=to_int(r.get("EcoCrop ID")),
        shade_tolerance=slug(r.get("Shade Tolerance")) or None,
        drainage_requirement=slug(r.get("Drainage Requirement")) or None,
        opt_temp_min=to_float(r.get("Opt. Temp Min (°C)")),
        opt_temp_max=to_float(r.get("Opt. Temp Max (°C)")),
        abs_temp_min=to_float(r.get("Abs. Temp Min (°C)")),
        abs_temp_max=to_float(r.get("Abs. Temp Max (°C)")),
        opt_rain_min=opt_rain_min,
        opt_rain_max=to_float(r.get("Opt. Rain Max (mm)")),
        abs_rain_min=to_float(r.get("Abs. Rain Min (mm)")),
        abs_rain_max=to_float(r.get("Abs. Rain Max (mm)")),
        light_pt=light_txt,
        light_en=light_txt,
        soil_pt=soil_txt,
        soil_en=soil_txt,
        water_need=default_water,
        drought_tolerance="unknown",
        shade_min_pct=None,
        shade_max_pct=None,
        soil_ph_min=to_float(r.get("Opt. pH Min")),
        soil_ph_max=to_float(r.get("Opt. pH Max")),
        abs_ph_min=to_float(r.get("Abs. pH Min")),
        abs_ph_max=to_float(r.get("Abs. pH Max")),
        first_harvest_days=None,
        harvest_notes_pt=harvest_txt,
        harvest_notes_en=harvest_txt,
        yield_notes=yield_txt,
        yield_notes_en=yield_txt,
        pathogens_notes=slug(r.get("Pathogens")) or None,
        layout_notes=slug(r.get("Layout")) or None,
        evidence_status="company_reported" if d["sci"] in GROWN else "published_research",
        source_id="SRC-T01",
        source_url=slug(r.get("Sources")) or None,
        raw_source_row=json.dumps({k: v for k, v in r.items() if v}, ensure_ascii=False),
        notes=("Possível duplicata de Paricá (mesma espécie, Schizolobium parahyba) — confirmar com a equipe." if d["sci"] == "Schizolobium parahyba" else None),
        notes_en=("Possible duplicate of Paricá (same species, Schizolobium parahyba) — confirm with the team." if d["sci"] == "Schizolobium parahyba" else None),
    ))

# --- 2. Extra hypothesis species from team docs (only if not already in CSV) ---
existing_sci = {norm_key(s["scientific_name"]) for s in species if s["scientific_name"]}
EXTRA = [
    ("Cacau", "Theobroma cacao", "mid", "medium", "Plantas jovens precisam de sombra e proteção contra seca"),
    ("Feijão-guandu", "Cajanus cajan", "lower_mid", "unknown", "Adubo verde: cortar e deixar sobre o solo"),
    ("Crotalária", "Crotalaria spp.", "ground", "unknown", "Adubo verde / fixadora de nitrogênio"),
    ("Pimenta-do-reino", "Piper nigrum", "mid", "unknown", "Pode crescer sob plantas mais altas"),
]
NOTES_EN = {
    "Cacau": "Young plants need shade and protection from drought",
    "Feijão-guandu": "Green manure: cut and leave on the soil",
    "Crotalária": "Green manure / nitrogen fixer",
    "Pimenta-do-reino": "Can grow beneath taller plants",
}
for common, sci, layer, water, note in EXTRA:
    if norm_key(sci) in existing_sci:
        continue
    sid = f"SP-{n:04d}"; n += 1
    species.append(dict(
        id=sid, common_name_pt=common, scientific_name=sci, layer_id=layer,
        succession_stage=None, role_in_system=None, is_panc=0, grown_by_hdt=0,
        ecocrop_id=None, shade_tolerance=None, drainage_requirement=None,
        opt_temp_min=None, opt_temp_max=None, abs_temp_min=None, abs_temp_max=None,
        opt_rain_min=None, opt_rain_max=None, abs_rain_min=None, abs_rain_max=None,
        light_pt=None, light_en=None, soil_pt=None, soil_en=None,
        water_need=water, drought_tolerance="unknown", shade_min_pct=None, shade_max_pct=None,
        soil_ph_min=None, soil_ph_max=None, abs_ph_min=None, abs_ph_max=None,
        first_harvest_days=None, harvest_notes_pt=None, harvest_notes_en=None,
        yield_notes=None, yield_notes_en=None, pathogens_notes=None, layout_notes=None,
        evidence_status="hypothesis", source_id="SRC-T04", source_url=None,
        raw_source_row=None, notes=note, notes_en=NOTES_EN[common],
    ))

# --- 3. Parse & link companions cleanly ---
# Build token -> species_id lookup so companions can link to real IDs
token_to_id = {}
for s in species:
    for part in re.split(r"[/,()]+", s["common_name_pt"]):
        t = norm_key(part).split()[0] if norm_key(part) else ""
        if len(t) >= 4:
            token_to_id.setdefault(t, s["id"])
    if s["scientific_name"]:
        token_to_id.setdefault(norm_key(s["scientific_name"]), s["id"])

SKIP_PHRASES = ("not documented", "n/a", "none", "unknown")

def parse_partner_items(text):
    if not text:
        return []
    raw_items = re.split(r"[;\n]+|,\s*(?![^()]*\))", text)
    cleaned = []
    for item in raw_items:
        item = slug(item).strip(".")
        low = norm_key(item)
        if not item or any(low == p or low.startswith(p + " ") for p in SKIP_PHRASES):
            continue
        cleaned.append(item)
    return cleaned

def match_partner_id(label, self_id):
    low = norm_key(label)
    for tok, sid in token_to_id.items():
        if sid != self_id and tok in low:
            return sid
    return None

relations = []
for s, d in zip(species[:len(rows)], rows):
    r = d["raw"]
    for col, rtype in (("Intercrop", "intercrop"), ("Companion Plants", "companion"), ("Trees", "plant_under")):
        for item in parse_partner_items(slug(r.get(col))):
            relations.append(dict(
                id=f"REL-{len(relations)+1:04d}",
                species_a_id=s["id"],
                species_b_id=match_partner_id(item, s["id"]),
                species_b_label=item,
                relation_type=rtype,
                note=None,
                evidence_status="published_research",
                source_id="SRC-T01",
            ))

# --- 4. Safe species lookup for rules (never crashes on synonym/CSV moves) ---
def find_sp(name_or_sci):
    target = norm_key(name_or_sci)
    for s in species:
        if norm_key(s["common_name_pt"]) == target or norm_key(s["scientific_name"]) == target:
            return s["id"]
    for s in species:
        if target in norm_key(s["common_name_pt"]) or target in norm_key(s["scientific_name"]):
            return s["id"]
    return None

# --- 5. Homegarden survey (optional) ---
survey_rows = []
if os.path.exists(HG):
    def keyof(sci):
        w = re.sub(r"[()]", " ", (sci or "").lower()).split()
        if not w: return None
        return (w[0], None) if len(w) < 2 or w[1] in ("sp", "sp.", "spp", "spp.") else (w[0], w[1].strip("."))
    sp_key = {}
    for s in species:
        k = keyof(s["scientific_name"])
        if k: sp_key[k] = s["id"]
    ALIAS = {("hibiscus", "sabdafira"): "SP-0005", ("spilanthes", "oleraceae"): "SP-0001"}
    _g = {}
    for s in species:
        k = keyof(s["scientific_name"])
        if k and k[1]: _g.setdefault(k[0], []).append(s["id"])
    genus_map = {g: v[0] for g, v in _g.items() if len(v) == 1}
    hg = sqlite3.connect(HG); T = "Dados_disponiveis_EN"
    groups = {}
    for mun, zone, common, sci, fam, hab, org, use in hg.execute(f'SELECT "Municipality","Zone","Common Name","Scientific name","Family","Growth habit","Origin","Use" FROM {T}'):
        if not sci or not sci.strip(): continue
        g = groups.setdefault(" ".join(sci.split()), dict(mun=set(), zones=Counter(), common=Counter(), fam=fam, hab=Counter(), org=Counter(), use=Counter(), n=0))
        g["mun"].add(mun); g["zones"][zone] += 1; g["common"][(common or "").strip()] += 1; g["hab"][hab] += 1; g["org"][org] += 1; g["use"][use] += 1; g["n"] += 1
    for sci, g in groups.items():
        k = keyof(sci)
        sid = (ALIAS.get(k) or sp_key.get(k) or (genus_map.get(k[0]) if k[1] is None else None) or sp_key.get((k[0], None))) if k else None
        survey_rows.append((sci, g["common"].most_common(1)[0][0], g["fam"], g["hab"].most_common(1)[0][0], g["org"].most_common(1)[0][0],
                            g["use"].most_common(1)[0][0], g["n"], len(g["mun"]), ", ".join(z for z, _ in g["zones"].most_common()), sid))

# --- 6. Transparent management rules ---
RULES = [
    ("R-001","el_nino",{"water_access":["rain_only","unknown"]},find_sp("Açaí"),"conditional",
     "El Niño: açaí precisa de muita água. Plante só onde houver água confiável ou espere a chuva melhorar.","SRC-T02"),
    ("R-002","el_nino",{},find_sp("Cacau"),"conditional","El Niño: cacau pode dar certo, mas as mudas novas precisam de sombra e proteção contra a seca.","SRC-T02"),
    ("R-003","el_nino",{},find_sp("Cupuaçu"),"conditional","El Niño: cupuaçu pode precisar de mais sombra e água nos períodos secos.","SRC-T02"),
    ("R-004","any",{},find_sp("Ingá-cipó"),"prefer","Ingá dá sombra, protege o solo e os galhos podados viram cobertura (mulch).","SRC-T02"),
    ("R-005","any",{},find_sp("Feijão-guandu"),"prefer","Guandu: cortar e deixar sobre o solo devolve matéria orgânica e protege contra o sol.","SRC-T04"),
    ("R-006","any",{},None,"practice","Mantenha o solo sempre coberto (folhas, galhos, mulch, plantas baixas). Solo nu esquenta e seca mais rápido.","SRC-T02"),
    ("R-007","el_nino",{},None,"practice","Plante quando houver chuva e umidade no solo — não só pelo calendário. Mudas novas sofrem mais com a seca.","SRC-T02"),
    ("R-008","el_nino",{},None,"practice","Risco de fogo: mantenha aceiros limpos de material seco e deixe água disponível para emergência.","SRC-T02"),
    ("R-009","la_nina",{},find_sp("Cacau"),"conditional","La Niña: mais risco de fungos no cacau (vassoura-de-bruxa, podridão-parda). Pode o dossel para circular o ar.","SRC-T03"),
    ("R-010","la_nina",{},find_sp("Acmella oleracea"),"conditional","Com menos circulação de ar o jambu sofre com fungos (ferrugem-branca, manchas, podridão). Solução da planilha: podar as árvores.","SRC-T01"),
    ("R-011","la_nina",{},None,"practice","Chuva forte atrapalha colheita e transporte, principalmente em várzea. Planeje o escoamento e colha antes dos picos.","SRC-T03"),
    ("R-012","any",{"canopy":["low"]},find_sp("Eryngium foetidum"),"conditional","Chicória prefere 30–70% de sombra; sol pleno estressa e faz a planta florescer cedo. Plante sob árvores.","SRC-T01"),
    ("R-013","any",{"canopy":["low"]},find_sp("Talinum triangulare"),"conditional","Cariru sofre com sol pleno na seca. Prefira sob copa média/alta (bananeira, ingá).","SRC-T01"),
    ("R-014","any",{"canopy":["low"]},find_sp("Acmella oleracea"),"conditional","Jambu prefere meia-sombra; evite sol forte do meio-dia. Plante sob açaí, cupuaçu ou cacau.","SRC-T01"),
    ("R-015","any",{},None,"practice","Faça análise de solo antes de plantar. O solo da região é ácido e pobre; calagem e fósforo só conforme o resultado.","SRC-T04"),
]

RULES_EN = {
    "R-001": "El Niño: açaí needs a lot of water. Plant it only where water is reliable, or wait for rainfall to improve.",
    "R-002": "El Niño: cacao can work, but young seedlings need shade and protection from drought.",
    "R-003": "El Niño: cupuaçu may need more shade and water during dry periods.",
    "R-004": "Ingá gives shade, protects the soil, and pruned branches become mulch.",
    "R-005": "Pigeon pea (guandu): cutting it and leaving it on the soil returns organic matter and protects against the sun.",
    "R-006": "Keep the soil covered at all times (leaves, branches, mulch, low plants). Bare soil heats up and dries out faster.",
    "R-007": "Plant when there is rain and moisture in the soil, not just by the calendar. Young seedlings suffer most from drought.",
    "R-008": "Fire risk: keep firebreaks clear of dry material and keep water available for emergencies.",
    "R-009": "La Niña: higher risk of fungal disease in cacao (witches' broom, black pod rot). Prune the canopy so air can circulate.",
    "R-010": "With less air circulation, jambu suffers from fungi (white rust, leaf spots, rot). Fix from the team sheet: prune the trees.",
    "R-011": "Heavy rain disrupts harvest and transport, especially in floodplain (várzea) areas. Plan how to get produce out and harvest before the peaks.",
    "R-012": "Chicória prefers 30–70% shade; full sun stresses it and makes it flower early. Plant under trees.",
    "R-013": "Cariru suffers in full sun during the dry season. Prefer planting under a medium or high canopy (banana, ingá).",
    "R-014": "Jambu prefers partial shade; avoid strong midday sun. Plant under açaí, cupuaçu or cacao.",
    "R-015": "Test the soil before planting. Soils in the region are acidic and poor; add lime and phosphorus only according to the result.",
}

# --- 7. Write SQLite + seed.json ---
os.makedirs(OUT, exist_ok=True)
dbp = f"{OUT}/hdt.db"
if os.path.exists(dbp):
    os.remove(dbp)
con = sqlite3.connect(dbp)
con.executescript(open(f"{HERE}/schema.sql", encoding="utf-8").read())
con.executemany("INSERT INTO source VALUES (?,?,?,?,?,?)", sources)
con.executemany("INSERT INTO layer VALUES (?,?,?,?)", LAYERS)

SP_COLS = [
    "id","common_name_pt","scientific_name","layer_id","succession_stage","role_in_system","is_panc","grown_by_hdt",
    "ecocrop_id","shade_tolerance","drainage_requirement","opt_temp_min","opt_temp_max","abs_temp_min","abs_temp_max",
    "opt_rain_min","opt_rain_max","abs_rain_min","abs_rain_max","light_pt","light_en","soil_pt","soil_en","water_need","drought_tolerance",
    "shade_min_pct","shade_max_pct","soil_ph_min","soil_ph_max","abs_ph_min","abs_ph_max","first_harvest_days","harvest_notes_pt","harvest_notes_en",
    "yield_notes","yield_notes_en","pathogens_notes","layout_notes","evidence_status","source_id","source_url","raw_source_row","notes","notes_en",
]
con.executemany(
    f"INSERT INTO species ({','.join(SP_COLS)}) VALUES ({','.join('?'*len(SP_COLS))})",
    [[s[c] for c in SP_COLS] for s in species],
)
con.executemany(
    "INSERT INTO species_relation (id,species_a_id,species_b_id,species_b_label,relation_type,note,evidence_status,source_id) VALUES (?,?,?,?,?,?,?,?)",
    [[r[k] for k in ("id","species_a_id","species_b_id","species_b_label","relation_type","note","evidence_status","source_id")] for r in relations],
)
con.executemany(
    "INSERT INTO rule (id,scenario,condition_json,species_id,action,message_pt,message_en,evidence_status,source_id) VALUES (?,?,?,?,?,?,?,'hypothesis',?)",
    [(r[0], r[1], json.dumps(r[2]), r[3], r[4], r[5], RULES_EN[r[0]], r[6]) for r in RULES],
)
con.execute("INSERT INTO site (id,farm_code,municipality,state,water_access,current_land_use,consent_for_data_use,updated_at) VALUES ('SITE-0001','HDT-MAIN (confirmar limites)','Santo Antônio do Tauá','PA','unknown','Agrofloresta regenerativa (modelo)','not_obtained',datetime('now'))")
con.commit()

if survey_rows:
    con.executemany("INSERT INTO homegarden_survey VALUES (?,?,?,?,?,?,?,?,?,?)", survey_rows)
    con.commit()

def q(sql):
    cur = con.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

seed = dict(
    layers=q("SELECT * FROM layer ORDER BY sort"),
    species=q("SELECT * FROM species ORDER BY id"),
    relations=q("SELECT * FROM species_relation"),
    rules=[dict(r, condition=json.loads(r.pop("condition_json"))) for r in q("SELECT * FROM rule")],
    sources=q("SELECT * FROM source"),
    survey_matches=q("SELECT species_id, scientific_name, n_records, n_municipalities, origin, use FROM homegarden_survey WHERE species_id IS NOT NULL"),
    survey_candidates=q("SELECT scientific_name, common_name, family, growth_habit, origin, use, n_records, n_municipalities FROM homegarden_survey WHERE species_id IS NULL AND use IN ('Food','Food/Medicinal','Shading') AND n_records >= 25 ORDER BY n_records DESC LIMIT 40"),
    sites=q("SELECT id,farm_code,municipality,state,water_access FROM site"),
)
json.dump(seed, open(f"{OUT}/seed.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print({t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("source","layer","species","species_relation","rule","site","homegarden_survey")})