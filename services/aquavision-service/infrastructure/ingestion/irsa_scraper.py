# infrastructure/ingestion/irsa_scraper.py
# Parse IRSA Daily Water Situation PDFs into structured observations.
# Handles the two-column PDF layout where pdfplumber merges left/right columns.
import logging
import re
import io
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Dict
import pdfplumber

logger = logging.getLogger("aquavision.ingest.irsa")


@dataclass
class IRSAObservation:
    asset_name: str
    asset_type: str
    observed_at: date
    water_level_ft: Optional[float] = None
    dead_level_ft: Optional[float] = None
    inflow_cusecs: Optional[float] = None
    outflow_cusecs: Optional[float] = None
    upstream_discharge_cusecs: Optional[float] = None
    downstream_discharge_cusecs: Optional[float] = None
    discharge_cusecs: Optional[float] = None
    provincial_releases: Dict[str, float] = field(default_factory=dict)
    # Canal offtakes at this structure, in cusecs. Keys are canal names as
    # printed in the report ("Dera Ghazi Khan Canal", "C-J Link"); the special
    # key "_total" holds the aggregate "Canal W/dls" figure where given.
    canal_withdrawals: Dict[str, float] = field(default_factory=dict)
    source_url: str = ""
    raw_text: str = ""


def _c(s: str) -> Optional[float]:
    if not s:
        return None
    s = s.replace(",", "").replace("Cs", "").replace("cs", "").replace("*", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _find(pattern, text, flags=0):
    m = re.search(pattern, text, flags)
    return _c(m.group(1)) if m else None


# ─── Column-aware block parsing ─────────────────────────────────────────────
#
# The IRSA report is laid out in TWO COLUMNS. pdfplumber's page-level
# extract_text() concatenates them line by line, so a single output line can
# carry Taunsa's canal on the left and Guddu's withdrawals on the right:
#
#   "Muzafarghar Canal = 0 Cs * Canal W/dls = 33875 Cs"
#
# Regexes written against that merged text mis-attribute values between the
# columns, which is why six of eleven assets were parsing to empty rows.
# Cropping each page at the column boundary first makes every station a clean
# contiguous block, and makes canal lines attributable to the structure that
# owns them.

COLUMN_SPLIT_X = 300  # page width is 612pt; the gutter sits at the midpoint

# Header text -> (canonical asset name, asset type). Order matters: longer,
# more specific headers must be tested before their prefixes.
STATION_HEADERS = [
    ("INDUS @ TARBELA", "Tarbela Reservoir", "reservoir"),
    ("KABUL @ NOWSHERA", "Kabul @ Nowshera", "river_station"),
    ("JHELUM @ MANGLA", "Mangla Reservoir", "reservoir"),
    ("CHENAB @ MARALA", "Chenab @ Marala", "river_station"),
    ("KALABAGH", "Kalabagh (Indus)", "barrage"),
    ("CHASHMA", "Chashma Barrage", "barrage"),
    ("TAUNSA", "Taunsa Barrage", "barrage"),
    ("GUDDU", "Guddu Barrage", "barrage"),
    ("SUKKUR", "Sukkur Barrage", "barrage"),
    ("KOTRI", "Kotri Barrage", "barrage"),
    ("PANJNAD", "Panjnad", "river_station"),
]

# Lines matching these are readings, not canals.
_METRIC_PATTERNS = [
    (r"^DEAD LEVEL\s*=\s*([\d.,]+)", "dead_level_ft"),
    (r"^LEVEL\s*=\s*([\d.,]+)", "water_level_ft"),
    (r"^MEAN INFLOW\s*=\s*([\d.,]+)", "inflow_cusecs"),
    (r"^MEAN OUTFLOW\s*=\s*([\d.,]+)", "outflow_cusecs"),
    (r"^MEAN DISCHARGE\s*=\s*([\d.,]+)", "discharge_cusecs"),
    (r"^MEAN U/S DISCHARGE\s*=\s*([\d.,]+)", "upstream_discharge_cusecs"),
    (r"^MEAN D/S DISCHARGE\s*=\s*([\d.,]+)", "downstream_discharge_cusecs"),
    (r"^U/S DISCHARGE\s*=\s*([\d.,]+)", "upstream_discharge_cusecs"),
    (r"^D/S DISCHARGE\s*=\s*([\d.,]+)", "downstream_discharge_cusecs"),
]

# Labels that look like "<name> = <n> Cs" but are report furniture, not canals.
_NOT_CANALS = {
    "TOTAL", "MEAN DISCHARGE", "MEAN INFLOW", "MEAN OUTFLOW", "LEVEL",
    "DEAD LEVEL", "DISCHARGE", "INFLOW", "OUTFLOW",
}

# Aggregate canal withdrawal for a whole structure, rather than a named canal.
_CANAL_TOTAL_RE = re.compile(r"^\*?\s*Canal\s*W/dls\s*=\s*([\d.,]+)", re.IGNORECASE)
# A named offtake: "Dera Ghazi Khan Canal = 8100 Cs", "C-J Link = 13000 Cs".
_CANAL_NAMED_RE = re.compile(r"^\*?\s*([A-Za-z][A-Za-z0-9 ()\-/&.']*?)\s*=\s*([\d.,]+)\s*Cs", re.IGNORECASE)


def extract_column_text(pdf) -> str:
    """Text with the two columns separated, left column first then right.

    Returns one string with a form-feed between columns so downstream block
    splitting never runs a left-column station into a right-column one.
    """
    parts = []
    for page in pdf.pages:
        for x0, x1 in ((0, COLUMN_SPLIT_X), (COLUMN_SPLIT_X, page.width)):
            cropped = page.crop((x0, 0, x1, page.height))
            parts.append(cropped.extract_text() or "")
    return "\n\f\n".join(parts)


def _match_header(line: str):
    """Return (asset_name, asset_type) if this line starts a station block."""
    upper = line.strip().upper().rstrip(":").strip()
    for header, name, atype in STATION_HEADERS:
        if upper == header or upper.startswith(header + " ") or upper.startswith(header + ":"):
            return name, atype
    return None


def split_station_blocks(column_text: str) -> dict:
    """Group column text into {asset_name: (asset_type, [lines])}.

    A block runs from its header to the next header or column break.
    """
    blocks: dict = {}
    current = None
    for raw in column_text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line == "\f":
            current = None
            continue
        hit = _match_header(line)
        if hit:
            name, atype = hit
            current = name
            blocks.setdefault(name, (atype, []))
            # A header may carry its first reading inline ("PANJNAD U/S = ...").
            remainder = line.split(":", 1)[1].strip() if ":" in line else ""
            if remainder:
                blocks[name][1].append(remainder)
            continue
        if current:
            blocks[current][1].append(line)
    return blocks


def parse_block(lines: list) -> tuple:
    """Split one station's lines into (readings, canal_withdrawals).

    Anything of the form "<name> = <number> Cs" that is not a known metric is
    treated as a canal offtake - which is exactly how the report lists them.
    """
    readings: dict = {}
    canals: dict = {}

    for line in lines:
        text = line.strip()

        total = _CANAL_TOTAL_RE.match(text)
        if total:
            canals["_total"] = _c(total.group(1))
            continue

        matched_metric = False
        for pattern, field_name in _METRIC_PATTERNS:
            m = re.match(pattern, text, re.IGNORECASE)
            if m:
                if field_name not in readings:  # first occurrence wins
                    readings[field_name] = _c(m.group(1))
                matched_metric = True
                break
        if matched_metric:
            continue

        named = _CANAL_NAMED_RE.match(text)
        if named:
            label = named.group(1).strip()
            upper = label.upper()
            # Guard against prose, report furniture and stray headings. Without
            # this, "TOTAL = ..." and "MEAN D/S DISCHARGE = ..." are read as canals.
            if (1 <= len(label.split()) <= 5
                    and upper not in _NOT_CANALS
                    and not upper.startswith(("TODAY", "RIM", "NOTE", "MEAN ", "TOTAL"))):
                canals[label] = _c(named.group(2))

    return readings, canals


class IRSAParser:
    def parse(self, pdf_bytes: bytes, source_url: str, target_date: date) -> List[IRSAObservation]:
        full_text = ""
        column_text = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                full_text += (page.extract_text() or "") + "\n"
            try:
                column_text = extract_column_text(pdf)
            except Exception as exc:  # noqa: BLE001 - never lose the legacy path
                logger.warning("Column extraction failed, using merged text only: %s", exc)

        obs: List[IRSAObservation] = []
        t = full_text

        # Column-aware pass. Runs first so its cleanly attributed values can be
        # merged over the legacy regex results, which mis-assign across columns.
        block_data = {}
        if column_text:
            for name, (atype, lines) in split_station_blocks(column_text).items():
                readings, canals = parse_block(lines)
                if readings or canals:
                    block_data[name] = (atype, readings, canals)

        # ================================================================
        # TARBELA
        # ================================================================
        tl = _find(r"LEVEL\s*=\s*([\d.]+)\s+MEAN DISCHARGE", t)
        td = _find(r"INDUS\s*@\s*TARBELA.*?DEAD LEVEL\s*=\s*([\d.]+)", t, re.DOTALL | re.IGNORECASE)
        ti = _find(r"INDUS\s*@\s*TARBELA.*?MEAN INFLOW\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        to_ = _find(r"INDUS\s*@\s*TARBELA.*?MEAN OUTFLOW\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        if tl:
            obs.append(IRSAObservation(
                asset_name="Tarbela Reservoir", asset_type="reservoir", observed_at=target_date,
                water_level_ft=tl, dead_level_ft=td, inflow_cusecs=ti, outflow_cusecs=to_,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ================================================================
        # KABUL @ NOWSHERA
        # ================================================================
        kd = _find(r"KABUL\s*@\s*NOWSHERA.*?MEAN DISCHARGE\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        if kd:
            obs.append(IRSAObservation(
                asset_name="Kabul @ Nowshera", asset_type="river_station", observed_at=target_date,
                discharge_cusecs=kd, source_url=source_url, raw_text=t[:4000],
            ))

        # ================================================================
        # CHASHMA + KALABAGH (merged two-column block)
        # Block from CHASHMA: to TAUNSA:
        # In the merged text, Chashma's U/S and D/S appear on lines that also
        # contain Kalabagh data (right column). We extract Chashma's values as
        # the FIRST U/S and D/S in the block, and Kalabagh's LEVEL/INFLOW/OUTFLOW
        # from the KALABAGH section.
        # ================================================================
        ck_block_match = re.search(r"CHASHMA\s*:(.+?)(?:TAUNSA|CHENAB)", t, re.DOTALL | re.IGNORECASE)
        if ck_block_match:
            block = ck_block_match.group(1)

            # Chashma: first U/S and D/S in block (left column values)
            ch_us_all = re.findall(r"U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)
            ch_ds_all = re.findall(r"D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)
            ch_us = _c(ch_us_all[0]) if ch_us_all else None
            ch_ds = _c(ch_ds_all[0]) if ch_ds_all else None
            ch_dead = _find(r"DEAD LEVEL\s*=\s*([\d.]+)", block, re.IGNORECASE)

            if ch_us or ch_ds:
                obs.append(IRSAObservation(
                    asset_name="Chashma Barrage", asset_type="barrage", observed_at=target_date,
                    upstream_discharge_cusecs=ch_us, downstream_discharge_cusecs=ch_ds,
                    dead_level_ft=ch_dead,
                    source_url=source_url, raw_text=t[:4000],
                ))

            # Kalabagh: LEVEL, DEAD LEVEL, INFLOW, OUTFLOW from the block
            ka_level = _find(r"KALABAGH.*?LEVEL\s*=\s*([\d.]+)", block, re.DOTALL | re.IGNORECASE)
            if ka_level is None:
                ka_level = _find(r"LEVEL\s*=\s*([\d.]+)", block)
            ka_dead_all = re.findall(r"DEAD LEVEL\s*=\s*([\d.]+)", block, re.IGNORECASE)
            ka_dead = _c(ka_dead_all[1]) if len(ka_dead_all) > 1 else (_c(ka_dead_all[0]) if ka_dead_all else None)
            ka_inf = _find(r"MEAN INFLOW\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)
            ka_outf = _find(r"MEAN OUTFLOW\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)

            if ka_level or ka_inf or ka_outf:
                obs.append(IRSAObservation(
                    asset_name="Kalabagh (Indus)", asset_type="river_station", observed_at=target_date,
                    water_level_ft=ka_level, dead_level_ft=ka_dead,
                    inflow_cusecs=ka_inf, outflow_cusecs=ka_outf,
                    source_url=source_url, raw_text=t[:4000],
                ))

        # ================================================================
        # TAUNSA + GUDDU (merged two-column block)
        # Merged: "TAUNSA:\nU/S DISCHARGE = 238045 Cs GUDDU:\nD/S DISCHARGE = 224145 Cs U/S DISCHARGE = 209206 Cs"
        # ================================================================
        tg_block_match = re.search(r"TAUNSA\s*:?\s*(.+?)(?:KOTRI|SUKKUR|CHENAB)", t, re.DOTALL | re.IGNORECASE)
        if tg_block_match:
            block = tg_block_match.group(1)
            guddu_pos = re.search(r"GUDDU\s*:", block, re.IGNORECASE)

            if guddu_pos:
                taunsa_section = block[:guddu_pos.start()]
                guddu_section = block[guddu_pos.start():]
            else:
                taunsa_section = block
                guddu_section = ""

            # --- Taunsa ---
            taunsa_us = _find(r"U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", taunsa_section, re.IGNORECASE)
            # Taunsa D/S is the first D/S in the GUDDU section (it's Taunsa's D/S in the left column)
            taunsa_ds = None
            if guddu_section:
                ds_in_guddu = re.findall(r"D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", guddu_section, re.IGNORECASE)
                taunsa_ds = _c(ds_in_guddu[0]) if ds_in_guddu else None
            if taunsa_us or taunsa_ds:
                obs.append(IRSAObservation(
                    asset_name="Taunsa Barrage", asset_type="barrage", observed_at=target_date,
                    upstream_discharge_cusecs=taunsa_us, downstream_discharge_cusecs=taunsa_ds,
                    source_url=source_url, raw_text=t[:4000],
                ))

            # --- Guddu ---
            guddu_us = _find(r"U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", guddu_section, re.IGNORECASE)
            # Guddu D/S is the LAST D/S in the section (not Taunsa's)
            guddu_ds_all = re.findall(r"D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", guddu_section, re.IGNORECASE)
            guddu_ds = _c(guddu_ds_all[-1]) if guddu_ds_all else None
            if guddu_us or guddu_ds:
                obs.append(IRSAObservation(
                    asset_name="Guddu Barrage", asset_type="barrage", observed_at=target_date,
                    upstream_discharge_cusecs=guddu_us, downstream_discharge_cusecs=guddu_ds,
                    source_url=source_url, raw_text=t[:4000],
                ))

        # ================================================================
        # SUKKUR + KOTRI (merged two-column block)
        # "KOTRI:\nSUKKUR: U/S DISCHARGE = 153592 Cs\nU/S DISCHARGE = 199130 Cs D/S DISCHARGE = 111427 Cs\n..."
        # Kotri: header appears BEFORE Sukkur in merged text.
        # In the block: 2 U/S values, 2 D/S values.
        #   Sukkur: U/S=153592 (header line), D/S=111427
        #   Kotri: U/S=199130, D/S=145110
        # ================================================================
        # Find from KOTRI: to CHENAB (KOTRI header appears before SUKKUR)
        kotri_block_match = re.search(r"KOTRI\s*:?\s*(.+?)(?:CHENAB)", t, re.DOTALL | re.IGNORECASE)
        if kotri_block_match:
            block = kotri_block_match.group(1)
            us_all = re.findall(r"U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)
            ds_all = re.findall(r"D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)

            # Sukkur: first U/S (header line), first D/S
            sukkur_us = _c(us_all[0]) if us_all else None
            sukkur_ds = _c(ds_all[0]) if ds_all else None
            if sukkur_us or sukkur_ds:
                obs.append(IRSAObservation(
                    asset_name="Sukkur Barrage", asset_type="barrage", observed_at=target_date,
                    upstream_discharge_cusecs=sukkur_us, downstream_discharge_cusecs=sukkur_ds,
                    source_url=source_url, raw_text=t[:4000],
                ))

            # Kotri: second U/S, second D/S
            kotri_us = _c(us_all[1]) if len(us_all) > 1 else None
            kotri_ds = _c(ds_all[1]) if len(ds_all) > 1 else None
            if kotri_us or kotri_ds:
                obs.append(IRSAObservation(
                    asset_name="Kotri Barrage", asset_type="barrage", observed_at=target_date,
                    upstream_discharge_cusecs=kotri_us, downstream_discharge_cusecs=kotri_ds,
                    source_url=source_url, raw_text=t[:4000],
                ))

        # ================================================================
        # CHENAB @ MARALA + JHELUM @ MANGLA (merged two-column block)
        # "CHENAB @ MARALA:\nJHELUM @ MANGLA: MEAN U/S DISCHARGE = 87401 Cs\n..."
        # Chenab @ Marala has no discharge data in this text (header only).
        # Mangla: LEVEL, DEAD LEVEL, INFLOW, OUTFLOW from right column.
        # ================================================================
        cm_block_match = re.search(
            r"CHENAB\s*@\s*MARALA\s*:?\s*(.+?)(?:PANJNAD)",
            t, re.DOTALL | re.IGNORECASE
        )
        if cm_block_match:
            block = cm_block_match.group(1)

            # Mangla data (right column): LEVEL, DEAD LEVEL, INFLOW, OUTFLOW
            mangla_level = _find(r"LEVEL\s*=\s*([\d.]+)", block, re.IGNORECASE)
            mangla_dead = _find(r"DEAD LEVEL\s*=\s*([\d.]+)", block, re.IGNORECASE)
            mangla_inf = _find(r"MEAN INFLOW\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)
            mangla_outf = _find(r"MEAN OUTFLOW\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)

            if mangla_level or mangla_inf or mangla_outf:
                obs.append(IRSAObservation(
                    asset_name="Mangla Reservoir", asset_type="reservoir", observed_at=target_date,
                    water_level_ft=mangla_level, dead_level_ft=mangla_dead,
                    inflow_cusecs=mangla_inf, outflow_cusecs=mangla_outf,
                    source_url=source_url, raw_text=t[:4000],
                ))

        # ================================================================
        # CHENAB @ MARALA (separate search)
        # The header "CHENAB @ MARALA:" may have US/DS on next lines
        # before JHELUM @ MANGLA starts
        # ================================================================
        # Search for CHENAB @ MARALA up to JHELUM @ MANGLA
        chenab_us = None
        chenab_ds = None
        chenab_section_match = re.search(
            r"CHENAB\s*@\s*MARALA\s*:?\s*(.+?)(?:JHELUM|MANGLA)",
            t, re.DOTALL | re.IGNORECASE
        )
        if chenab_section_match:
            csec = chenab_section_match.group(1)
            chenab_us = _find(r"U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", csec, re.IGNORECASE)
            chenab_ds = _find(r"D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", csec, re.IGNORECASE)
            if chenab_us is None:
                chenab_us = _find(r"MEAN U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", csec, re.IGNORECASE)
            if chenab_ds is None:
                chenab_ds = _find(r"MEAN D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", csec, re.IGNORECASE)
        if chenab_us or chenab_ds:
            obs.append(IRSAObservation(
                asset_name="Chenab @ Marala", asset_type="river_station", observed_at=target_date,
                upstream_discharge_cusecs=chenab_us, downstream_discharge_cusecs=chenab_ds,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ================================================================
        # PANJNAD
        # ================================================================
        panjnad_us = _find(r"PANJNAD.*?U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        panjnad_ds = _find(r"PANJNAD.*?D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        if panjnad_us or panjnad_ds:
            obs.append(IRSAObservation(
                asset_name="Panjnad", asset_type="river_station", observed_at=target_date,
                upstream_discharge_cusecs=panjnad_us, downstream_discharge_cusecs=panjnad_ds,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ================================================================
        # RIM STATION TOTALS
        # ================================================================
        rim_in = _find(r"RIM STATION INFLOWS.*?TOTAL\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        rim_out = _find(r"RIM STATION OUTFLOWS.*?TOTAL\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        if rim_in or rim_out:
            obs.append(IRSAObservation(
                asset_name="Rim Stations Aggregate", asset_type="aggregate",
                observed_at=target_date, inflow_cusecs=rim_in, outflow_cusecs=rim_out,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ================================================================
        # PROVINCIAL RELEASES
        # ================================================================
        prov = {}
        for m in re.finditer(r"(Punjab|Sindh|KP|Balochistan)\s*:\s*([\d,]+)\s*Cs", t, re.IGNORECASE):
            prov[m.group(1).title()] = _c(m.group(2))
        if prov:
            obs.append(IRSAObservation(
                asset_name="IRSA Provincial Releases", asset_type="provincial_release",
                observed_at=target_date, provincial_releases=prov,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ================================================================
        # MERGE THE COLUMN-AWARE PASS
        # Block values fill any field the legacy regexes left empty, and add
        # canal withdrawals plus any station the regex path missed entirely.
        # ================================================================
        by_name = {o.asset_name: o for o in obs}
        for name, (atype, readings, canals) in block_data.items():
            existing = by_name.get(name)
            if existing is None:
                existing = IRSAObservation(
                    asset_name=name, asset_type=atype, observed_at=target_date,
                    source_url=source_url, raw_text=t[:4000],
                )
                obs.append(existing)
                by_name[name] = existing
            for field_name, value in readings.items():
                if value is not None and getattr(existing, field_name, None) is None:
                    setattr(existing, field_name, value)
            if canals:
                existing.canal_withdrawals.update(
                    {k: v for k, v in canals.items() if v is not None}
                )

        # Deduplicate
        seen = set()
        unique = []
        for o in obs:
            key = (o.asset_name, o.observed_at)
            if key not in seen:
                seen.add(key)
                unique.append(o)
        return unique


def parse_irsa_pdf(pdf_path: str, target_date: date, source_url: str = "") -> List[IRSAObservation]:
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    return IRSAParser().parse(pdf_bytes, source_url, target_date)


if __name__ == "__main__":
    test_files = [
        ("Data15-08-2026.pdf", date(2026, 8, 15)),
        ("Data14-08-2026.pdf", date(2026, 8, 14)),
        ("Data09-08-2026.pdf", date(2026, 8, 9)),
    ]
    for path, dt in test_files:
        print(f"\n{'='*70}")
        print(f"  {path}  ({dt})")
        print(f"{'='*70}")
        obs_list = parse_irsa_pdf(path, dt, f"http://pakirsa.gov.pk/Doc/{path}")
        for o in obs_list:
            fields = []
            if o.water_level_ft is not None: fields.append(f"level={o.water_level_ft}")
            if o.dead_level_ft is not None: fields.append(f"dead={o.dead_level_ft}")
            if o.inflow_cusecs is not None: fields.append(f"inflow={o.inflow_cusecs}")
            if o.outflow_cusecs is not None: fields.append(f"outflow={o.outflow_cusecs}")
            if o.upstream_discharge_cusecs is not None: fields.append(f"us={o.upstream_discharge_cusecs}")
            if o.downstream_discharge_cusecs is not None: fields.append(f"ds={o.downstream_discharge_cusecs}")
            if o.discharge_cusecs is not None: fields.append(f"disch={o.discharge_cusecs}")
            if o.provincial_releases: fields.append(f"prov={o.provincial_releases}")
            print(f"  {o.asset_name:<28} {o.asset_type:<18} {'  '.join(fields)}")
        print(f"\n  Total: {len(obs_list)} observations")
