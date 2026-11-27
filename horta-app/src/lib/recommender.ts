// horta-app/src/lib/recommender.ts
import seedData from './data/seed.json';

export type LayerId = 'emergent' | 'canopy' | 'mid' | 'lower_mid' | 'ground';

export interface SiteInput {
  tempC?: number;
  rainMm?: number;
  soilPh?: number;
  drainage?: 'well_drained' | 'wet' | 'any';
  preferPancs?: boolean;
  primaryCashCropId?: string;
}

export interface Species {
  id: string;
  common_name_pt: string;
  scientific_name: string | null;
  layer_id: LayerId;
  succession_stage: string | null;
  role_in_system: string | null;
  is_panc: number;
  shade_tolerance: string | null;
  drainage_requirement: string | null;
  opt_temp_min: number | null;
  opt_temp_max: number | null;
  abs_temp_min: number | null;
  abs_temp_max: number | null;
  opt_rain_min: number | null;
  opt_rain_max: number | null;
  abs_rain_min: number | null;
  abs_rain_max: number | null;
  soil_ph_min: number | null;
  soil_ph_max: number | null;
  abs_ph_min: number | null;
  abs_ph_max: number | null;
  layout_notes: string | null;
  harvest_notes_en: string | null;
  harvest_notes_pt: string | null;
}

export interface ScoredSpecies {
  species: Species;
  score: number;
  reasons: string[];
  penalties: string[];
  isCompanionMatch: boolean;
  isAntagonistMatch: boolean;
}

export interface GuildResult {
  slots: Record<LayerId, ScoredSpecies | null>;
  warnings: string[];
  blueprint: string[];
}

const LAYERS_ORDER: LayerId[] = ['emergent', 'canopy', 'mid', 'lower_mid', 'ground'];

const allSpecies = (seedData.species as Species[]).filter(
  (sp) => Boolean(sp.scientific_name) && (sp.opt_temp_min !== null || sp.soil_ph_min !== null)
);

const allRelations = seedData.relations as Array<{
  species_a_id: string;
  species_b_id: string | null;
  species_b_label: string;
  relation_type: string;
}>;

const ALIASES: Record<string, string[]> = {
  cacau: ['cacau', 'cacao', 'cocoa'],
  mandioca: ['mandioca', 'macaxeira', 'cassava'],
  pimenta: ['pimenta', 'black pepper', 'pepper'],
  castanha: ['castanha', 'brazil nut', 'castanha-do-pará'],
  ingá: ['inga', 'ingá'],
  açaí: ['acai', 'açaí'],
  cupuaçu: ['cupuacu', 'cupuaçu'],
  batata: ['batata-ariá', 'batata aria', 'ariá', 'aria'],
};

