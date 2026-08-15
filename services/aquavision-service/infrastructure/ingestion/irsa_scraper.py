# infrastructure/ingestion/irsa_scraper.py
# Parse IRSA Daily Water Situation PDFs into structured observations.
# Handles the two-column PDF layout where pdfplumber merges left/right columns.
import re
import io
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Dict
import pdfplumber


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


class IRSAParser:
    def parse(self, pdf_bytes: bytes, source_url: str, target_date: date) -> List[IRSAObservation]:
        full_text = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                full_text += (page.extract_text() or "") + "\n"

        obs: List[IRSAObservation] = []
        t = full_text  # shorthand

        # ---- TARBELA ----
        # "INDUS @ TARBELA ... LEVEL = 1550.00 ... DEAD LEVEL = 1402.00 ... MEAN INFLOW = ... MEAN OUTFLOW = ..."
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

        # ---- KABUL @ NOWSHERA ----
        kd = _find(r"KABUL\s*@\s*NOWSHERA.*?MEAN DISCHARGE\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        if kd:
            obs.append(IRSAObservation(
                asset_name="Kabul @ Nowshera", asset_type="river_station", observed_at=target_date,
                discharge_cusecs=kd, source_url=source_url, raw_text=t[:4000],
            ))

        # ---- CHASHMA + KALABAGH (merged two-column block) ----
        # Block from CHASHMA: to TAUNSA: (or CHENAB)
        ck_block = re.search(r"CHASHMA\s*:(.+?)(?:TAUNSA|CHENAB)", t, re.DOTALL | re.IGNORECASE)
        if ck_block:
            block = ck_block.group(1)

            # ChashMA: U/S and D/S discharge
            # In the merged text, ChashMA's U/S appears as "U/S DISCHARGE = NNNNNN Cs"
            # and ChashMA's D/S appears as "D/S DISCHARGE = NNNNNN Cs"
            # We need to distinguish from Kalabagh's values
            # ChashMA values come FIRST in the merged text (left column)
            ch_us_all = re.findall(r"U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)
            ch_ds_all = re.findall(r"D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)

            # ChashMA gets the first U/S and first D/S (left column)
            ch_us = _c(ch_us_all[0]) if ch_us_all else None
            ch_ds = _c(ch_ds_all[0]) if ch_ds_all else None

            # ChashMA dead level is on the same line as first U/S: "U/S DISCHARGE = 356769 Cs DEAD LEVEL = 638.15"
            ch_dead_match = re.search(r"U/S DISCHARGE\s*=\s*[\d,]+\s*Cs\s+DEAD LEVEL\s*=\s*([\d.]+)", block, re.IGNORECASE)
            ch_dead = _c(ch_dead_match.group(1)) if ch_dead_match else None

            if ch_us or ch_ds:
                obs.append(IRSAObservation(
                    asset_name="Chashma Barrage", asset_type="barrage", observed_at=target_date,
                    upstream_discharge_cusecs=ch_us, downstream_discharge_cusecs=ch_ds,
                    dead_level_ft=ch_dead,
                    source_url=source_url, raw_text=t[:4000],
                ))

            # Kalabagh: level, dead level, inflow, outflow
            # Kalabagh level appears after "KALABAGH:" or in the block
            ka_level = _find(r"KALABAGH.*?LEVEL\s*=\s*([\d.]+)", block, re.DOTALL | re.IGNORECASE)
            # If level not found after KALABAGH, try to get it from first LEVEL in block
            if ka_level is None:
                ka_level = _find(r"LEVEL\s*=\s*([\d.]+)", block)

            # Kalabagh dead level is the SECOND DEAD LEVEL in block (right column)
            ka_dead_all = re.findall(r"DEAD LEVEL\s*=\s*([\d.]+)", block, re.IGNORECASE)
            ka_dead = _c(ka_dead_all[1]) if len(ka_dead_all) > 1 else (ka_dead_all[0] if ka_dead_all else None)
            ka_dead = _c(ka_dead) if isinstance(ka_dead, str) else ka_dead

            # Kalabagh inflow is the SECOND MEAN INFLOW (right column)
            ka_inf_all = re.findall(r"MEAN INFLOW\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)
            ka_inf = _c(ka_inf_all[0]) if ka_inf_all else None  # Actually both columns may have inflow

            # Kalabagh outflow
            ka_outf = _find(r"MEAN OUTFLOW\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)

            # Kalabagh U/S and D/S are the SECOND occurrence (right column)
            ka_us = _c(ch_us_all[1]) if len(ch_us_all) > 1 else None
            ka_ds = _c(ch_ds_all[1]) if len(ch_ds_all) > 1 else None

            if ka_level or ka_inf or ka_outf:
                obs.append(IRSAObservation(
                    asset_name="Kalabagh (Indus)", asset_type="river_station", observed_at=target_date,
                    water_level_ft=ka_level, dead_level_ft=ka_dead,
                    upstream_discharge_cusecs=ka_us, downstream_discharge_cusecs=ka_ds,
                    inflow_cusecs=ka_inf, outflow_cusecs=ka_outf,
                    source_url=source_url, raw_text=t[:4000],
                ))

        # ---- TAUNSA ----
        # Block from TAUNSA: to next barrage header
        # "TAUNSA:\nU/S DISCHARGE = 238045 Cs GUDDU:\nD/S DISCHARGE = 224145 Cs U/S DISCHARGE = 209206 Cs\n..."
        taunsa_block = re.search(r"TAUNSA\s*:?\s*(.+?)(?:GUDDU|KOTRI|SUKKUR)", t, re.DOTALL | re.IGNORECASE)
        taunsa_us = None
        taunsa_ds = None
        if taunsa_block:
            block = taunsa_block.group(1)
            taunsa_us = _find(r"U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)
            taunsa_ds = _find(r"D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)

        # Taunsa D/S may be on the same line as GUDDU header
        if taunsa_ds is None:
            taunsa_ds_match = re.search(r"TAUNSA.*?D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs\s+GUDDU", t, re.DOTALL | re.IGNORECASE)
            if taunsa_ds_match:
                taunsa_ds = _c(taunsa_ds_match.group(1))

        # Also try: "D/S DISCHARGE = 224145 Cs U/S DISCHARGE = 209206 Cs" pattern
        # where first D/S is Taunsa and second U/S is Guddu
        if taunsa_ds is None:
            taunsa_ds_match = re.search(r"TAUNSA.*?D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
            if taunsa_ds_match:
                taunsa_ds = _c(taunsa_ds_match.group(1))

        if taunsa_us or taunsa_ds:
            obs.append(IRSAObservation(
                asset_name="Taunsa Barrage", asset_type="barrage", observed_at=target_date,
                upstream_discharge_cusecs=taunsa_us, downstream_discharge_cusecs=taunsa_ds,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ---- GUDDU ----
        guddu_block = re.search(r"GUDDU\s*:?\s*(.+?)(?:KOTRI|SUKKUR)", t, re.DOTALL | re.IGNORECASE)
        guddu_us = None
        guddu_ds = None
        if guddu_block:
            block = guddu_block.group(1)
            # First U/S in Guddu block is Guddu's
            guddu_us = _find(r"U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)
            # D/S: first in block is Taunsa's (from two-column merge), second is Guddu's
            ds_all = re.findall(r"D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)
            guddu_ds = _c(ds_all[1]) if len(ds_all) > 1 else (_c(ds_all[0]) if ds_all else None)

        if guddu_us or guddu_ds:
            obs.append(IRSAObservation(
                asset_name="Guddu Barrage", asset_type="barrage", observed_at=target_date,
                upstream_discharge_cusecs=guddu_us, downstream_discharge_cusecs=guddu_ds,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ---- SUKKUR ----
        # Sukkur block: from SUKKUR: to KOTRI or CHENAB
        # "SUKKUR: U/S DISCHARGE = 153592 Cs\nU/S DISCHARGE = 199130 Cs D/S DISCHARGE = 111427 Cs\n..."
        sukkur_us = None
        sukkur_ds = None

        # Try: "SUKKUR: U/S DISCHARGE = NNNNNN Cs" (Sukkur U/S on header line)
        sukkur_inline = re.search(r"SUKKUR\s*:\s*U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", t, re.IGNORECASE)
        if sukkur_inline:
            sukkur_us = _c(sukkur_inline.group(1))

        # Sukkur D/S and second U/S (may be Kotri's U/S) on following lines
        # Block from SUKKUR to CHENAB/KOTRI
        sukkur_block = re.search(r"SUKKUR\s*:?\s*(.+?)(?:CHENAB|KOTRI)", t, re.DOTALL | re.IGNORECASE)
        if sukkur_block:
            block = sukkur_block.group(1)
            us_all = re.findall(r"U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)
            ds_all = re.findall(r"D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)

            # Sukkur U/S is the SECOND U/S in the block (first was on header line)
            if sukkur_us is None and len(us_all) >= 1:
                sukkur_us = _c(us_all[0])

            # Sukkur D/S is the FIRST D/S
            if ds_all:
                sukkur_ds = _c(ds_all[0])

        if sukkur_us or sukkur_ds:
            obs.append(IRSAObservation(
                asset_name="Sukkur Barrage", asset_type="barrage", observed_at=target_date,
                upstream_discharge_cusecs=sukkur_us, downstream_discharge_cusecs=sukkur_ds,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ---- KOTRI ----
        # Kotri block: from KOTRI: to CHENAB
        # "KOTRI:\nSUKKUR: U/S DISCHARGE = 153592 Cs\nU/S DISCHARGE = 199130 Cs D/S DISCHARGE = 111427 Cs\nD/S DISCHARGE = 145110 Cs..."
        kotri_us = None
        kotri_ds = None
        kotri_block = re.search(r"KOTRI\s*:?\s*(.+?)(?:CHENAB)", t, re.DOTALL | re.IGNORECASE)
        if kotri_block:
            block = kotri_block.group(1)
            us_all = re.findall(r"U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)
            ds_all = re.findall(r"D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", block, re.IGNORECASE)

            # Kotri U/S is the SECOND U/S (first is Sukkur's on header line)
            if len(us_all) >= 2:
                kotri_us = _c(us_all[1])
            # Kotri D/S is the SECOND D/S
            if len(ds_all) >= 2:
                kotri_ds = _c(ds_all[1])

        if kotri_us or kotri_ds:
            obs.append(IRSAObservation(
                asset_name="Kotri Barrage", asset_type="barrage", observed_at=target_date,
                upstream_discharge_cusecs=kotri_us, downstream_discharge_cusecs=kotri_ds,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ---- CHENAB @ MARALA ----
        marala_us = _find(r"CHENAB\s*@\s*MARALA.*?MEAN U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        marala_ds = _find(r"CHENAB\s*@\s*MARALA.*?MEAN D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        if marala_us or marala_ds:
            obs.append(IRSAObservation(
                asset_name="Chenab @ Marala", asset_type="river_station", observed_at=target_date,
                upstream_discharge_cusecs=marala_us, downstream_discharge_cusecs=marala_ds,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ---- MANGLA ----
        mangla_level = _find(r"MANGLA.*?LEVEL\s*=\s*([\d.]+)", t, re.DOTALL | re.IGNORECASE)
        mangla_dead = _find(r"MANGLA.*?DEAD LEVEL\s*=\s*([\d.]+)", t, re.DOTALL | re.IGNORECASE)
        mangla_inf = _find(r"MANGLA.*?MEAN INFLOW\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        mangla_outf = _find(r"MANGLA.*?MEAN OUTFLOW\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        if mangla_level or mangla_inf or mangla_outf:
            obs.append(IRSAObservation(
                asset_name="Mangla Reservoir", asset_type="reservoir", observed_at=target_date,
                water_level_ft=mangla_level, dead_level_ft=mangla_dead,
                inflow_cusecs=mangla_inf, outflow_cusecs=mangla_outf,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ---- PANJNAD ----
        panjnad_us = _find(r"PANJNAD.*?U/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        panjnad_ds = _find(r"PANJNAD.*?D/S DISCHARGE\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        if panjnad_us or panjnad_ds:
            obs.append(IRSAObservation(
                asset_name="Panjnad", asset_type="river_station", observed_at=target_date,
                upstream_discharge_cusecs=panjnad_us, downstream_discharge_cusecs=panjnad_ds,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ---- RIM STATION TOTALS ----
        rim_in = _find(r"RIM STATION INFLOWS.*?TOTAL\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        rim_out = _find(r"RIM STATION OUTFLOWS.*?TOTAL\s*=\s*([\d,]+)\s*Cs", t, re.DOTALL | re.IGNORECASE)
        if rim_in or rim_out:
            obs.append(IRSAObservation(
                asset_name="Rim Stations Aggregate", asset_type="aggregate",
                observed_at=target_date, inflow_cusecs=rim_in, outflow_cusecs=rim_out,
                source_url=source_url, raw_text=t[:4000],
            ))

        # ---- PROVINCIAL RELEASES ----
        prov = {}
        for m in re.finditer(r"(Punjab|Sindh|KP|Balochistan)\s*:\s*([\d,]+)\s*Cs", t, re.IGNORECASE):
            prov[m.group(1).title()] = _c(m.group(2))
        if prov:
            obs.append(IRSAObservation(
                asset_name="IRSA Provincial Releases", asset_type="provincial_release",
                observed_at=target_date, provincial_releases=prov,
                source_url=source_url, raw_text=t[:4000],
            ))

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