function getSearchTerms(sp: Species): string[] {
  const base = sp.common_name_pt.toLowerCase().split(/[\s-(/]/)[0];
  return ALIASES[base] ?? (base.length > 3 ? [base] : []);
}

function getRelationStatus(
  spA: Species,
  spB: Species
): { isCompanion: boolean; isAntagonist: boolean; avoidNote?: string } {
  if (spA.id === spB.id) return { isCompanion: false, isAntagonist: false };

  const relsA = allRelations.filter((r) => r.species_a_id === spA.id);
  const relsB = allRelations.filter((r) => r.species_a_id === spB.id);
  const termsA = getSearchTerms(spA);
  const termsB = getSearchTerms(spB);

  const matchingRels = [
    ...relsA.filter(
      (r) =>
        r.species_b_id === spB.id ||
        termsB.some((t) => r.species_b_label.toLowerCase().includes(t))
    ),
    ...relsB.filter(
      (r) =>
        r.species_b_id === spA.id ||
        termsA.some((t) => r.species_b_label.toLowerCase().includes(t))
    ),
  ];

  if (matchingRels.length === 0) {
    return { isCompanion: false, isAntagonist: false };
  }

  const avoidRel = matchingRels.find((r) => r.species_b_label.toLowerCase().includes('avoid'));
  if (avoidRel) {
    return { isCompanion: false, isAntagonist: true, avoidNote: avoidRel.species_b_label };
  }

  return { isCompanion: true, isAntagonist: false };
}

function rangeScore(
  label: string,
  val: number | undefined,
  optMin: number | null,
  optMax: number | null,
  absMin: number | null,
  absMax: number | null,
  softLow = 1,
  softHigh = 1
): { pts: number; penalty?: string } {
  if (val === undefined || (optMin === null && optMax === null)) return { pts: 10 };
  if (optMin !== null && optMax !== null && val >= optMin && val <= optMax) return { pts: 20 };

  const effAbsMin = absMin ?? (optMin !== null ? optMin - softLow : null);
  const effAbsMax = absMax ?? (optMax !== null ? optMax + softHigh : null);

  if (effAbsMin !== null && effAbsMax !== null && val >= effAbsMin && val <= effAbsMax) {
    return {
      pts: 10,
      penalty: `${label} outside optimal (${val}; ideal ${optMin ?? '?'}–${optMax ?? '?'}, tolerated ${effAbsMin}–${effAbsMax}) [+10 of 20 pts]`,
    };
  }

  return {
    pts: -15,
    penalty: `${label} out of range (${val}; optimal ${optMin ?? '?'}–${optMax ?? '?'}, max tolerance ${effAbsMin ?? '?'}–${effAbsMax ?? '?'}) [−15 pts]`,
  };
}

function isSoilHealer(sp: Species): boolean {
  const role = (sp.role_in_system || '').toLowerCase();
  return role.includes('nitrogen') || role.includes('biomass');
}

function isCashCrop(sp: Species): boolean {
  return (sp.role_in_system || '').toLowerCase().includes('cash crop');
}

export function rankSpeciesForSite(site: SiteInput): ScoredSpecies[] {
  const anchorSp = site.primaryCashCropId
    ? allSpecies.find((s) => s.id === site.primaryCashCropId)
    : undefined;

  const results: ScoredSpecies[] = [];

  for (const sp of allSpecies) {
    const reasons: string[] = [];
    const penalties: string[] = [];
    let rawScore = 0;

    // Drainage check (Wet / Várzea sites)
    if (site.drainage === 'wet') {
      if (sp.drainage_requirement === 'tolerates_wet_soils') {
        rawScore += 10;
        reasons.push('Thrives in wet / floodplain soils (+10 pts)');
      } else if (sp.drainage_requirement === 'strictly_well_drained') {
        rawScore -= 20;
        penalties.push('Strictly requires well-drained soil; high root-rot risk on Wet/Várzea sites [−20 pts]');
      } else if (sp.drainage_requirement === 'well_drained') {
        rawScore -= 15;
        penalties.push('Prefers well-drained soil — use raised beds/mounds on Wet/Várzea sites [−15 pts]');
      }
    }

    // Climate & soil checks
    const t = rangeScore('Temp', site.tempC, sp.opt_temp_min, sp.opt_temp_max, sp.abs_temp_min, sp.abs_temp_max, 7, 6);
    const r = rangeScore('Rain', site.rainMm, sp.opt_rain_min, sp.opt_rain_max, sp.abs_rain_min, sp.abs_rain_max, 500, 1200);
    const p = rangeScore('pH', site.soilPh, sp.soil_ph_min, sp.soil_ph_max, sp.abs_ph_min, sp.abs_ph_max, 1, 1);

    rawScore += t.pts + r.pts + p.pts;
    if (t.penalty) penalties.push(t.penalty);
    if (r.penalty) penalties.push(r.penalty);
    if (p.penalty) penalties.push(p.penalty);

    // Agroforestry bonuses
    if (site.preferPancs && sp.is_panc === 1) {
      rawScore += 12;
      reasons.push('PANC (+12 pts)');
    }
    if (isSoilHealer(sp)) {
      rawScore += 10;
      reasons.push('Soil healer: N-fixer / Biomass (+10 pts)');
    }

    // Companion vs. Antagonist check against primary anchor crop
    let isCompanionMatch = false;
    let isAntagonistMatch = false;
    if (anchorSp && sp.id !== anchorSp.id) {
      const rel = getRelationStatus(anchorSp, sp);
      isCompanionMatch = rel.isCompanion;
      isAntagonistMatch = rel.isAntagonist;

      if (isAntagonistMatch) {
        rawScore -= 20;
        penalties.push(`Avoid pairing with ${anchorSp.common_name_pt}: ${rel.avoidNote} [−20 pts]`);
      } else if (isCompanionMatch) {
        rawScore += 15;
        reasons.push(`Recommended companion for ${anchorSp.common_name_pt} (+15 pts)`);
      }
    }

    const score = Math.max(0, Math.min(100, rawScore));
    results.push({ species: sp, score, reasons, penalties, isCompanionMatch, isAntagonistMatch });
  }

  return results.sort((a, b) => b.score - a.score);
}

export function getOptionsForLayer(layer: LayerId, site: SiteInput): ScoredSpecies[] {
  return rankSpeciesForSite(site).filter((item) => item.species.layer_id === layer);
}

export function buildRecommendedGuild(
  site: SiteInput,
  activeLayers: LayerId[] = LAYERS_ORDER
): GuildResult {
  const ranked = rankSpeciesForSite(site);
  const slots: Record<LayerId, ScoredSpecies | null> = {
    emergent: null,
    canopy: null,
    mid: null,
    lower_mid: null,
    ground: null,
  };

  if (site.primaryCashCropId) {
    const anchor = ranked.find((x) => x.species.id === site.primaryCashCropId);
    if (anchor) slots[anchor.species.layer_id] = anchor;
  }

  for (const layer of activeLayers) {
    if (!slots[layer]) {
      // Avoid auto-picking an antagonist if a safe alternative exists
      slots[layer] =
        ranked.find((x) => x.species.layer_id === layer && !x.isAntagonistMatch) ??
        ranked.find((x) => x.species.layer_id === layer) ??
        null;
    }
  }

  const chosen = Object.values(slots).filter(Boolean) as ScoredSpecies[];
  if (!chosen.some((c) => isSoilHealer(c.species))) {
    const healer = ranked.find(
      (x) =>
        activeLayers.includes(x.species.layer_id) &&
        isSoilHealer(x.species) &&
        !x.isAntagonistMatch &&
        x.species.id !== site.primaryCashCropId
    );
    if (healer) slots[healer.species.layer_id] = healer;
  }

  return evaluateGuild(slots);
}

export function evaluateGuild(slots: Record<LayerId, ScoredSpecies | null>): GuildResult {
  const chosen = Object.values(slots).filter(Boolean) as ScoredSpecies[];
  const warnings: string[] = [];

  // 1. Core functional checks
  if (!chosen.some((c) => isSoilHealer(c.species))) {
    warnings.push('No nitrogen-fixer or heavy biomass plant selected — add Ingá-cipó, Gliricidia, or Banana to restore soil.');
  }
  if (!chosen.some((c) => isCashCrop(c.species))) {
    warnings.push('No primary cash crop selected — consider adding Açaí, Cupuaçu, Banana, or Jambu for farm income.');
  }
  if (!chosen.some((c) => c.species.is_panc === 1)) {
    warnings.push('No PANC species included — add a ground or lower-mid PANC (e.g., Jambu, Cariru, Taioba).');
  }

  // 2. Antagonist pair check across all selected slots
  for (let i = 0; i < chosen.length; i++) {
    for (let j = i + 1; j < chosen.length; j++) {
      const a = chosen[i].species;
      const b = chosen[j].species;
      const rel = getRelationStatus(a, b);
      if (rel.isAntagonist) {
        warnings.push(`Avoid planting ${a.common_name_pt} next to ${b.common_name_pt} (${rel.avoidNote}).`);
      }
    }
  }

  // 3. Shade / canopy mismatch check
  const hasUpperCanopy = Boolean(slots.emergent || slots.canopy);
  const hasAnyShadeAboveGround = Boolean(slots.emergent || slots.canopy || slots.mid);

  const exposedShadeLovers: ScoredSpecies[] = [];
  if (!hasUpperCanopy && slots.mid && (slots.mid.species.shade_tolerance || '').toLowerCase() === 'partial shade') {
    exposedShadeLovers.push(slots.mid);
  }
  if (!hasAnyShadeAboveGround) {
    for (const s of [slots.lower_mid, slots.ground]) {
      if (s && (s.species.shade_tolerance || '').toLowerCase() === 'partial shade') {
        exposedShadeLovers.push(s);
      }
    }
  }
  if (exposedShadeLovers.length > 0) {
    warnings.push(
      `No shade layer above partial-shade crops (${exposedShadeLovers.map((s) => s.species.common_name_pt).join(', ')}).`
    );
  }

  if (hasUpperCanopy) {
    const sunLovers = [slots.lower_mid, slots.ground]
      .filter(Boolean)
      .filter((c) => (c!.species.shade_tolerance || '').toLowerCase() === 'full sun') as ScoredSpecies[];
    if (sunLovers.length > 0) {
      warnings.push(
        `${sunLovers.map((s) => s.species.common_name_pt).join(', ')} prefer Full Sun — plant in sunny alley edges or prune the upper canopy regularly.`
      );
    }
  }

  // 4. Succession balance check
  const stages = chosen.map((c) => (c.species.succession_stage || '').toLowerCase());
  if (!stages.some((s) => s.includes('placenta'))) {
    warnings.push('No Placenta (0–2 yr) species selected — add a fast ground/lower-mid crop for Year 1 soil cover and early harvest.');
  }
  if (!stages.some((s) => s.includes('secondary') || s.includes('climax'))) {
    warnings.push('No Secondary or Climax species selected — add mid/canopy trees for long-term structure and income.');
  }

  const name = (l: LayerId) => slots[l]?.species.common_name_pt ?? '—';
  const blueprint = [
    `Main Tree Line (every 3–5 m): ${name('emergent')} (Emergent) + ${name('canopy')} (Canopy)`,
    `Between Trees (every 2–3 m): ${name('mid')} (Mid-layer)`,
    `Alley / Raised Beds (1–2 m strips between tree lines): ${name('lower_mid')} (Lower-mid) + ${name('ground')} (Ground cover)`,
  ];

  return { slots, warnings, blueprint };
}